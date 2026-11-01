"""Offline A87 runtime/driver association checks; no native device opening."""
import ctypes as C
import struct
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_apple_trial as a
import verify_radio_apple_trial as v

class Tests(unittest.TestCase):
    def device(self):
        plan=a.Plan();memory={}
        def store(address,data):
            for i,value in enumerate(data):memory[address+i]=value
        store(0x208f02,v.IDENTITY)
        store(0x209014,(r.ROOT/'private/candidates/radio-apple-wp-profile/extension.bin').read_bytes())
        store(0x206aa8,bytes.fromhex('02f0d3fa'))
        store(0x208ea8,struct.pack('<I',0x20c900));store(0x20c900,struct.pack('<I',0x20d800))
        store(0x20d800,struct.pack('<15I',*v.METHODS))
        store(0x20c914,b'\x4e');store(0x20c906,bytes.fromhex('102030405060'))
        store(0x205e1c,struct.pack('<I',0x4000))
        store(0xff000000,b'\0'+plan.new_ss[1:]);store(0xff000100,plan.backup_ss)
        class IO:
            def read(self,address,n):return bytes(memory.get(address+i,0) for i in range(n))
            def set(self,*args):raise AssertionError('No mutation allowed')
        return IO(),plan,store
    def test_exact_runtime_and_rollback_state_pass(self):
        io,plan,_=self.device();result,address=v.verify(io,plan)
        self.assertTrue(result['A87_active']);self.assertTrue(result['trial_SS0_invalidated'])
        self.assertEqual(result['battery_estimate'],78)
        self.assertEqual(address,bytes.fromhex('102030405060'))
        self.assertNotIn('address',result)
    def test_runtime_corruption_and_wrong_bank_reject(self):
        for address,data in [(0x208f04,b'\x86'),(0x209014,b'\0'),
                             (0x20d808,b'\0'*4),(0x205e1c,struct.pack('<I',0x8000)),
                             (0xff000000,b'\1')]:
            io,plan,store=self.device();store(address,data)
            with self.assertRaises(ValueError):v.verify(io,plan)
    def test_native_service_association_requires_exact_address(self):
        address=bytes.fromhex('102030405060')
        tree=[{'IOObjectClass':'AppleDeviceManagementHIDEventService','BD_ADDR':bytes(6),'BatteryPercent':99},
              {'IOObjectClass':'AppleDeviceManagementHIDEventService','BD_ADDR':address,'BatteryPercent':78,'BatteryStatusFlags':0}]
        rows=v.native_battery_services(address,tree)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['battery_percent'],78)
        self.assertNotIn('BD_ADDR',rows[0])
    def test_firmware_SDP_and_pairing_slot_are_verified_without_identity_output(self):
        io,plan,store=self.device()
        store(0x202c6c,struct.pack('<III',0x762c,1053,0x20d000))
        store(0x20d000,(r.ROOT/'private/apple-profile/grouped-sdp.bin').read_bytes())
        store(0xff00f000,b'\x01')
        result=v.radio_profile(io)
        self.assertTrue(result['firmware_SDP_override_verified'])
        self.assertEqual(result['active_pairing_slot'],2)
        store(0x202c74,struct.pack('<I',0x329000))
        self.assertFalse(v.radio_profile(io)['firmware_SDP_override_verified'])
    def test_native_GET_types_lengths_and_failure(self):
        class IO:
            device=None
            failed=False
            def _before_request(self):
                if self.failed:raise RuntimeError('failed')
        io=IO();calls=[]
        def receive(device,kind,rid,buffer,length):
            calls.append((kind,rid,length._obj.value))
            packet=bytes([rid])+bytes(length._obj.value-1)
            C.memmove(buffer,packet,len(packet));return 0
        io.get_report=receive
        with patch.object(v.signal,'alarm',lambda n:None):
            self.assertEqual(len(v.get_report(io,0,0x90,3)),3)
            self.assertEqual(len(v.get_report(io,2,0x34,77)),77)
            self.assertEqual(calls,[(0,0x90,3),(2,0x34,77)])
            io.get_report=lambda *args:0xe00002e2
            with self.assertRaises(ValueError):v.get_report(io,0,0x90,3)
            self.assertTrue(io.failed)

if __name__=='__main__':unittest.main()
