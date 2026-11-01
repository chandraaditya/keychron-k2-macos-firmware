"""Offline Apple trial gating, exact staged writes and interruption tests."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_wp_trial as wp
import radio_apple_trial as a
from test_radio_installer import selected
import test_radio_wp_trial as neutral_fixture

PROOF_CHECK=a.physical_recovery_verified

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=a.Plan()
    def setUp(self):
        mock=patch.object(a,'physical_recovery_verified',lambda:None)
        mock.start();self.addCleanup(mock.stop)
    def make(self):
        fixture=neutral_fixture.Tests();fixture.plan=self.plan
        dev,journal,_=fixture.make()
        return dev,journal,a.Runner(dev,self.plan,journal)
    def test_complete_Apple_staging_retains_all_protected_bytes(self):
        dev,journal,runner=self.make();runner.run()
        self.assertTrue(runner.committed);self.assertEqual(selected(dev.eeprom),0x4000)
        self.assertEqual(journal.saved,self.plan.baseline)
        self.assertEqual(dev.eeprom[0x4000:0x4000+len(self.plan.candidate)],self.plan.candidate)
        for i,(old,new) in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(old,new)
    def test_every_completed_byte_cut_selects_backup_until_final_commit(self):
        dev,_,runner=self.make();runner.run();state=bytearray(self.plan.baseline);count=0
        writes=[f for f in dev.calls if f[0]==0x74]
        for f in writes:
            offset,n=struct.unpack_from('<IH',f,1);offset-=0xff000000
            for i,value in enumerate(f[7:-1]):
                state[offset+i]=value;count+=1
                bank=selected(state);self.assertIn(bank,(0x8000,0x4000))
                if count<len(self.plan.candidate)+1:self.assertEqual(bank,0x8000)
                if bank==0x4000:self.assertEqual(state[bank:bank+len(self.plan.candidate)],self.plan.candidate)
        self.assertEqual(count,len(self.plan.candidate)+1)
    def test_missing_physical_acceptance_stops_before_enable(self):
        dev,journal,runner=self.make()
        with patch.object(a,'physical_recovery_verified',side_effect=ValueError('missing proof')):
            with self.assertRaises(ValueError):runner.run()
            with self.assertRaises(ValueError):a.runtime_view().load_plan()
        self.assertEqual(dev.calls,[]);self.assertIsNone(journal.saved)
    def test_exact_physical_acceptance_requires_both_stages(self):
        with tempfile.TemporaryDirectory()as name,patch.object(r,'ROOT',Path(name)):
            folder=Path(name)/'artifacts/k2-initial-release';folder.mkdir(parents=True)
            with self.assertRaises(ValueError):PROOF_CHECK()
            for stage,bank in [('trial',0x4000),('fallback',0x8000)]:
                data={'passed':True,'corrected_WP_trial':True,'candidate_DS_sha256':wp.EXPECTED_CANDIDATE_SHA,
                      'stage':stage,'running_DS':bank,'trial_SS0_invalidated':True,
                      'backup_SS100_selects_A86':True,'working_A86_extension_and_methods_verified':True}
                (folder/f'radio-wp-{stage}-verification.json').write_text(json.dumps(data))
            PROOF_CHECK()
            data['running_DS']=0x4000
            (folder/'radio-wp-fallback-verification.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):PROOF_CHECK()
    def test_unexpected_headers_firmware_or_settings_stop_and_save(self):
        for offset in [0,0x100,0x4000,0x8000,0xf02b]:
            dev,journal,runner=self.make();dev.eeprom[offset]^=1
            with self.assertRaises(ValueError):runner.run()
            self.assertEqual(dev.calls,[]);self.assertEqual(journal.saved,bytes(dev.eeprom))
    def test_failed_writes_are_not_retried(self):
        complete,_,runner=self.make();runner.run()
        for index in [1,2,3,len(complete.calls)]:
            for after in [False,True]:
                dev,journal,runner=self.make();dev.after_write=after
                dev.fail=lambda f,d:len(d.calls)==index
                with self.assertRaises(OSError):runner.run()
                self.assertEqual(len(dev.calls),index)
                self.assertEqual(dev.eeprom[0x100:0x128],self.plan.backup_ss)
    def test_forbidden_writes_and_default_capability(self):
        for offset in [1,0x100,0x1c0,0x3c0,0x8000,0xf000]:
            with self.assertRaises(ValueError):self.plan.write_frame(offset,b'x')
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)

if __name__=='__main__':unittest.main()
