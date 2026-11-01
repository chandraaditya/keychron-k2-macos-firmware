"""Offline actual-ROM MTU negotiation, send boundary and buffer-pool checks.

No firmware image changes or device APIs. Queue transmission, buffer freeing
and critical-section primitives are modeled; negotiation/allocator code runs.
"""
from pathlib import Path
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import *

ROOT = Path(__file__).resolve().parents[1]
CB, CONFIG, PACKET, STACK, STOP = 0x20e000, 0x20e100, 0x20e200, 0x20ef00, 0x70000


class MTUTests(unittest.TestCase):
    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.u.mem_map(0, 0x80000)
        self.u.mem_map(0x200000, 0x10000)
        self.u.mem_write(0, (ROOT/'private/bt-rom-000000-050000.bin').read_bytes())
        self.u.mem_write(0x200000, (ROOT/'private/ram-200000.bin').read_bytes())
        self.sent, self.freed = [], []
        def hook(u, address, size, unused):
            if address == 0xd032:
                self.sent.append((u.reg_read(UC_ARM_REG_R0), u.reg_read(UC_ARM_REG_R1), u.reg_read(UC_ARM_REG_R2)))
            elif address == 0x71fc:
                self.freed.append(u.reg_read(UC_ARM_REG_R0))
            elif address not in (0x6f3e, 0x6f3c):
                return
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        self.u.hook_add(UC_HOOK_CODE, hook)

    def hput(self, address, value):
        self.u.mem_write(address, struct.pack('<H', value))

    def hget(self, address):
        return struct.unpack('<H', self.u.mem_read(address, 2))[0]

    def call(self, entry, *args):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.u.reg_write(reg, value)
        self.u.reg_write(UC_ARM_REG_SP, STACK)
        self.u.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.u.emu_start(entry | 1, STOP, count=5000)
        self.assertEqual(self.u.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(self.u.reg_read(UC_ARM_REG_SP), STACK)
        return self.u.reg_read(UC_ARM_REG_R0)

    def config(self, mtu):
        self.u.mem_write(CONFIG, bytes(60))
        self.u.mem_write(CONFIG+2, b'\1')
        self.hput(CONFIG+4, mtu)

    def test_peer_receive_mtu_is_clamped_to_global_send_limit(self):
        for cap in (48, 128):
            for peer in (48, 79, 128, 672):
                self.hput(0x2007d2, cap)
                self.config(peer)
                self.assertEqual(self.call(0xeed4, CB, CONFIG), 1)
                self.assertEqual(self.hget(CB+0x3a), min(cap, peer))

    def test_unchanged_hid_template_keeps_local_receive_mtu_48(self):
        template = bytes(self.u.mem_read(0x4aef8, 60))
        self.assertEqual(struct.unpack_from('<H', template, 4)[0], 48)
        self.hput(0x2007d2, 128)
        self.u.mem_write(CONFIG, template)
        self.call(0xef70, CB, CONFIG)
        self.assertEqual(self.hget(CB+0x38), 48)
        self.assertEqual(self.hget(CONFIG+4), 48)

    def test_control_send_drops_only_packets_over_actual_channel_limit(self):
        # Use the real historical control-channel CID and existing link object.
        cid = 0x4b
        channel = 0x20255c+(cid-0x40)*0x7c
        self.assertEqual(self.u.mem_read(channel, 1), b'\1')
        for cap in (48, 128):
            self.hput(channel+0x3a, cap)
            for payload in (4, 47, 48, 77, 78, 127, 128):
                self.sent.clear(); self.freed.clear()
                self.hput(PACKET+2, payload+1) # One additional HIDP DATA header.
                result = self.call(0xe172, cid, PACKET, 0)
                if payload+1 > cap:
                    self.assertEqual(result, 0)
                    self.assertEqual(self.freed, [PACKET]); self.assertEqual(self.sent, [])
                else:
                    self.assertIn(result, (1, 2))
                    self.assertEqual(self.freed, [])
                    self.assertEqual(self.sent, [(channel, 0x1d, PACKET)])

    def test_existing_284_byte_pool_handles_reply_and_larger_receive_allocations(self):
        for requested in (99, 140, 148):
            address = self.call(0x70b6, requested)
            self.assertNotEqual(address, 0)
            self.assertEqual(self.u.mem_read(address-4, 1), b'\1')
            self.assertEqual(self.call(0x71c4, address), 284)

    def test_two_byte_load_override_survives_real_scatter_and_ds_loader(self):
        import sys
        sys.path.insert(0, str(ROOT/'firmware'))
        from build_radio_candidate import records, encode
        from research.test_radio_wp_guard import WPGuardTests
        original = (ROOT/'private/candidates/radio-apple-keyhole-profile/dynamic-section.bin').read_bytes()
        items = records(original)
        self.assertEqual(items[-1], (0xfe, b''))
        self.assertEqual(items[-2][0], 0x0b)
        items.insert(-2, (0x0a, struct.pack('<IH', 0x2007d2, 128)))
        baseline = WPGuardTests().run_case('ok', dynamic=original)[0]
        changed = WPGuardTests().run_case('ok', dynamic=encode(items))[0]
        old = bytes(baseline.mem_read(0x2007c8, 13))
        new = bytes(changed.mem_read(0x2007c8, 13))
        self.assertEqual(old[10:12], struct.pack('<H', 48))
        self.assertEqual(new, old[:10]+struct.pack('<H', 128)+old[12:])
        self.assertEqual(bytes(changed.mem_read(0x4aef8, 60)), bytes(baseline.mem_read(0x4aef8, 60)))


if __name__ == '__main__':
    unittest.main()
