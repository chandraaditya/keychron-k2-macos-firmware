"""A88 callbacks through captured root GET/SET and ROM updater delegation.

No hardware. Retains the A87 protocol tests; adds the independently traced
Apple FF/F0 exchange, every selector, wrong types/sizes and buffer reuse.
"""
import struct
from pathlib import Path
import sys
import unittest
from research.test_radio_apple_component import AppleComponentTests as BaseTests
from research.test_radio_apple_component import ROOT,BASE,OBJ,SHADOW,APP,TRANS,LEN,STACK,put,word
sys.path.insert(0,str(ROOT/'firmware'))
from build_radio_candidate import assemble

class KeyholeComponentTests(BaseTests):
    @classmethod
    def setUpClass(cls):
        cls.code,cls.syms=assemble(ROOT/'firmware/radio_apple_keyhole_component.S')
        for slot,target in [('address_getter','get_report'),('address_notify','notify'),
                            ('address_connect','connected'),('address_setter','root_set_report')]:
            struct.pack_into('<I',cls.code,cls.syms[slot],BASE+cls.syms[target] | 1)
    def setUp(self):
        super().setUp();put(self.u,0x208ea8,OBJ)
    def select(self,selector,*,kind=3,rid=0xff,n=1):
        payload=0x20dd20;self.u.mem_write(payload,bytes([selector,0]))
        return self.call(word(self.u,0x208d30),(APP,TRANS,kind,rid),(payload,n,0))
    def test_Apple_identity_and_battery_keyhole_framing(self):
        self.assertEqual(self.select(0x34),0)
        expected=bytes([0xf0,0x34,3,0,0])+bytes.fromhex('102030405060')+bytes(67)
        self.assertEqual(len(expected),78)
        self.assertEqual(self.get(3,0xf0),(0,expected))
        self.assertEqual(self.select(0x90),0)
        self.assertEqual(self.get(1,0xf0),(0,bytes([0xf0,0x90,0,58])))
    def test_every_selector_and_invalid_selection_clears_prior_state(self):
        for selector in range(256):
            self.assertEqual(self.select(0x34),0)
            status=self.select(selector)
            if selector in (0x34,0x90):self.assertEqual(status,0)
            else:
                self.assertEqual(status,2)
                self.assertEqual(self.get(1,0xf0),(2,b''))
                self.assertEqual(self.get(3,0xf0),(2,b''))
    def test_keyhole_requires_matching_type_and_prior_valid_selection(self):
        self.assertEqual(self.get(1,0xf0),(2,b''))
        self.select(0x34);self.assertEqual(self.get(1,0xf0),(2,b''))
        self.select(0x90);self.assertEqual(self.get(3,0xf0),(2,b''))
        self.assertEqual(self.get(2,0xf0),(2,b''))
    def test_short_reply_does_not_corrupt_subsequent_identity_header(self):
        self.select(0x90);self.get(1,0xf0)
        self.assertEqual(self.get(3,0x34)[1][:4],b'\x34\x03\0\0')
        self.select(0x34)
        self.assertEqual(self.get(3,0xf0)[1][:5],b'\xf0\x34\x03\0\0')
    def test_all_percentages_through_keyhole(self):
        self.select(0x90)
        for percent in range(101):
            self.u.mem_write(OBJ+0x14,bytes([percent]))
            self.assertEqual(self.get(1,0xf0),(0,bytes([0xf0,0x90,0,percent])))
    def test_wrong_FF_shapes_retain_original_failure_behavior(self):
        for kind,n in [(1,1),(2,1),(3,0),(3,2)]:
            self.assertEqual(self.select(0x34,kind=kind,n=n),2)
    def test_original_update_read_setup_delegates_unchanged(self):
        payload=0x20dd20
        body=struct.pack('<IH',0x208f02,14)
        body+=bytes([(-0x71-sum(body))&255])
        self.u.mem_write(payload,body)
        self.assertEqual(self.call(word(self.u,0x208d30),(APP,TRANS,3,0x71),(payload,len(body),0)),0)
        self.assertEqual(word(self.u,0x20ca00+0x18),0x208f02)
    def test_installer_declines_unexpected_original_root_setter(self):
        put(self.u,OBJ,0x4c2f4);put(self.u,0x208d30,0x12345)
        self.assertEqual(self.call(BASE,(OBJ,0,0,0)),0)
        self.assertEqual(word(self.u,0x208d30),0x12345)
        self.assertEqual(self.allocs,[])

if __name__=='__main__':unittest.main()
