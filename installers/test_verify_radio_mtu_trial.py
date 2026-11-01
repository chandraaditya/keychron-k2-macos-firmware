"""Offline exact A90 runtime/header validation; no live interface access."""
import struct
import unittest
import radio_installer as r
import radio_mtu_trial as k
import verify_radio_mtu_trial as v

class Tests(unittest.TestCase):
    def fixture(self):
        plan=k.Plan();memory={}
        def store(address,data):
            for i,value in enumerate(data):memory[address+i]=value
        store(0x208f02,v.IDENTITY)
        store(0x209014,(r.ROOT/'private/candidates/radio-control-mtu-profile/extension.bin').read_bytes())
        store(0x206aa8,bytes.fromhex('02f0d3fa'));store(0x208d30,struct.pack('<I',0x20914b))
        store(0x208ea8,struct.pack('<I',0x20c900));store(0x20c900,struct.pack('<I',0x20d800))
        store(0x20d800,struct.pack('<15I',*v.METHODS))
        store(0x20c914,b'\x57');store(0x20c906,bytes.fromhex('102030405060'))
        store(0x205e1c,struct.pack('<I',0x4000))
        store(0x2007d2,bytes.fromhex('8000'))
        store(0x200414,struct.pack('<I',0x20b000))
        store(0x20b044,struct.pack('<I',0x20b100))
        store(0x20b11c,struct.pack('<I',0x20b200))
        store(0x20b208,struct.pack('<I',0x20b300))
        store(0x20b30c,struct.pack('<H',0x41))
        store(0x2025d8,b'\1')
        store(0x2025d8+0x38,struct.pack('<HH',48,128))
        store(0xff000000,b'\0'+plan.new_ss[1:]);store(0xff000100,plan.backup_ss)
        class IO:
            def read(self,address,n):return bytes(memory.get(address+i,0)for i in range(n))
            def set(self,*args):raise AssertionError('No firmware mutation')
        return IO(),plan,store
    def test_valid_runtime_and_recovery_headers(self):
        io,plan,_=self.fixture();result,address=v.verify(io,plan)
        self.assertTrue(result['A90_active']);self.assertEqual(result['battery_estimate'],87)
        self.assertEqual(address,bytes.fromhex('102030405060'))
        self.assertNotIn('address',result)
    def test_unexpected_packet_cap_or_negotiation_rejects(self):
        for address,data in [(0x2007d2,bytes.fromhex('3000')),
                             (0x2025d8+0x38,struct.pack('<H',128)),
                             (0x2025d8+0x3a,struct.pack('<H',48)),
                             (0x20b30c,struct.pack('<H',0x7f))]:
            io,plan,store=self.fixture();store(address,data)
            with self.assertRaises(ValueError):v.verify(io,plan)
    def test_changed_getter_setter_code_bank_or_headers_reject(self):
        for address,data in [(0x208f04,b'\x87'),(0x209014,b'\0'),
                             (0x208d30,struct.pack('<I',0x206ad5)),(0x20d80c,b'\0'*4),
                             (0x205e1c,struct.pack('<I',0x8000)),(0xff000000,b'\1')]:
            io,plan,store=self.fixture();store(address,data)
            with self.assertRaises(ValueError):v.verify(io,plan)

if __name__=='__main__':unittest.main()
