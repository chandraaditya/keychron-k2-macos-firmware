"""A88 complete startup, unchanged physical recovery and real constructor hook.

Actual ROM pre-DS/DS/GPIO/I2C setup, modeled EEPROM controller/allocator/SPI.
No native or peripheral access.
"""
import json
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research import test_radio_wp_guard as wp

ROOT=Path(__file__).resolve().parents[1]

class Tests(unittest.TestCase):
    def machine(self,mode='ok'):
        self.m=json.loads((ROOT/'private/candidates/radio-apple-keyhole-profile/manifest.json').read_text())
        self.ds=(ROOT/'private/candidates/radio-apple-keyhole-profile/dynamic-section.bin').read_bytes()
        harness=wp.WPGuardTests()
        return harness.run_case(mode,dynamic=self.ds)[0]
    def test_recovery_prefix_and_successful_DS_are_exact(self):
        cpu=self.machine()
        self.assertEqual(bytes(cpu.mem_read(0x208f04,1)),b'\x88')
        self.assertEqual(wp.word(cpu,0x201350),self.m['heap_start'])
        self.assertEqual(bytes(cpu.mem_read(0x209014,816)),
                         (ROOT/'private/candidates/radio-apple-keyhole-profile/extension.bin').read_bytes())
        # The prefix through A7/load/callback is identical to physical neutral.
        import sys
        sys.path.insert(0,str(ROOT/'firmware'))
        from build_radio_candidate import records,encode
        old=records((ROOT/'private/candidates/radio-rollback-wp/dynamic-section.bin').read_bytes())
        new=records((ROOT/'private/candidates/radio-apple-keyhole-one-boot/dynamic-section.bin').read_bytes())
        self.assertEqual(encode(old[:3]),encode(new[:3]))
    def test_write_failure_keeps_A86_and_original_root_setter(self):
        cpu=self.machine('protected')
        self.assertEqual(bytes(cpu.mem_read(0x208f04,1)),b'\x86')
        self.assertEqual(wp.word(cpu,0x208d30),0x206ad5)
        self.assertEqual(wp.word(cpu,0x205e1c),0x8000)
    def test_heap_and_constructor_install_full_get_and_set_hooks(self):
        cpu=self.machine();end=self.m['heap_start']
        cpu.reg_write(r.UC_ARM_REG_R0,end);cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.emu_start(0x291c9,0x70000,count=200000)
        self.assertEqual(bytes(cpu.mem_read(0x209014,816)),
                         (ROOT/'private/candidates/radio-apple-keyhole-profile/extension.bin').read_bytes())
        obj,shadow=0x20c9d4,0x20d800
        wp.put(cpu,obj,0x4c2f4);wp.put(cpu,0x208ea8,obj)
        calls=[]
        def hook(cpu,address,size,data):
            if address==0x208380:
                calls.append('SPI');cpu.reg_write(r.UC_ARM_REG_R0,0x20cabc)
            elif address==0x1676e:
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),152)
                calls.append('allocate');cpu.reg_write(r.UC_ARM_REG_R0,shadow)
            else:return
            cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        cpu.hook_add(UC_HOOK_CODE,hook)
        registers=[r.UC_ARM_REG_R4,r.UC_ARM_REG_R5,r.UC_ARM_REG_R6,r.UC_ARM_REG_R7,
                   r.UC_ARM_REG_R8,r.UC_ARM_REG_R9,r.UC_ARM_REG_R10,r.UC_ARM_REG_R11]
        for i,reg in enumerate(registers):cpu.reg_write(reg,0x12340000+i)
        cpu.reg_write(r.UC_ARM_REG_SP,0x2003f8);cpu.reg_write(r.UC_ARM_REG_LR,0x70001)
        cpu.emu_start((0x209014+self.m['boot_symbols']['constructor_wrapper'])|1,0x70000,count=20000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_R0),0x20cabc)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP),0x2003f8)
        self.assertEqual([cpu.reg_read(reg)for reg in registers],[0x12340000+i for i in range(8)])
        base=self.m['component_base'];syms=self.m['component_symbols']
        self.assertEqual(wp.word(cpu,shadow+12),(base+syms['get_report'])|1)
        self.assertEqual(wp.word(cpu,0x208d30),(base+syms['root_set_report'])|1)
        self.assertEqual(calls,['SPI','allocate'])

if __name__=='__main__':unittest.main()
