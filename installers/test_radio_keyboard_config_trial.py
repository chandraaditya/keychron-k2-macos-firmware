"""Offline A88 raw-interface -> A89 staged-write checks; no HID opening."""
import struct
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_keyboard_config_trial as k
from test_radio_installer import MemoryDevice,MemoryJournal,selected

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=k.Plan()
    def setUp(self):
        p=patch.object(k,'maintenance_proof',lambda:None);p.start();self.addCleanup(p.stop)
    def make(self):
        dev=MemoryDevice(self.plan)
        dev.ram[0x8f02:0x8f10]=k.A88_IDENTITY
        dev.ram[0x9014:0x9014+816]=(r.ROOT/'private/candidates/radio-apple-keyhole-profile/extension.bin').read_bytes()
        dev.ram[0x6aa8:0x6aac]=bytes.fromhex('02f0d3fa')
        dev.ram[0x8d30:0x8d34]=struct.pack('<I',0x20914b)
        dev.ram[0x8ea8:0x8eac]=struct.pack('<I',0x20c9d4)
        dev.ram[0xc9d4:0xc9d8]=struct.pack('<I',0x20d800)
        dev.ram[0xd800:0xd83c]=struct.pack('<15I',*k.A88_METHODS)
        dev.ram[0x5e1c:0x5e20]=struct.pack('<I',0x4000)
        journal=MemoryJournal();return dev,journal,k.Runner(dev,self.plan,journal)
    def test_complete_staging_preserves_every_protected_byte(self):
        dev,journal,runner=self.make();runner.run()
        self.assertTrue(runner.committed);self.assertEqual(selected(dev.eeprom),0x4000)
        self.assertEqual(journal.saved,self.plan.baseline)
        for i,(old,new)in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(old,new)
    def test_completed_byte_cuts_select_backup_until_final_commit(self):
        dev,_,runner=self.make();runner.run();state=bytearray(self.plan.baseline);count=0
        for f in dev.calls:
            if f[0]!=0x74:continue
            address,n=struct.unpack_from('<IH',f,1);address-=0xff000000
            for i,value in enumerate(f[7:-1]):
                state[address+i]=value;count+=1
                if count<len(self.plan.candidate)+1:self.assertEqual(selected(state),0x8000)
                else:self.assertEqual(state[0x4000:0x4000+len(self.plan.candidate)],self.plan.candidate)
        self.assertEqual(count,16104)
    def test_changed_storage_or_runtime_saves_and_rejects_without_enable(self):
        for offset in [0,0x100,0x4000,0x8000,0xf002]:
            dev,journal,runner=self.make();dev.eeprom[offset]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[]);self.assertEqual(journal.saved,bytes(dev.eeprom))
        for address in [0x208f04,0x209014,0x208d30,0x20d80c]:
            dev,journal,runner=self.make();dev.ram[address-0x200000]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[])
    def test_failed_reports_are_never_retried(self):
        complete,_,runner=self.make();runner.run()
        for index in [1,2,3,len(complete.calls)]:
            for after in [False,True]:
                dev,journal,runner=self.make();dev.after_write=after
                dev.fail=lambda f,d:len(d.calls)==index
                with self.assertRaises(OSError):runner.run()
                self.assertEqual(len(dev.calls),index)
                self.assertEqual(dev.eeprom[0x100:0x128],self.plan.backup_ss)
    def test_physical_and_raw_proofs_required_before_open_or_enable(self):
        dev,journal,runner=self.make()
        with patch.object(k,'maintenance_proof',side_effect=ValueError('missing proof')):
            with self.assertRaises(ValueError):runner.run()
            with self.assertRaises(ValueError):k.runtime_view().load_plan()
        self.assertEqual(dev.calls,[]);self.assertIsNone(journal.saved)
    def test_live_VS_preserved_but_no_other_mutable_mask_expansion(self):
        dev,journal,runner=self.make();dev.eeprom[0x250]^=1;before=bytes(dev.eeprom)
        runner.run();self.assertEqual(dev.eeprom[r.VS],before[r.VS])
        for address in [1,0x100,0x1c0,0x3c0,0x8000,0xf000]:
            with self.assertRaises(ValueError):self.plan.write_frame(address,b'x')
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)

if __name__=='__main__':unittest.main()
