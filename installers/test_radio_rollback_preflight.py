"""Offline guarded-A86 staging and interruption tests. No native HID opens."""
import struct
import unittest
import radio_installer as r
import radio_rollback_preflight as p
from verify_radio_rollback_preflight import verify
from test_radio_installer import MemoryDevice,MemoryJournal,selected

METHODS=(0x28a9,0x28dd,0x209141,0x209119,0x209145,0x2949,0x296d,
         0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=p.Plan()
    def make(self):
        dev=MemoryDevice(self.plan)
        dev.ram[0x8f02:0x8f10]=p.IDENTITY
        dev.ram[0x9014:0x9014+440]=(r.ROOT/'private/candidates/radio-battery-phase1/extension.bin').read_bytes()
        dev.ram[0x6aa8:0x6aac]=bytes.fromhex('02f0d3fa')
        dev.ram[0x8ea8:0x8eac]=struct.pack('<I',0x20c9d4)
        dev.ram[0xc9d4:0xc9d8]=struct.pack('<I',0x20d800)
        dev.ram[0xd800:0xd83c]=struct.pack('<15I',*METHODS)
        journal=MemoryJournal()
        return dev,journal,p.Runner(dev,self.plan,journal)
    def test_full_staging_preserves_active_and_original_banks_and_pairings(self):
        dev,journal,runner=self.make();runner.run()
        self.assertEqual(selected(dev.eeprom),0x4000)
        self.assertEqual(dev.eeprom[0x100:0x128],self.plan.backup_ss)
        self.assertEqual(dev.eeprom[0x8000:0xb7f2],self.plan.active)
        self.assertEqual(journal.saved,self.plan.baseline)
        for i,(a,b) in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(a,b)
    def test_every_completed_byte_cut_keeps_selectable_complete_bank(self):
        dev,_,runner=self.make();runner.run();state=bytearray(self.plan.baseline);count=0
        for frame in dev.calls:
            if frame[0]!=0x74:continue
            address,n=struct.unpack_from('<IH',frame,1);address-=0xff000000
            for i,value in enumerate(frame[7:-1]):
                state[address+i]=value;bank=selected(state)
                self.assertIn(bank,(0x8000,0x4000))
                if bank==0x4000:self.assertEqual(state[bank:bank+len(self.plan.candidate)],self.plan.candidate)
                count+=1
        self.assertEqual(count,len(self.plan.candidate)+82)
    def test_altered_context_or_storage_stops_before_enable(self):
        for offset in [0,0x100,0x4000,0x8000,0xf000]:
            dev,_,runner=self.make();dev.eeprom[offset]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[])
        for address in [0x208f04,0x209014,0x206aa8,0x20d800]:
            dev,_,runner=self.make();dev.ram[address-0x200000]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[])
    def test_lost_ack_is_never_retried(self):
        for after in [False,True]:
            dev,journal,runner=self.make();dev.after_write=after
            dev.fail=lambda f,d:len(d.calls)==4
            with self.assertRaises(OSError):runner.run()
            self.assertEqual(len(dev.calls),4)
            self.assertEqual(selected(dev.eeprom),0x8000)
    def test_rejected_fresh_capture_is_saved_before_comparison(self):
        dev,journal,runner=self.make();dev.eeprom[0xf074]^=1
        with self.assertRaises(ValueError):runner.run()
        self.assertEqual(journal.saved,bytes(dev.eeprom))
        self.assertEqual(journal.events[-1]['action'],'preflight-rejected')
        self.assertFalse(journal.events[-1]['update_enabled'])
        self.assertEqual(dev.calls,[])
    def test_further_slot_metadata_change_is_still_rejected(self):
        dev,journal,runner=self.make();dev.eeprom[0xf02b]^=1
        with self.assertRaises(ValueError):runner.run()
        self.assertEqual(journal.saved,bytes(dev.eeprom))
        self.assertEqual(dev.calls,[])
    def test_write_allowlist_preserves_active_original_and_vs(self):
        for offset in [0x28,0x128,0x1c0,0x3c0,0x8000,0xf000]:
            with self.assertRaises(ValueError):self.plan.write_frame(offset,b'x')
    def test_live_pairings_can_change_and_are_preserved(self):
        dev,journal,runner=self.make();dev.eeprom[0x250]^=7;before=bytes(dev.eeprom)
        runner.run();self.assertEqual(journal.saved,before)
        self.assertEqual(dev.eeprom[r.VS],before[r.VS])
    def test_default_native_capability_remains_disabled(self):
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)
        with self.assertRaises(ValueError):r.NativeHID(self.plan,write=True)
    def test_physical_verifier_distinguishes_trial_from_fallback(self):
        for stage,bank in [('trial',0x4000),('fallback',0x8000)]:
            dev,_,_=self.make()
            dev.eeprom[:40]=b'\0'+self.plan.new_ss[1:]
            dev.eeprom[0x100:0x128]=self.plan.backup_ss
            dev.ram[0x5e1c:0x5e20]=struct.pack('<I',bank)
            dev.ram[0xc9e8]=58
            self.assertTrue(verify(dev,self.plan,stage)['passed'])
            self.assertEqual(dev.calls,[])
            other='fallback' if stage=='trial' else 'trial'
            with self.assertRaises(ValueError):verify(dev,self.plan,other)
    def test_failed_header_check_still_reports_sanitized_state(self):
        dev,_,_=self.make();seen=[]
        dev.eeprom[:40]=self.plan.new_ss
        dev.eeprom[0x100:0x128]=self.plan.backup_ss
        dev.ram[0x5e1c:0x5e20]=struct.pack('<I',0x8000)
        with self.assertRaises(ValueError):verify(dev,self.plan,'trial',observer=seen.append)
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]['SS0_validity_byte'],1)
        self.assertTrue(seen[0]['SS0_matches_committed_trial'])
        self.assertEqual(seen[0]['running_DS'],0x8000)
        self.assertTrue(seen[0]['SS100_matches_working_A86_header'])
        self.assertNotIn('ss0',seen[0])

if __name__=='__main__':unittest.main()
