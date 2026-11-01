"""Offline A85->A86 transaction tests; no native hardware opening."""
import json
from pathlib import Path
import struct
import unittest

import radio_installer as r
import radio_phase1_installer as p2
from test_radio_installer import MemoryDevice,MemoryJournal,selected


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=p2.Plan()
    def make(self):
        dev=MemoryDevice(self.plan);dev.ram[0x8f02:0x8f10]=p2.IDENTITY
        journal=MemoryJournal();return dev,journal,p2.Runner(dev,self.plan,journal)
    def test_full_repair_preserves_all_previous_banks_and_pairings(self):
        dev,journal,runner=self.make();runner.run()
        self.assertTrue(runner.committed);self.assertEqual(selected(dev.eeprom),0x8000)
        self.assertEqual(dev.eeprom[0x8000:0xb7f2],self.plan.candidate)
        self.assertEqual(dev.eeprom[0x100:0x128],self.plan.old_ss)
        for i,(old,new)in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(old,new)
        self.assertEqual(journal.saved,self.plan.baseline)
        for frame in dev.calls:
            if frame[0]==0x74:
                address,n=struct.unpack_from('<IH',frame,1)
                self.assertTrue(address<0xff000028 or address>=0xff008000)
    def test_modified_live_pairings_preserved(self):
        dev,journal,runner=self.make();dev.eeprom[0x250]^=7;fresh=bytes(dev.eeprom);runner.run()
        self.assertEqual(journal.saved,fresh);self.assertEqual(dev.eeprom[r.VS],fresh[r.VS])
    def test_active_or_backup_corruption_blocks_enable(self):
        for offset in (0,30,0x100,0x3c0,0x4000,0x8000,0xf000):
            with self.subTest(offset=offset):
                dev,journal,runner=self.make();dev.eeprom[offset]^=1
                with self.assertRaises(ValueError):runner.run()
                self.assertEqual(dev.calls,[])
    def test_wrong_current_identity_or_arena_or_methods_blocks_enable(self):
        ptr=int.from_bytes(r.RAM.read_bytes()[0x8ea8:0x8eac],'little')
        for address in (0x208f04,0x206aa8,0x201350,ptr):
            with self.subTest(address=address):
                dev,journal,runner=self.make();dev.ram[address-0x200000]^=1
                with self.assertRaises(ValueError):runner.run()
                self.assertEqual(dev.calls,[])
    def test_failure_before_and_after_ack_selects_complete_known_bank(self):
        complete,_,runner=self.make();runner.run()
        indices={1,2,3,len(complete.calls)-1,len(complete.calls)}
        for i,frame in enumerate(complete.calls,1):
            if frame[0]==0x74 and struct.unpack_from('<I',frame,1)[0]in (0xff000000,0xff008000):indices.add(i)
        for index in sorted(indices):
            for after in (False,True):
                with self.subTest(index=index,after=after):
                    dev,journal,runner=self.make();dev.after_write=after;dev.fail=lambda f,d:len(d.calls)==index
                    with self.assertRaises(OSError):runner.run()
                    self.assertEqual(len(dev.calls),index)
                    choice=selected(dev.eeprom);self.assertIn(choice,(0x4000,0x3c0,0x8000))
                    if choice==0x8000:self.assertEqual(dev.eeprom[choice:choice+14322],self.plan.candidate)
                    self.assertEqual(dev.eeprom[0x100:0x128],self.plan.old_ss)
                    self.assertEqual(dev.eeprom[0x4000:0x77f2],self.plan.retained_candidate)
                    self.assertEqual(dev.eeprom[r.VS],self.plan.baseline[r.VS])
    def test_original_backup_and_active_trial_are_write_protected(self):
        for offset in (0x100,0x1c0,0x3c0,0x4000,0x7fff,0xb7f2,0xf000):
            with self.assertRaises(ValueError):self.plan.write_frame(offset,b'x')
    def test_complete_byte_prefix_cuts_for_SS0_switch(self):
        # At each completed-byte prefix, a selected new DS must be whole. This
        # tests every modeled byte of the actual staged new payload/header.
        dev,_,runner=self.make();runner.run();frames=dev.calls
        eeprom=bytearray(self.plan.baseline);states=0
        for frame in frames:
            if frame[0]!=0x74:continue
            address,n=struct.unpack_from('<IH',frame,1);offset=address-0xff000000
            for i,value in enumerate(frame[7:-1]):
                eeprom[offset+i]=value;choice=selected(eeprom);self.assertIn(choice,(0x4000,0x3c0,0x8000))
                if choice==0x8000:self.assertEqual(eeprom[choice:choice+14322],self.plan.candidate)
                states+=1
        self.assertEqual(states,14363)
    def test_capability_default_remains_disabled(self):
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)
        with self.assertRaises(ValueError):r.NativeHID(self.plan,write=True)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report={'methods_run':result.testsRun,'passed':result.wasSuccessful(),'completed_byte_cuts':14363,
            'device_access':False,'flashed':False,'source_sha256':r.digest(Path(p2.__file__).read_bytes()),
            'candidate_sha256':p2.EXPECTED_CANDIDATE_SHA,'target_DS':32768,
            'preserves_original_DS_and_SS100_and_A85_DS':True}
    (r.ROOT/'artifacts/k2-initial-release/radio-phase1-installer-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
