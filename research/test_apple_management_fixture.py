"""Offline stdlib tests; no host or hardware access."""
import unittest
from pathlib import Path
import apple_management_fixture as f

class FixtureTests(unittest.TestCase):
    def test_exact_observed_descriptor(self):
        self.assertEqual(len(f.DESCRIPTOR),83)
        self.assertEqual(f.DESCRIPTOR,(Path(__file__).resolve().parents[1]/'private/apple/trackpad-management-report-descriptor.bin').read_bytes())

    def test_all_percentages_and_declared_flags(self):
        for value in range(101):
            for flags in range(8):
                report=f.encode_battery(value,flags)
                self.assertEqual(report,bytes((0x90,flags,value)))
                self.assertEqual(f.decode_battery(report),{'percent':value,'status':flags})

    def test_invalid_battery(self):
        for value in (-1,101,256,True,1.5,'87'):
            with self.assertRaises(ValueError):f.encode_battery(value)
        for flags in (-1,8,16,255,True):
            with self.assertRaises(ValueError):f.encode_battery(87,flags)
        for report in (b'',b'\x90',b'\x90\0',b'\x90\0\x57\0',b'\x91\0\x57',b'\x90\0\x65',b'\x90\x80\x57'):
            with self.assertRaises(ValueError):f.decode_battery(report)

    def test_address_order_and_uint16(self):
        # Deliberately synthetic unicast address, not an owner's device.
        address=bytes.fromhex('021324354657')
        for firmware in (0,1,255,256,0x1234,65535):
            report=f.encode_bluetooth_info(address,firmware)
            self.assertEqual(len(report),77)
            self.assertEqual(report[:2],b'\x34\x03')
            self.assertEqual(report[4:10],address)
            parsed=f.decode_bluetooth_info(report)
            self.assertEqual(parsed['address'],address)
            self.assertEqual(parsed['firmware_version'],firmware)
            self.assertEqual(parsed['tail'],bytes(67))

    def test_invalid_bluetooth_info(self):
        good=f.encode_bluetooth_info(bytes(6))
        for length in range(78):
            if length!=77:
                with self.assertRaises(ValueError):f.decode_bluetooth_info((good+bytes(78))[:length])
        for version in (0,1,2,4,255,True):
            with self.assertRaises(ValueError):f.encode_bluetooth_info(bytes(6),version=version)
            if type(version) is int:
                with self.assertRaises(ValueError):f.decode_bluetooth_info(good[:1]+bytes((version,))+good[2:])
        for address in (b'',bytes(5),bytes(7),'00:00:00:00:00:00'):
            with self.assertRaises(ValueError):f.encode_bluetooth_info(address)
        for tail in (bytes(66),bytes(68)):
            with self.assertRaises(ValueError):f.encode_bluetooth_info(bytes(6),tail=tail)
        for firmware in (-1,65536,True):
            with self.assertRaises(ValueError):f.encode_bluetooth_info(bytes(6),firmware)

if __name__=='__main__':unittest.main(verbosity=2)
