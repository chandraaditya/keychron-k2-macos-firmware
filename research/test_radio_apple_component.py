"""Offline Apple report experiment through captured ROM root GET dispatcher.

No device access. EEPROM and radio are not emulated. Allocation/transport are
modeled; root161E, fallbackD3E, legacy battery getter and clock helpers execute.
"""
import struct
import sys
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn import arm_const as r

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'firmware'))
from build_radio_candidate import assemble

BASE, OBJ, SHADOW, APP = 0x20d000, 0x20c900, 0x20d800, 0x20c000
TRANS, TABLE, BUFFER = 0x20da00, 0x20db00, 0x20dc00
OUT, LEN, STACK, RET = 0x20dd00, 0x20dd04, 0x20ed00, 0x70000
ALLOC, SEND = 0x70100, 0x70200

def put(u,a,n): u.mem_write(a, struct.pack('<I',n))
def word(u,a): return int.from_bytes(u.mem_read(a,4),'little')

class AppleComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.syms = assemble(ROOT/'firmware/radio_apple_component.S')
        for slot,target in [('address_getter','get_report'),('address_notify','notify'),
                            ('address_connect','connected')]:
            struct.pack_into('<I',cls.code,cls.syms[slot],BASE+cls.syms[target] | 1)

    def setUp(self):
        u=self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        for a,n in [(0,0x80000),(0x200000,0x10000),(0x318000,0x1000)]:u.mem_map(a,n)
        u.mem_write(0,(ROOT/'private/bt-rom-000000-050000.bin').read_bytes())
        u.mem_write(0x200000,(ROOT/'private/ram-200000.bin').read_bytes())
        u.mem_write(BASE,bytes(self.code))
        put(u,OBJ,0x4c2f4);u.mem_write(OBJ+4,b'\x03\x00');u.mem_write(OBJ+0x14,b'\x3a')
        u.mem_write(0x2005c8+0x11,b'\x03\x02\x00')
        put(u,APP+0x74,OBJ);put(u,TRANS,TABLE)
        # Real original updater table; untouched fallback GET accepts only72.
        put(u,APP+0x80,0x20ca00);put(u,0x20ca00,0x206794)
        u.mem_write(0x20ca04,bytes(range(0x70,0x76)))
        put(u,TABLE+0x1c,ALLOC|1);put(u,TABLE+0x2c,SEND|1)
        u.mem_write(OBJ+6,bytes.fromhex('102030405060'))
        put(u,0x318088,1000)
        self.allocs=[];self.sent=[];self.alloc_fail=False
        def hook(cpu,a,n,data):
            if a==0x1676e:
                self.allocs.append(cpu.reg_read(r.UC_ARM_REG_R0))
                cpu.reg_write(r.UC_ARM_REG_R0,0 if self.alloc_fail else SHADOW)
            elif a==ALLOC:
                self.allocs.append(cpu.reg_read(r.UC_ARM_REG_R1))
                cpu.reg_write(r.UC_ARM_REG_R0,0 if self.alloc_fail else BUFFER)
            elif a==0x48252:
                cpu.mem_write(cpu.reg_read(r.UC_ARM_REG_R0),bytes(cpu.mem_read(
                    cpu.reg_read(r.UC_ARM_REG_R1),cpu.reg_read(r.UC_ARM_REG_R2))))
            elif a==SEND:
                count=cpu.reg_read(r.UC_ARM_REG_R2)
                self.sent.append(bytes(cpu.mem_read(cpu.reg_read(r.UC_ARM_REG_R1),count)))
                self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP)%8,0)
                self.assertEqual(word(cpu,cpu.reg_read(r.UC_ARM_REG_SP)),1)
                self.assertEqual(word(cpu,cpu.reg_read(r.UC_ARM_REG_SP)+4),0)
            else:return
            cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        self.assertEqual(self.call(BASE,(OBJ,0,0,0)),1)
        self.assertEqual(self.allocs,[152]);self.allocs.clear()

    def call(self,entry,args,extra=()):
        u=self.u
        kept=[r.UC_ARM_REG_R4,r.UC_ARM_REG_R5,r.UC_ARM_REG_R6,r.UC_ARM_REG_R7,
              r.UC_ARM_REG_R8,r.UC_ARM_REG_R9,r.UC_ARM_REG_R10,r.UC_ARM_REG_R11]
        for i,reg in enumerate(kept):u.reg_write(reg,0x12340000+i)
        for reg,v in zip([r.UC_ARM_REG_R0,r.UC_ARM_REG_R1,r.UC_ARM_REG_R2,r.UC_ARM_REG_R3],args):u.reg_write(reg,v)
        for i,v in enumerate(extra):put(u,STACK+4*i,v)
        u.reg_write(r.UC_ARM_REG_SP,STACK);u.reg_write(r.UC_ARM_REG_LR,RET|1)
        u.emu_start(entry|1,RET,count=10000)
        self.assertEqual(u.reg_read(r.UC_ARM_REG_PC),RET)
        self.assertEqual(u.reg_read(r.UC_ARM_REG_SP),STACK)
        self.assertEqual([u.reg_read(reg) for reg in kept],[0x12340000+i for i in range(8)])
        return u.reg_read(r.UC_ARM_REG_R0)

    def get(self,kind,rid,size=0xffffffff):
        status=self.call(0x161e,(APP,TRANS,kind,rid),(size,OUT,LEN))
        ptr,n=word(self.u,OUT),word(self.u,LEN)
        return status,bytes(self.u.mem_read(ptr,n)) if ptr else b''

    def test_all_percentages_via_real_root_dispatch_and_legacy_report(self):
        for value in range(101):
            self.u.mem_write(OBJ+0x14,bytes([value]))
            self.assertEqual(self.get(1,0x90),(0,bytes([0x90,0,value])))
            self.assertEqual(self.get(1,3),(0,bytes([3,value])))

    def test_feature34_complete_and_requested_length_rules(self):
        expected=bytes([0x34,3,0,0])+bytes.fromhex('102030405060')+bytes(67)
        self.assertEqual(len(expected),77)
        self.assertEqual(self.get(3,0x34),(0,expected))
        for n in [0,1,3,76,77,78]:
            self.assertEqual(self.get(3,0x34,n),(0,expected[:n]))
        self.assertEqual(self.get(1,0x90,2),(0,b'\x90\x00'))

    def test_get_does_not_send_or_write_cached_legacy_percentage(self):
        self.get(1,0x90);self.get(3,0x34)
        self.assertEqual(self.sent,[])
        self.assertEqual(bytes(self.u.mem_read(OBJ+5,1)),b'\x00')

    def test_connection_and_changed_notifications_preserve_both_reports(self):
        self.call(BASE+self.syms['connected'],(OBJ,TRANS,0,0))
        self.assertEqual(self.sent,[b'\x03\x3a',b'\x90\x00\x3a'])
        self.sent.clear()
        self.call(BASE+self.syms['notify'],(OBJ,TRANS,0,0))
        self.assertEqual(self.sent,[])
        put(self.u,0x318088,200001)
        self.u.mem_write(OBJ+0x14,b'\x39')
        self.call(BASE+self.syms['notify'],(OBJ,TRANS,0,0))
        self.assertEqual(self.sent,[b'\x03\x39',b'\x90\x00\x39'])

    def test_feature34_address_is_from_current_battery_object(self):
        self.u.mem_write(OBJ+6,bytes.fromhex('aabbccddeeff'))
        self.assertEqual(self.get(3,0x34)[1][4:10],bytes.fromhex('aabbccddeeff'))

    def test_unsupported_reports_use_original_failure_path(self):
        for kind,rid in [(3,0x90),(1,0x34),(3,0xbb),(3,0xb4),(3,0xbc),
                         (3,0xe0),(3,0xc5),(3,0x14)]:
            self.assertEqual(self.get(kind,rid),(2,b''))

    def test_original_keyboard_media_and_system_get_reports_remain(self):
        fixtures=[(1,1,0x8c,0xcc,b'\x01\x02\x00\x04\x05\x06\x00\x00'),
                  (1,2,0xa6,0xdc,b'\x02\x0a\x00'),
                  (1,4,0xb2,None,b'\x04\x01'),
                  (2,1,0xa4,None,b'\x01\x02')]
        for kind,rid,offset,length_offset,data in fixtures:
            self.u.mem_write(APP+offset,data)
            if length_offset is not None:self.u.mem_write(APP+length_offset,bytes([len(data)]))
            self.assertEqual(self.get(kind,rid),(0,data))

    def test_allocator_failure_returns_without_copying(self):
        self.alloc_fail=True
        status,data=self.get(1,0x90)
        # Existing ROM fallback returns success with null allocation: inherited
        # behavior, not an invented error code for this callback.
        self.assertEqual((status,data),(0,b''))

if __name__=='__main__':unittest.main()
