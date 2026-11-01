"""Complete existing34 response fails at48 and succeeds at128. No device API."""
import struct
import unittest
from research.test_radio_keyboard_full_hidp import FullHIDPTests
from research.test_radio_apple_component import TRANS, word


class MTUFullHIDPTests(FullHIDPTests):
    def test_long_management_reply_drop_then_success_at_new_channel_cap(self):
        u = self.f.u
        child = word(u, TRANS + 0x1c)
        control = word(u, child + 8)
        cid = int.from_bytes(u.mem_read(control + 0xc, 2), 'little')
        self.assertTrue(0x40 <= cid <= 0x4b)
        channel = 0x20255c + (cid - 0x40) * 0x7c
        self.assertEqual(bytes(u.mem_read(channel + 0x3a, 2)), b'\x30\x00')
        self.packet(bytes.fromhex('53 ff 34'))
        self.packet(bytes.fromhex('4b f0 4e 00'))
        self.assertEqual(self.sent, [])
        u.mem_write(channel + 0x3a, struct.pack('<H', 128))
        self.packet(bytes.fromhex('4b f0 4e 00'))
        expected = bytes.fromhex('a3 f0 34 03 00 00 10 20 30 40 50 60') + bytes(67)
        self.assertEqual(len(expected), 79)
        self.assertEqual(self.sent, [expected])


if __name__ == '__main__':
    unittest.main()
