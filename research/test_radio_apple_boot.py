"""Offline complete ROM scatter/DS/BF loader checks for A87 research image.

Reuses established reset harness with modeled EEPROM/hardware. No HID access.
"""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research.test_radio_boot_phase1 import PhaseOneTests, word, put

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'firmware'))
from build_radio_apple_candidate import build_apple
from build_radio_candidate import records

class AppleBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.out=Path(cls.tmp.name)
        cls.m=build_apple(out=cls.out)

    def machine(self):
        x=PhaseOneTests();x.new=self.out
        x.rom=(ROOT/'private/bt-rom-000000-050000.bin').read_bytes()
        x.ram=(ROOT/'private/ram-200000.bin').read_bytes()
        m=dict(self.m);m['new_heap_stack_start']=m['heap_start']
        m['component_symbols']={k:m['component_base']+v for k,v in m['component_symbols'].items()}
        x.new_manifest=m
        return x.machine()[0]

    def test_full_rom_parser_registers_new_sdp_and_reserves_extension(self):
        cpu=self.machine()
        self.assertEqual(word(cpu,0x201350),self.m['heap_start'])
        self.assertEqual(word(cpu,0x202c70),1053)
        address=word(cpu,0x202c6c)
        dynamic=(self.out/'dynamic-section.bin').read_bytes()
        self.assertEqual(dynamic[address-0x4000:address-0x4000+1053],
                         (ROOT/'private/apple-profile/grouped-sdp.bin').read_bytes())
        self.assertEqual(bytes(cpu.mem_read(0x208f02,14)),bytes.fromhex('b125870ac002')+b'20261028')

    def test_original_rom_sdp_loader_reads_full_bf_and_caches_it(self):
        cpu=self.machine();allocs=[]
        def allocate(cpu,a,n,data):
            if a==0x2d222:
                allocs.append(cpu.reg_read(r.UC_ARM_REG_R0))
                cpu.reg_write(r.UC_ARM_REG_R0,0x20d000)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        cpu.hook_add(UC_HOOK_CODE,allocate)
        for _ in range(2):
            cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
            cpu.emu_start(0x17755,0x70000,count=10000)
            self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
            self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),0x20d000)
        self.assertEqual(allocs,[1053])
        self.assertEqual(bytes(cpu.mem_read(0x20d000,1053)),
                         (ROOT/'private/apple-profile/grouped-sdp.bin').read_bytes())

    def test_heap_initialization_preserves_new_extension(self):
        cpu=self.machine();end=self.m['heap_start']
        cpu.reg_write(r.UC_ARM_REG_R0,end);cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.emu_start(0x291c9,0x70000,count=200000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(word(cpu,0x20104c),end)
        self.assertLess(word(cpu,0x200e90),0x20ef00)
        self.assertEqual(bytes(cpu.mem_read(0x209014,self.m['extension_bytes'])),
                         (self.out/'extension.bin').read_bytes())

    def test_original_records_preserved_except_identity_and_added_tail(self):
        original=records((ROOT/'private/bt-eeprom-active-prefix.bin').read_bytes()[0x3c0:])
        new=records((self.out/'dynamic-section.bin').read_bytes())
        for old,now in zip(original[:-2],new[:-4]):
            if old==now:continue
            self.assertEqual(old[0],0xa)
            self.assertEqual(old[1][:4],struct.pack('<I',0x208e80))
            changed=[i for i,(a,b) in enumerate(zip(old[1],now[1])) if a!=b]
            self.assertTrue(all(i in [0x88,*range(0x8c,0x94)] for i in changed))
        self.assertEqual(len(new),len(original)+2)

if __name__=='__main__':unittest.main()
