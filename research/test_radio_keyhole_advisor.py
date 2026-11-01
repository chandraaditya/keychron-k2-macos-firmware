"""Independent A88 integration check from complete HIDP SET packets.

Runs ROM14482 and the emitted component. Activity notification, handshake
transmission and packet freeing are modeled. No device access or image writes.
"""
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research.test_radio_keyhole_component import KeyholeComponentTests
from research.test_radio_apple_component import APP, TRANS, TABLE, SHADOW, put


class WireSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        KeyholeComponentTests.setUpClass()

    def setUp(self):
        self.fixture = KeyholeComponentTests('test_Apple_identity_and_battery_keyhole_framing')
        self.fixture.setUp()
        u = self.fixture.u
        put(u, APP, 0x208d04)
        put(u, TRANS+8, APP)
        put(u, TABLE+0x68, 0x70301)
        self.handshakes = []
        def hook(cpu, address, size, unused):
            if address == 0x14446:
                self.handshakes.append(cpu.reg_read(r.UC_ARM_REG_R2))
            elif address not in (0x70300, 0x71fc):
                return
            cpu.reg_write(r.UC_ARM_REG_PC, cpu.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE, hook)

    def send(self, packet):
        address = 0x20de00
        header = b'\0\0' + len(packet).to_bytes(2, 'little') + bytes(4)
        self.fixture.u.mem_write(address, header+packet)
        self.fixture.call(0x14482, (TRANS, address, 0, 0))
        return self.handshakes[-1]

    def test_complete_feature_selector_frames_reach_hook_and_reply(self):
        self.assertEqual(self.send(bytes.fromhex('53 ff 34')), 0)
        self.assertEqual(self.fixture.get(3, 0xf0)[1][:5], bytes.fromhex('f0 34 03 00 00'))
        self.assertEqual(len(self.fixture.get(3, 0xf0)[1]), 78)
        self.assertEqual(self.send(bytes.fromhex('53 ff 90')), 0)
        self.assertEqual(self.fixture.get(1, 0xf0), (0, bytes.fromhex('f0 90 00 3a')))

    def test_unsupported_selector_invalidates_then_hidp_handshake_rejects(self):
        self.send(bytes.fromhex('53 ff 34'))
        self.assertEqual(self.send(bytes.fromhex('53 ff bb')), 2)
        self.assertEqual(self.fixture.u.mem_read(SHADOW+150, 1), b'\0')
        self.assertEqual(self.fixture.get(3, 0xf0), (2, b''))

    def test_other_types_and_lengths_keep_original_hidp_rejection(self):
        for packet in ['51 ff 34', '52 ff 34', '53 ff', '53 ff 34 00']:
            self.assertEqual(self.send(bytes.fromhex(packet)), 2)


if __name__ == '__main__':
    unittest.main()
