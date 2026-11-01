"""Actual ROM scatter -> complete DS parser -> heap regression; no device I/O.

Models EEPROM transport, hardware patch-register installation, watchdog service,
and the startup pin probe. Does not model the whole reset or scheduler.
Historical source/images are only read; builds go to temporary directories.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn import arm_const as r

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'firmware'))
from build_radio_candidate import build
from build_radio_phase1_candidate import build_phase1

def word(cpu,address):return int.from_bytes(cpu.mem_read(address,4),'little')
def put(cpu,address,value):cpu.mem_write(address,struct.pack('<I',value))

class PhaseOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.old=Path(cls.tmp.name)/'old';cls.new=Path(cls.tmp.name)/'new'
        cls.historical=ROOT/'private/candidates/radio-battery-initial'
        cls.historical_bytes={p.name:p.read_bytes() for p in cls.historical.iterdir() if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            cls.old_manifest=build(out=cls.old)
            cls.new_manifest=build_phase1(out=cls.new)
        cls.rom=(ROOT/'private/bt-rom-000000-050000.bin').read_bytes()
        cls.ram=(ROOT/'private/ram-200000.bin').read_bytes()

    def machine(self,*,old=False,phase=None,probe=0,corrupt_call=False):
        directory=self.old if old else self.new
        manifest=self.old_manifest if old else self.new_manifest
        cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        for address,length in ((0,0x80000),(0x200000,0x10000),(0x300000,0x100000),(0x600000,0x10000)):
            cpu.mem_map(address,length)
        cpu.mem_write(0,self.rom);cpu.mem_write(0x200000,self.ram)
        cpu.mem_write(0x201344,b'\0')
        cpu.reg_write(r.UC_ARM_REG_SP,0x200400)
        cpu.emu_start(0x2f1,0x454,count=1000000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x454)
        self.assertEqual(bytes(cpu.mem_read(0x201344,4)),bytes.fromhex('01030000'))
        # The original failure was concealed by manually forcing this byte0.
        if phase is not None:cpu.mem_write(0x201344,bytes([phase]))
        cpu.mem_write(0x205e10,b'\x10');put(cpu,0x205e1c,0x4000);put(cpu,0x200c80,0)
        dynamic=(directory/'dynamic-section.bin').read_bytes()
        eeprom=bytearray(65536);eeprom[0x4000:0x4000+len(dynamic)]=dynamic
        trace=[]
        def hook(cpu,address,size,data):
            if address==0x1cb34:
                source=cpu.reg_read(r.UC_ARM_REG_R0);dest=cpu.reg_read(r.UC_ARM_REG_R1);length=cpu.reg_read(r.UC_ARM_REG_R2)
                self.assertLessEqual(source+length,len(eeprom))
                cpu.mem_write(dest,bytes(eeprom[source:source+length]));cpu.reg_write(r.UC_ARM_REG_R0,1)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address in (0x40acc,0x2c428,0x40e86):
                cpu.reg_write(r.UC_ARM_REG_R0,probe if address==0x40e86 else 0)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address==0x209014:
                if corrupt_call:put(cpu,0x206aa8,0xbf00bf00)
                trace.append(('boot-entry',word(cpu,0x201350),word(cpu,0x206aa8)))
            elif 0x209014<=address<manifest['component_base']:
                # Observe before each instruction; no global write hook that
                # changes Unicorn's self-page zero-fill execution behavior.
                trace.append((address,word(cpu,0x201350),word(cpu,0x206aa8)))
            elif address==0x294a0:
                self.fail('ROM assertion during actual heap initialization')
        cpu.hook_add(UC_HOOK_CODE,hook)
        cpu.reg_write(r.UC_ARM_REG_SP,0x2003f8);cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.reg_write(r.UC_ARM_REG_R0,0x4000)
        cpu.emu_start(0x1d15d,0x70000,count=1000000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP),0x2003f8)
        self.assertEqual(word(cpu,0x200400),0x206839)
        self.assertEqual(bytes(cpu.mem_read(0x208fd8,0x3c)),b'\0'*0x3c)
        self.assertEqual(bytes(cpu.mem_read(0x209014,manifest['extension_bytes'])),(directory/'extension.bin').read_bytes())
        return cpu,trace,manifest

    def test_original_default_build_is_byte_identical_and_files_untouched(self):
        self.assertEqual(self.old_manifest['candidate_dynamic_sha256'],'b3f34bdbe1e5c32ff65707482cbddf621efee8fe705a63e1e7a82f7d8d8806ea')
        for name in ('dynamic-section.bin','extension.bin','manifest.json','disassembly.txt'):
            self.assertEqual((self.old/name).read_bytes(),self.historical_bytes[name])
        self.assertEqual({p.name:p.read_bytes() for p in self.historical.iterdir() if p.is_file()},self.historical_bytes)

    def test_original_candidate_reproduces_observed_failure(self):
        cpu,trace,m=self.machine(old=True)
        self.assertEqual(word(cpu,0x201350),0x209014)
        self.assertEqual(bytes(cpu.mem_read(0x206aa8,4)),bytes.fromhex('01f06afc'))
        self.assertTrue(any(entry[0]=='boot-entry' for entry in trace))

    def test_phase1_reserves_before_publishing_and_heap_preserves_extension(self):
        cpu,trace,m=self.machine()
        end=m['new_heap_stack_start'];new_call=int.from_bytes(bytes.fromhex(m['runtime_hook_bytes']),'little')
        self.assertEqual(word(cpu,0x201350),end)
        self.assertEqual(word(cpu,0x206aa8),new_call)
        for _,arena,call in trace:
            if call==new_call:self.assertEqual(arena,end)
        cpu.reg_write(r.UC_ARM_REG_R0,end);cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.emu_start(0x291c9,0x70000,count=200000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(word(cpu,0x20104c),end)
        self.assertGreater(word(cpu,0x200e90),end)
        self.assertLess(word(cpu,0x200e90),0x20ef00)
        self.assertEqual(bytes(cpu.mem_read(0x209014,m['extension_bytes'])),(self.new/'extension.bin').read_bytes())

    def test_phases0_2_3_decline(self):
        for phase in (0,2,3):
            with self.subTest(phase=phase):
                cpu,_,_=self.machine(phase=phase)
                self.assertEqual(word(cpu,0x201350),0x209014)
                self.assertEqual(bytes(cpu.mem_read(0x206aa8,4)),bytes.fromhex('01f06afc'))

    def test_alternate_probe_retains_arena_guard(self):
        cpu,_,_=self.machine(probe=1)
        self.assertEqual(word(cpu,0x201350),0x2067ec)
        self.assertEqual(bytes(cpu.mem_read(0x206aa8,4)),bytes.fromhex('01f06afc'))

    def test_original_instruction_guard_retained(self):
        cpu,_,_=self.machine(corrupt_call=True)
        self.assertEqual(word(cpu,0x201350),0x209014)
        self.assertEqual(word(cpu,0x206aa8),0xbf00bf00)

    def test_new_identity_and_size_are_separate(self):
        cpu,_,m=self.machine()
        self.assertEqual(bytes(cpu.mem_read(0x208f02,14)),bytes.fromhex('b125860ac002')+b'20261028')
        self.assertEqual(m['phase_guard']['expected'],1)
        # The extra halfword consumes existing alignment padding; total size
        # stays440, while the constructor wrapper and its BL target move.
        self.assertEqual(m['extension_bytes'],440)

    def test_shifted_constructor_wrapper_and_unchanged_battery_component(self):
        cpu,_,m=self.machine()
        base=m['component_base'];offset=base-0x209014
        self.assertEqual(base,self.old_manifest['component_base'])
        self.assertEqual((self.new/'extension.bin').read_bytes()[offset:],
                         (self.old/'extension.bin').read_bytes()[offset:])
        obj,shadow=0x20c9d4,0x20d800
        put(cpu,obj,0x4c2f4);put(cpu,0x208ea8,obj);put(cpu,0x200e90,0x20cc80)
        calls=[]
        def callbacks(cpu,address,size,data):
            if address==0x208380:
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP)%8,0)
                calls.append('original');cpu.reg_write(r.UC_ARM_REG_R0,0x20cabc)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address==0x1676e:
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),68)
                calls.append('allocate');cpu.reg_write(r.UC_ARM_REG_R0,shadow)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        cpu.hook_add(UC_HOOK_CODE,callbacks)
        preserved=[r.UC_ARM_REG_R4,r.UC_ARM_REG_R5,r.UC_ARM_REG_R6,r.UC_ARM_REG_R7,
                   r.UC_ARM_REG_R8,r.UC_ARM_REG_R9,r.UC_ARM_REG_R10,r.UC_ARM_REG_R11]
        for i,reg in enumerate(preserved):cpu.reg_write(reg,0x12340000+i)
        cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.emu_start(m['boot_symbols']['constructor_wrapper']|1,0x70000,count=20000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP),0x2003f8)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),0x20cabc)
        self.assertEqual([cpu.reg_read(reg) for reg in preserved],[0x12340000+i for i in range(8)])
        self.assertEqual(calls,['original','allocate'])
        self.assertEqual(word(cpu,obj),shadow)
        self.assertEqual(word(cpu,shadow+12),m['component_symbols']['get_report']|1)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PhaseOneTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'device_access':False,
            'actual_ROM_scatter_and_DS_parser_and_heap':True,'complete_reset_or_scheduler':False,
            'modeled':['EEPROM reader','patch registers','watchdog service','startup hardware probe','zero MMIO'],
            'historical_candidate_preserved':True}
    p=ROOT/'private/bt-persistence-research/phase1-regression-results.json'
    p.write_text(json.dumps(report,indent=2)+'\n');p.chmod(0o600)
    raise SystemExit(not result.wasSuccessful())
