"""Offline rejected-capture preservation and partial-read diagnosis tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_rollback_preflight as p
import diagnose_radio_preflight as d

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=p.Plan()
    def test_region_classification_keeps_metadata_outside_vs(self):
        fresh=bytearray(self.plan.baseline)
        fresh[0x200]^=1;fresh[0xf074]^=1
        result,blocks=d.analyze(self.plan.baseline,fresh)
        self.assertEqual(result['changed_bytes'],2)
        self.assertEqual(result['outside_pairing_changed_bytes'],1)
        self.assertEqual(blocks,[0xf060])
        self.assertTrue(result['active_A86_DS_matches'])
    def device(self,fresh,fail_reread=False):
        plan=self.plan
        class Device:
            def __init__(self):self.requests=[]
            def read(self,address,n):
                self.requests.append((address,n))
                if (address,n)==(0xff000000,65536):return fresh
                if fail_reread:raise RuntimeError('read failed')
                if n!=16:raise AssertionError('Expected independent16-byte reread')
                offset=address-0xff000000
                return plan.baseline[offset:offset+n]
            def set(self,*args):raise AssertionError('No update/set call is permitted')
        return Device()
    def test_partial_aa_tail_is_saved_then_independently_rechecked(self):
        fresh=bytearray(self.plan.baseline);a=0x8040
        fresh[a+16:a+32]=b'\xaa'*16
        dev=self.device(bytes(fresh))
        with tempfile.TemporaryDirectory()as name,patch.object(p,'guard_context',lambda io:None):
            folder=Path(name);result=d.capture(dev,self.plan,folder)
            self.assertEqual((folder/'eeprom-first.bin').read_bytes(),fresh)
            self.assertEqual((folder/'eeprom-first.bin').stat().st_mode&0o777,0o600)
            self.assertEqual(result['suspected_second_half_AA_reads'],[hex(a)])
            self.assertTrue(result['all_changed_blocks_returned_to_baseline'])
            self.assertFalse(result['all_changed_blocks_stable'])
            self.assertEqual(dev.requests[-2:],[(0xff000000+a,16),(0xff000000+a+16,16)])
    def test_reread_failure_keeps_first_capture_and_comparison(self):
        fresh=bytearray(self.plan.baseline);fresh[0xf074]^=1
        dev=self.device(bytes(fresh),fail_reread=True)
        with tempfile.TemporaryDirectory()as name,patch.object(p,'guard_context',lambda io:None):
            folder=Path(name)
            with self.assertRaises(RuntimeError):d.capture(dev,self.plan,folder)
            self.assertEqual((folder/'eeprom-first.bin').read_bytes(),fresh)
            self.assertTrue((folder/'first-comparison.json').exists())
            self.assertTrue((folder/'result.json').exists())
    def test_default_hardware_gate_is_disabled(self):
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)

if __name__=='__main__':unittest.main()
