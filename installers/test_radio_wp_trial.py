"""Offline exact predecessor, interrupted staging and retained recovery tests."""
import struct
import unittest
import radio_installer as r
import radio_rollback_preflight as old
import radio_wp_trial as wp
from test_radio_installer import MemoryDevice,MemoryJournal,selected

METHODS=(0x28a9,0x28dd,0x209141,0x209119,0x209145,0x2949,0x296d,
         0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=wp.Plan();cls.old=old.Plan()
    def make(self):
        dev=MemoryDevice(self.plan)
        dev.ram[0x8f02:0x8f10]=old.IDENTITY
        dev.ram[0x9014:0x9014+440]=(r.ROOT/'private/candidates/radio-battery-phase1/extension.bin').read_bytes()
        dev.ram[0x6aa8:0x6aac]=bytes.fromhex('02f0d3fa')
        dev.ram[0x8ea8:0x8eac]=struct.pack('<I',0x20c9d4)
        dev.ram[0xc9d4:0xc9d8]=struct.pack('<I',0x20d800)
        dev.ram[0xd800:0xd83c]=struct.pack('<15I',*METHODS)
        dev.ram[0x5e1c:0x5e20]=struct.pack('<I',0x8000)
        journal=MemoryJournal();return dev,journal,wp.Runner(dev,self.plan,journal)
    def test_complete_staging_retains_all_other_bytes_and_banks(self):
        dev,journal,runner=self.make();runner.run()
        self.assertTrue(runner.committed);self.assertEqual(selected(dev.eeprom),0x4000)
        self.assertEqual(dev.eeprom[0x100:0x128],self.plan.backup_ss)
        self.assertEqual(dev.eeprom[0x8000:0xb7f2],self.plan.active)
        self.assertEqual(dev.eeprom[0x4000:0x4000+len(self.plan.candidate)],self.plan.candidate)
        self.assertEqual(journal.saved,self.plan.baseline)
        for i,(a,b) in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(a,b)
        writes=[frame for frame in dev.calls if frame[0]==0x74]
        self.assertEqual(struct.unpack_from('<I',writes[0],1)[0],0xff000000)
        self.assertEqual(writes[0][7:-1],b'\0')
    def test_every_completed_byte_cut_has_complete_selected_bank(self):
        dev,_,runner=self.make();runner.run();state=bytearray(self.plan.baseline);cuts=0
        for frame in dev.calls:
            if frame[0]!=0x74:continue
            address,n=struct.unpack_from('<IH',frame,1);address-=0xff000000
            for i,value in enumerate(frame[7:-1]):
                state[address+i]=value;bank=selected(state)
                self.assertIn(bank,(0x8000,0x4000))
                if bank==0x4000:self.assertEqual(state[bank:bank+len(self.plan.candidate)],self.plan.candidate)
                cuts+=1
        self.assertEqual(cuts,len(self.plan.candidate)+2)
    def test_predecessor_or_runtime_mismatch_saves_and_stops_before_enable(self):
        for offset in [0,0x100,0x4000,0x8000,0xf02b]:
            dev,journal,runner=self.make();dev.eeprom[offset]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[]);self.assertEqual(journal.saved,bytes(dev.eeprom))
        dev,journal,runner=self.make();dev.ram[0x5e1d]^=1
        with self.assertRaises(ValueError):runner.run()
        self.assertEqual(dev.calls,[])
    def test_lost_ack_stops_without_retry_on_invalidation_and_commit(self):
        complete,_,runner=self.make();runner.run()
        for index in [1,2,3,len(complete.calls)]:
            for after in [False,True]:
                dev,journal,runner=self.make();dev.after_write=after
                dev.fail=lambda frame,d:len(d.calls)==index
                with self.assertRaises(OSError):runner.run()
                self.assertEqual(len(dev.calls),index)
                self.assertIn(selected(dev.eeprom),(0x4000,0x8000))
                self.assertEqual(dev.eeprom[0x100:0x128],self.plan.backup_ss)
                self.assertEqual(dev.eeprom[0x8000:0xb7f2],self.plan.active)
    def test_no_backup_header_body_or_settings_writes_allowed(self):
        for offset in [1,0x100,0x1c0,0x3c0,0x8000,0xf000,0xf074]:
            with self.assertRaises(ValueError):self.plan.write_frame(offset,b'x')
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)
    def test_changed_live_VS_is_preserved(self):
        dev,journal,runner=self.make();dev.eeprom[0x250]^=1;before=bytes(dev.eeprom)
        runner.run();self.assertEqual(journal.saved,before)
        self.assertEqual(dev.eeprom[r.VS],before[r.VS])

if __name__=='__main__':unittest.main()
