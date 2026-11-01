"""Offline exact A89 runtime/header validation; no live interface access."""
import struct
import unittest
import radio_installer as r
import radio_keyboard_config_trial as k
import verify_radio_keyboard_config_trial as v

class Tests(unittest.TestCase):
    def fixture(self):
        plan=k.Plan();memory={}
        def store(address,data):
            for i,value in enumerate(data):memory[address+i]=value
        store(0x208f02,v.IDENTITY)
        store(0x209014,(r.ROOT/'private/candidates/radio-keyboard-config-profile/extension.bin').read_bytes())
        store(0x206aa8,bytes.fromhex('02f0d3fa'));store(0x208d30,struct.pack('<I',0x20914b))
        store(0x208ea8,struct.pack('<I',0x20c900));store(0x20c900,struct.pack('<I',0x20d800))
        store(0x20d800,struct.pack('<15I',*v.METHODS))
        store(0x20c914,b'\x57');store(0x20c906,bytes.fromhex('102030405060'))
        store(0x205e1c,struct.pack('<I',0x4000))
        store(0xff000000,b'\0'+plan.new_ss[1:]);store(0xff000100,plan.backup_ss)
        class IO:
            def read(self,address,n):return bytes(memory.get(address+i,0)for i in range(n))
            def set(self,*args):raise AssertionError('No firmware mutation')
        return IO(),plan,store
    def test_valid_runtime_and_recovery_headers(self):
        io,plan,_=self.fixture();result,address=v.verify(io,plan)
        self.assertTrue(result['A89_active']);self.assertEqual(result['battery_estimate'],87)
        self.assertEqual(address,bytes.fromhex('102030405060'))
        self.assertNotIn('address',result)
    def test_changed_getter_setter_code_bank_or_headers_reject(self):
        for address,data in [(0x208f04,b'\x87'),(0x209014,b'\0'),
                             (0x208d30,struct.pack('<I',0x206ad5)),(0x20d80c,b'\0'*4),
                             (0x205e1c,struct.pack('<I',0x8000)),(0xff000000,b'\1')]:
            io,plan,store=self.fixture();store(address,data)
            with self.assertRaises(ValueError):v.verify(io,plan)

if __name__=='__main__':unittest.main()
