"""A89's additional configuration protocol through real root GET/SET.

Inherits A88 battery, updater, allocator and report-regression checks.
No peripheral access.
"""
import os
import struct
import unittest
from research.test_radio_keyhole_component import KeyholeComponentTests
from research.test_radio_apple_component import ROOT, BASE
from build_radio_candidate import assemble


class KeyboardConfigurationTests(KeyholeComponentTests):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.syms = assemble(ROOT / os.environ.get('K2_COMPONENT', 'firmware/radio_keyboard_config_component.S'))
        for slot, target in [('address_getter', 'get_report'), ('address_notify', 'notify'),
                             ('address_connect', 'connected'), ('address_setter', 'root_set_report')]:
            struct.pack_into('<I', cls.code, cls.syms[slot], BASE + cls.syms[target] | 1)

    def test_every_selector_and_invalid_selection_clears_prior_state(self):
        for selector in range(256):
            self.assertEqual(self.select(0x34), 0)
            status = self.select(selector)
            if selector in (2, 0x34, 0x90):
                self.assertEqual(status, 0)
            else:
                self.assertEqual(status, 2)
                for kind, rid in [(1, 0xf0), (3, 0xf0), (3, 0xf1)]:
                    self.assertEqual(self.get(kind, rid), (2, b''))

    def test_direct_configuration_and_actual_Apple_keyhole_framing(self):
        expected = bytes.fromhex(os.environ.get('K2_FEATURE2', '02010100000a0d0b0e0c0f'))
        self.assertEqual(self.get(3, 2), (0, expected))
        self.assertEqual(self.select(2), 0)
        self.assertEqual(self.get(3, 0xf1), (0, b'\xf1' + expected))
        self.assertEqual(self.get(3, 0xf1, 5), (0, b'\xf1' + expected[:4]))

    def test_keyboard_and_management_keyholes_do_not_leak_other_selection(self):
        self.assertEqual(self.get(3, 0xf1), (2, b''))
        self.select(2)
        for kind, rid in [(1, 0xf1), (2, 0xf1), (1, 0xf0), (3, 0xf0)]:
            self.assertEqual(self.get(kind, rid), (2, b''))
        for selector in (0x34, 0x90):
            self.select(selector)
            self.assertEqual(self.get(3, 0xf1), (2, b''))


if __name__ == '__main__':
    unittest.main()
