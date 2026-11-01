"""A94: the host's first F1 keyboard-configuration read re-arms SS0 byte 0.

Full HIDP path as in A89-A93. The real ROM EEPROM reader 2C97A, writer 2C9B2,
ACK poll and write-protect callback 17541 execute; only the synchronous I2C
transfer 2C846 is modeled, over the real pre-A92 64 KiB backup (its SS0/SS100
headers are compared, never printed). Physical write protection is modeled
from the radio GPIO the callback drives. No device access.
Run with K2_COMPONENT=firmware/radio_keyboard_rearm_component.S and A93's K2_FEATURE2.
"""
import os
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research.test_radio_keyboard_full_hidp import FullHIDPTests
from research.test_radio_apple_component import ROOT, SHADOW, STACK, put, word

A92_JOURNAL = ROOT / 'private/update-sessions/radio-1793184566954073000.jsonl'
FLAG = SHADOW + 151


def installed_layout():
    """Pre-A92-install EEPROM: SS0 invalid trial header, SS100 valid A86 header."""
    eeprom = bytearray(A92_JOURNAL.with_suffix('.eeprom.bin').read_bytes())
    assert len(eeprom) == 65536 and eeprom[0] == 0 and eeprom[0x100] == 1
    return eeprom


class RearmTests(FullHIDPTests):
    def setUp(self):
        super().setUp()
        u = self.f.u
        u.mem_map(0x390000, 0x1000)
        put(u, 0x390280, 0)
        put(u, 0x390118, 1)       # WP held high by the external pull-up.
        put(u, 0x205e1c, 0x4000)
        self.assertEqual(bytes(u.mem_read(0x200a02, 1)), b'\x40')
        self.assertEqual(word(u, 0x200a18), 0x17541)
        self.eeprom = installed_layout()
        self.original = bytes(self.eeprom)
        self.events = []
        self.wp_calls = []
        self.fault = None
        self.min_sp = STACK

        def hook(cpu, a, n, d):
            sp = cpu.reg_read(r.UC_ARM_REG_SP)
            self.min_sp = min(self.min_sp, sp)
            if a == 0x17540:
                self.wp_calls.append(cpu.reg_read(r.UC_ARM_REG_R0))
            if a != 0x2c846:
                return
            buf, n, address, alen = (cpu.reg_read(x) for x in
                                     (r.UC_ARM_REG_R0, r.UC_ARM_REG_R1, r.UC_ARM_REG_R2, r.UC_ARM_REG_R3))
            self.assertEqual(word(cpu, sp), 0xa0)
            write = word(cpu, sp + 4)
            status = 1
            if alen == 0:
                self.events.append(('ack',))
            else:
                self.assertEqual(alen, 2)
                at = int.from_bytes(cpu.mem_read(address, 2), 'big')
                if write:
                    data = bytes(cpu.mem_read(buf, n))
                    low = bool(word(cpu, 0x390280) & 0x4000) and not word(cpu, 0x390118) & 1
                    self.events.append(('write', at, data, low))
                    if self.fault == 'write':
                        status = 6
                    elif low and self.fault != 'protected':
                        self.eeprom[at:at + n] = data
                else:
                    self.events.append(('read', at, n))
                    if self.fault == 'read':
                        status = 6
                    else:
                        cpu.mem_write(buf, bytes(self.eeprom[at:at + n]))
            cpu.reg_write(r.UC_ARM_REG_R0, status)
            cpu.reg_write(r.UC_ARM_REG_PC, cpu.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE, hook)

    def logical(self):
        return bytes.fromhex(os.environ.get('K2_FEATURE2', '02 01 01 00 00 0a 0d 0b 0e 0c 0f'))

    def keyboard_configuration(self):
        self.packet(bytes.fromhex('53 c6 01 18 01 20'))
        self.packet(bytes.fromhex('53 ff 02'))
        self.assertEqual(self.events, [])
        self.packet(bytes.fromhex('4b f1 00 02'))
        self.assertEqual(self.sent[-1], b'\xa3\xf1' + self.logical())
        return bytes(self.f.u.mem_read(FLAG, 1))[0]

    def changed(self):
        return [i for i, (a, b) in enumerate(zip(self.original, self.eeprom)) if a != b]

    def test_first_F1_read_rearms_exactly_one_byte_once(self):
        self.assertEqual(self.keyboard_configuration(), 2)
        self.assertEqual(self.changed(), [0])
        self.assertEqual(self.eeprom[0], 1)
        writes = [e for e in self.events if e[0] == 'write']
        self.assertEqual(writes, [('write', 0, b'\x01', True)])
        self.assertEqual([e for e in self.events if e[0] == 'read'],
                         [('read', 0, 40), ('read', 0x100, 40), ('read', 0, 1)])
        self.assertEqual(self.wp_calls, [0, 1])
        self.assertEqual(self.eeprom[:40], b'\1' + self.original[1:40])
        self.assertEqual(self.handshakes, [0, 0])
        self.assertGreater(self.min_sp, STACK - 0x400)
        count = len(self.events)
        self.packet(bytes.fromhex('4b f1 00 02'))
        self.assertEqual(self.sent[-1], b'\xa3\xf1' + self.logical())
        self.assertEqual(len(self.events), count)

    def test_other_requests_never_touch_EEPROM(self):
        self.packet(bytes.fromhex('43 02'))
        self.packet(bytes.fromhex('53 ff 90'))
        self.packet(bytes.fromhex('41 f0'))
        self.packet(bytes.fromhex('53 ff 34'))
        self.packet(bytes.fromhex('4b f0 00 4e'))
        self.packet(bytes.fromhex('4b f1 00 02'))   # Wrong selection: F1 rejected.
        self.assertEqual(self.events, [])
        self.assertEqual(bytes(self.f.u.mem_read(FLAG, 1)), b'\0')

    def test_declines_any_layout_it_did_not_install(self):
        cases = {'running_from_8000': None, 'already_valid': (0, 1),
                 'backup_invalid': (0x100, 0), 'header_byte': (5, None),
                 'trial_DS_not_4000': (31, 0x50), 'backup_DS_not_8000': (0x11f, 0x40),
                 'trial_DS_high_byte': (32, 1)}
        for name, change in cases.items():
            with self.subTest(name=name):
                self.setUp()
                if change is None:
                    put(self.f.u, 0x205e1c, 0x8000)
                else:
                    at, value = change
                    self.eeprom[at] = self.eeprom[at] ^ 0xff if value is None else value
                    self.original = bytes(self.eeprom)
                self.assertEqual(self.keyboard_configuration(), 1)
                self.assertEqual(self.changed(), [])
                self.assertEqual([e for e in self.events if e[0] == 'write'], [])
                self.assertEqual(self.wp_calls, [])

    def test_read_failure_declines_without_write(self):
        self.fault = 'read'
        self.assertEqual(self.keyboard_configuration(), 1)
        self.assertEqual(self.events, [('read', 0, 40)])
        self.assertEqual(self.changed(), [])

    def test_failed_or_protected_write_is_reported_and_not_retried(self):
        for mode in ['write', 'protected']:
            with self.subTest(mode=mode):
                self.setUp()
                self.fault = mode
                self.assertEqual(self.keyboard_configuration(), 3)
                self.assertEqual(self.changed(), [])
                self.assertEqual(self.wp_calls, [0, 1])
                count = len(self.events)
                self.packet(bytes.fromhex('4b f1 00 02'))
                self.assertEqual(self.sent[-1], b'\xa3\xf1' + self.logical())
                self.assertEqual(len(self.events), count)

    def test_without_write_protect_callback_the_write_cannot_land(self):
        put(self.f.u, 0x200a18, 0)
        self.assertEqual(self.keyboard_configuration(), 3)
        self.assertEqual(self.changed(), [])
        self.assertEqual(self.wp_calls, [])


if __name__ == '__main__':
    unittest.main()
