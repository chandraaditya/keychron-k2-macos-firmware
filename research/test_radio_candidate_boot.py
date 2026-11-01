"""Offline normal-cold-boot candidate contracts, not a reset/scheduler simulator."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as r

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'firmware'))
from build_radio_candidate import build, records, encode, CAPTURE, OUT, DS_START, EXTENSION, sha

RETURN, OBJECT, SHADOW = 0x70000, 0x20c9d4, 0x20d800
KEEP = [r.UC_ARM_REG_R4,r.UC_ARM_REG_R5,r.UC_ARM_REG_R6,r.UC_ARM_REG_R7,
        r.UC_ARM_REG_R8,r.UC_ARM_REG_R9,r.UC_ARM_REG_R10,r.UC_ARM_REG_R11]


def put(cpu, addr, value):
    cpu.mem_write(addr,struct.pack('<I',value))


def word(cpu, addr):
    return struct.unpack('<I',cpu.mem_read(addr,4))[0]


class BootCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.manifest=build()
        cls.dynamic=(OUT/'dynamic-section.bin').read_bytes()
        cls.items=records(cls.dynamic)
        cls.rom=(ROOT/'private/bt-rom-000000-050000.bin').read_bytes()

    def machine(self):
        cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        cpu.mem_map(0,0x80000);cpu.mem_map(0x200000,0x10000)
        cpu.mem_write(0,self.rom)
        # Runtime RAM seeds framework configuration for this partial test;
        # exact persistent initialization records then replace the application.
        cpu.mem_write(0x200000,(ROOT/'private/ram-200000.bin').read_bytes())
        for kind,payload in self.items:
            if kind==0xa:cpu.mem_write(int.from_bytes(payload[:4],'little'),payload[4:])
        return cpu

    def call(self,cpu,address,r0=0,limit=30000):
        cpu.reg_write(r.UC_ARM_REG_R0,r0)
        cpu.reg_write(r.UC_ARM_REG_SP,0x2003f8)
        cpu.reg_write(r.UC_ARM_REG_LR,RETURN|1)
        for i,register in enumerate(KEEP):cpu.reg_write(register,0x12340000+i)
        cpu.emu_start(address|1,RETURN,count=limit)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),RETURN)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP),0x2003f8)
        self.assertEqual([cpu.reg_read(x)for x in KEEP],[0x12340000+i for i in range(8)])
        return cpu.reg_read(r.UC_ARM_REG_R0)

    def run_boot(self,probe=0,phase=0,corrupt_hook=False):
        cpu=self.machine();writes=[]
        put(cpu,0x201350,0x2067ec)
        cpu.mem_write(0x201344,bytes([phase]))
        cpu.mem_write(0x208fd8,b'\xa5'*0x3c)
        if corrupt_hook:put(cpu,0x206aa8,0xbf00bf00)
        def hardware(cpu,address,size,data):
            if address==0x40e86:
                cpu.reg_write(r.UC_ARM_REG_R0,probe)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        def written(cpu,access,address,size,value,data):writes.append((address,size,value))
        cpu.hook_add(UC_HOOK_CODE,hardware)
        # Scope observation to the two publication writes. Unicorn's global
        # write instrumentation changes the optimized ROM zero-fill execution
        # when it writes the same RAM page as the new code; BSS is checked by
        # readback with that instrumentation absent.
        cpu.hook_add(UC_HOOK_MEM_WRITE,written,begin=0x201350,end=0x201353)
        cpu.hook_add(UC_HOOK_MEM_WRITE,written,begin=0x206aa8,end=0x206aab)
        # Execute the real ROM type-0B trampoline, actual original BSS setup,
        # factory registration, and candidate wrapper.
        self.call(cpu,0x29f30,EXTENSION|1)
        self.assertEqual(cpu.mem_read(0x208fd8,0x3c),b'\0'*0x3c)
        self.assertEqual(word(cpu,0x200400),0x206839)
        self.assertEqual(cpu.mem_read(EXTENSION,self.manifest['extension_bytes']),
                         (OUT/'extension.bin').read_bytes())
        return cpu,writes

    def test_original_records_identity_and_byte_exact_roundtrip(self):
        self.assertEqual(encode(self.items),self.dynamic)
        original=records(CAPTURE.read_bytes()[DS_START:])
        differences=[]
        for index,(old,new)in enumerate(zip(original[:-2],self.items[:-3])):
            if old!=new:differences.append(index)
        self.assertEqual(len(differences),1)
        index=differences[0]
        self.assertEqual(int.from_bytes(original[index][1][:4],'little'),0x208e80)
        changed={i for i,(a,b)in enumerate(zip(original[index][1],self.items[index][1]))if a!=b}
        self.assertLessEqual(changed,{4+0x84}|set(range(4+0x88,4+0x90)))
        cpu=self.machine()
        self.assertEqual(cpu.mem_read(0x208f02,14),bytes.fromhex('b125850ac002')+b'20261027')
        self.assertEqual(self.items[-1],(0xfe,b''))
        self.assertEqual(self.items[-2],(0xb,struct.pack('<I',EXTENSION|1)))

    def test_normal_boot_reserves_before_publishing_hook(self):
        cpu,writes=self.run_boot()
        self.assertEqual(word(cpu,0x201350),self.manifest['new_heap_stack_start'])
        expected=int.from_bytes(bytes.fromhex(self.manifest['runtime_hook_bytes']),'little')
        self.assertEqual(word(cpu,0x206aa8),expected)
        reserve=next(i for i,x in enumerate(writes)if x==(0x201350,4,self.manifest['new_heap_stack_start']))
        publish=next(i for i,x in enumerate(writes)if x==(0x206aa8,4,expected))
        self.assertLess(reserve,publish)

    def test_phase_guards_decline_late_install(self):
        for phase in(1,2,3):
            cpu,_=self.run_boot(phase=phase)
            self.assertEqual(word(cpu,0x201350),EXTENSION)
            self.assertEqual(cpu.mem_read(0x206aa8,4),bytes.fromhex(self.manifest['original_hook_bytes']))

    def test_alternate_hardware_probe_declines_install(self):
        cpu,_=self.run_boot(probe=1)
        self.assertEqual(word(cpu,0x201350),0x2067ec)
        self.assertEqual(cpu.mem_read(0x206aa8,4),bytes.fromhex(self.manifest['original_hook_bytes']))

    def test_wrong_original_instruction_declines_install(self):
        cpu,_=self.run_boot(corrupt_hook=True)
        self.assertEqual(word(cpu,0x201350),EXTENSION)
        self.assertEqual(word(cpu,0x206aa8),0xbf00bf00)

    def test_real_heap_initializer_respects_moved_arena(self):
        cpu,_=self.run_boot()
        # Run the actual captured ROM heap/pool initializer with configuration
        # from the snapshot. This is not execution of the whole init task.
        assertions=[]
        def assertion(cpu,address,size,data):
            if address==0x294a0:
                assertions.append(address);cpu.emu_stop()
        cpu.hook_add(UC_HOOK_CODE,assertion)
        self.call(cpu,0x291c8,word(cpu,0x201350),limit=200000)
        self.assertEqual(assertions,[])
        self.assertEqual(word(cpu,0x20104c),self.manifest['new_heap_stack_start'])
        self.assertGreater(word(cpu,0x200e90),self.manifest['new_heap_stack_start']+0x600)
        self.assertEqual(cpu.mem_read(EXTENSION,self.manifest['extension_bytes']),
                         (OUT/'extension.bin').read_bytes())

    def test_runtime_constructor_hook_preserves_return_and_installs_component(self):
        cpu,_=self.run_boot()
        put(cpu,OBJECT,0x4c2f4);put(cpu,0x208ea8,OBJECT)
        put(cpu,0x200e90,0x20cc80)
        original_calls=[]
        def callbacks(cpu,address,size,data):
            if address==0x208380:
                original_calls.append(address)
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP)%8,0)
                cpu.reg_write(r.UC_ARM_REG_R0,0x20cabc)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address==0x1676e:
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),68)
                cpu.reg_write(r.UC_ARM_REG_R0,SHADOW)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        cpu.hook_add(UC_HOOK_CODE,callbacks)
        result=self.call(cpu,self.manifest['boot_symbols']['constructor_wrapper'])
        self.assertEqual(result,0x20cabc)
        self.assertEqual(original_calls,[0x208380])
        self.assertEqual(word(cpu,OBJECT),SHADOW)
        self.assertEqual(word(cpu,SHADOW+12),self.manifest['component_symbols']['get_report']|1)
        decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS)
        instruction=next(decoder.disasm(cpu.mem_read(0x206aa8,4),0x206aa8))
        self.assertEqual((instruction.mnemonic,instruction.op_str),
                         ('bl',f"#{hex(self.manifest['boot_symbols']['constructor_wrapper'])}"))

    def test_reproducible_candidate_and_source_hashes(self):
        with contextlib.redirect_stdout(io.StringIO()):again=build()
        self.assertEqual(again,self.manifest)
        self.assertEqual(sha((OUT/'dynamic-section.bin').read_bytes()),self.manifest['candidate_dynamic_sha256'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BootCandidateTests))
    report={'test_methods':result.testsRun,'passed':result.wasSuccessful(),
            'scope':'Actual ROM0B/startup and heap initializer plus candidate; hardware status, SPI singleton and allocation mocked in selected cases',
            'candidate_dynamic_sha256':sha((OUT/'dynamic-section.bin').read_bytes()),
            'complete_reset_scheduler_or_radio_emulation':False,'device_access':False,'flashed':False,
            'native_macos_ui_verified':False,'physical_activation_or_recovery_verified':False}
    p=OUT/'boot-test-results.json';p.write_text(json.dumps(report,indent=2)+'\n');p.chmod(0o600)
    raise SystemExit(0 if result.wasSuccessful() else 1)
