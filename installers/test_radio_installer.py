"""Offline transaction/transport tests. No IOHID manager or hardware is opened."""
import ctypes as C
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import radio_installer as r


class MemoryJournal:
    def __init__(self):self.events=[];self.saved=None
    def event(self,**data):self.events.append(data)
    def backup(self,data):self.saved=bytes(data)


class MemoryDevice:
    def __init__(self,plan):
        self.plan=plan;self.eeprom=bytearray(plan.baseline);self.ram=bytearray(r.RAM.read_bytes())
        self.enabled=False;self.calls=[];self.fail=None;self.after_write=False;self.read_fault=None
    def read(self,address,length):
        if self.read_fault and self.read_fault(address,length):raise ValueError('simulated underlying read failure')
        if 0xff000000<=address and address+length<=0xff010000:
            return bytes(self.eeprom[address-0xff000000:address-0xff000000+length])
        if 0x200000<=address and address+length<=0x210000:
            return bytes(self.ram[address-0x200000:address-0x200000+length])
        raise AssertionError('Unexpected address')
    def set(self,frame):
        self.calls.append(bytes(frame))
        failing=self.fail and self.fail(frame,self)
        if failing and not self.after_write:raise OSError('simulated lost acknowledgment')
        if frame==b'\x70':self.enabled=True
        else:
            assert frame[0]==0x74 and self.enabled
            address,n=struct.unpack_from('<IH',frame,1);offset=address-0xff000000;data=frame[7:-1]
            assert n==len(data) and self.plan.write_frame(offset,data)==frame
            self.eeprom[offset:offset+n]=data
        if failing:raise OSError('simulated lost acknowledgment after write')


def selected(ds):
    # A small independent selector for the tested section records; actual ROM
    # section validation is covered by the separate persistence emulator.
    for offset in (0,0x100):
        ss=ds[offset:offset+40]
        if ss[:3]==b'\x01\x08\0' and not sum(ss[3:11])&255:
            return int.from_bytes(ss[30:34],'little')
    return None


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=r.load_plan()
    def make(self):
        dev=MemoryDevice(self.plan);journal=MemoryJournal();return dev,journal,r.Runner(dev,self.plan,journal)
    def test_native_reader_uses_one_I2C_transfer_per_EEPROM_request(self):
        # Fake only the native transport. Execute the actual reader, response
        # parser and address/length checks without opening an HID manager.
        for address,expected in [(0xff008000,[16,16,16,16,1]),(0x208000,[32,32,1])]:
            reader=object.__new__(r.NativeHID)
            reader.device=None;reader.failed=False;reader.last_refresh=None;reader.progress=None
            requests=[]
            def request(frame):
                self.assertEqual(frame[0],0x71)
                a,n=struct.unpack_from('<IH',frame,1);requests.append((a,n))
            def response(device,kind,rid,buffer,size):
                a,n=requests[-1]
                payload=bytes((a+i)&255 for i in range(n))
                packet=r.checksum(b'\x72'+struct.pack('<IH',a,n)+payload)
                C.memmove(buffer,packet,len(packet));size._obj.value=len(packet)
                return 0
            reader.set=request;reader.get_report=response
            with patch.object(r.signal,'alarm',lambda seconds:None):
                actual=reader.read(address,65)
            self.assertEqual([n for _,n in requests],expected)
            self.assertEqual(actual,bytes((address+i)&255 for i in range(65)))
    def test_complete_transaction_and_write_allowlist(self):
        dev,journal,runner=self.make();r.guard_context(dev);runner.run()
        self.assertTrue(runner.committed);self.assertEqual(selected(dev.eeprom),0x4000)
        self.assertEqual(dev.eeprom[:40],self.plan.new_ss)
        self.assertEqual(dev.eeprom[0x100:0x128],self.plan.old_ss)
        self.assertEqual(dev.eeprom[0x4000:0x4000+14322],self.plan.candidate)
        for i,(old,new)in enumerate(zip(self.plan.baseline,dev.eeprom)):
            if not any(lo<=i<hi for lo,hi in self.plan.ranges):self.assertEqual(old,new)
        self.assertEqual(journal.saved,self.plan.baseline)
        self.assertEqual(journal.events[-1]['action'],'committed-and-verified')
        self.assertEqual({x[0] for x in dev.calls},{0x70,0x74})
    def test_current_pairings_are_saved_and_preserved(self):
        dev,journal,runner=self.make();dev.eeprom[0x200]^=7;fresh=bytes(dev.eeprom);runner.run()
        self.assertEqual(journal.saved,fresh);self.assertEqual(dev.eeprom[r.VS],fresh[r.VS])
    def test_fresh_identity_change_stops_before_enable(self):
        dev,journal,runner=self.make();dev.eeprom[5]^=1
        with self.assertRaises(ValueError):runner.run()
        self.assertEqual(dev.calls,[])
    def test_context_guards_stop_before_enable(self):
        # version, table, factory, dispatcher, base, mode, boundary, timer state
        pointer=int.from_bytes(r.RAM.read_bytes()[0x67bc:0x67c0],'little')
        timer=int.from_bytes(r.RAM.read_bytes()[pointer-0x200000+32:pointer-0x200000+36],'little')
        for address in (0x208f04,0x206794,0x206676,0x2066a4,pointer+12,0x205e10,0x20102c,timer):
            with self.subTest(address=hex(address)):
                dev,journal,runner=self.make();dev.ram[address-0x200000]^=0x10
                with self.assertRaises(ValueError):runner.run()
                self.assertEqual(dev.calls,[])
    def test_enable_ack_loss_has_durable_intent_and_no_retry(self):
        for after in (False,True):
            dev,journal,runner=self.make();dev.fail=lambda f,d:f==b'\x70';dev.after_write=after
            with self.assertRaises(OSError):runner.run()
            self.assertEqual(dev.calls,[b'\x70']);self.assertTrue(runner.enable_attempted)
            self.assertFalse(runner.enabled)
            self.assertTrue(any(e['action']=='before-enable'for e in journal.events))
            self.assertEqual(journal.events[-1]['action'],'stopped')
    def test_failure_boundaries_select_only_complete_old_or_new(self):
        # Obtain actual frame count and critical commit/invalidation indices.
        dev,_,runner=self.make();runner.run()
        indices={1,2,3,len(dev.calls)-2,len(dev.calls)-1,len(dev.calls)}
        for i,frame in enumerate(dev.calls,1):
            if frame[0]==0x74:
                address,n=struct.unpack_from('<IH',frame,1)
                if address in (0xff000000,0xff000100,0xff004000):indices.add(i)
        for index in sorted(indices):
            for after in (False,True):
                with self.subTest(index=index,after=after):
                    dev,journal,runner=self.make();dev.after_write=after
                    dev.fail=lambda f,d:len(d.calls)==index
                    with self.assertRaises(OSError):runner.run()
                    self.assertEqual(len(dev.calls),index)
                    chosen=selected(dev.eeprom);self.assertIn(chosen,(0x3c0,0x4000))
                    if chosen==0x4000:self.assertEqual(dev.eeprom[chosen:chosen+14322],self.plan.candidate)
                    self.assertEqual(dev.eeprom[0x3c0:0x39f3],self.plan.baseline[0x3c0:0x39f3])
                    self.assertEqual(dev.eeprom[r.VS],self.plan.baseline[r.VS])
    def test_post_write_readback_failure_stops_without_retry(self):
        dev,journal,runner=self.make()
        dev.read_fault=lambda a,n:dev.enabled and len(dev.calls)==2 and a==0xff000100
        with self.assertRaises(ValueError):runner.run()
        self.assertEqual(len(dev.calls),2);self.assertEqual(selected(dev.eeprom),0x3c0)
    def test_fixed_candidate_and_reference_hashes(self):
        changed=bytearray(self.plan.candidate);changed[-4]^=1
        manifest=dict(self.plan.manifest,candidate_dynamic_sha256=r.digest(changed))
        with self.assertRaises(ValueError):r.Plan(self.plan.baseline,changed,manifest)
        changed=bytearray(self.plan.baseline);changed[20]^=1
        with self.assertRaises(ValueError):r.Plan(changed,self.plan.candidate,self.plan.manifest)
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'ram';path.write_bytes(bytes(65536))
            with patch.object(r,'RAM',path):
                with self.assertRaises(ValueError):r.guard_context(MemoryDevice(self.plan))
    def test_write_boundaries_and_forbidden_regions(self):
        for offset,data in ((0x1c0,b'x'),(0x3c0,b'x'),(0xf000,b'x'),(0x400f,b'xx'),(0x4000,b'x'*15),(0x4000,b'')):
            with self.subTest(offset=offset,data=len(data)):
                with self.assertRaises(ValueError):self.plan.write_frame(offset,data)
    def test_framing_and_false_success_read(self):
        # AA is also the legitimate auto-sleep-disabled RAM flag. The false
        # EEPROM-success prefill guard must not reject ordinary RAM values.
        ram_reply=r.checksum(b'\x72'+struct.pack('<IH',0x20c934,1)+b'\xaa')
        self.assertEqual(r.parse_read(ram_reply,0x20c934,1),b'\xaa')
        for n in (1,14,32):
            frame=r.read_frame(0xff000100,n);self.assertEqual(sum(frame)&255,0)
            header=b'\x72'+struct.pack('<IH',0xff000100,n)
            self.assertEqual(r.parse_read(r.checksum(header+b'\x12'*n),0xff000100,n),b'\x12'*n)
            with self.assertRaises(ValueError):r.parse_read(r.checksum(header+b'\xaa'*n),0xff000100,n)
            wrong=bytearray(r.checksum(header+b'\x12'*n));wrong[-1]^=1
            with self.assertRaises(ValueError):r.parse_read(wrong,0xff000100,n)
        for a,n in ((0x329000,4),(0xff010000,1),(0x100000,1),(0,33)):
            with self.assertRaises(ValueError):r.read_frame(a,n)
    def test_hardware_gate_and_forbidden_reports(self):
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)
        with self.assertRaises(ValueError):r.NativeHID(self.plan,write=True)
        io=r.NativeHID(self.plan)
        for frame in (b'\x70',b'\x73',b'\x75',self.plan.write_frame(0,b'\0')):
            with self.assertRaises(ValueError):io.set(frame)
    def test_native_api_feature_enum_and_read_size(self):
        io=r.NativeHID(self.plan);io.device=None;calls=[];setup=[]
        for length in (0,-1,65537):
            with self.assertRaises(ValueError):io.read(0xff000000,length)
        def send(device,kind,rid,buf,size):
            calls.append(kind);setup[:]=[bytes(buf.raw)];return 0
        def receive(device,kind,rid,buf,size):
            calls.append(kind);address,n=struct.unpack_from('<IH',setup[0],1)
            reply=r.checksum(b'\x72'+struct.pack('<IH',address,n)+b'\x13'*n)
            C.memmove(buf,reply,len(reply));return 0
        io.set_report=send;io.get_report=receive
        self.assertEqual(io.read(0xff000000,65),b'\x13'*65)
        self.assertEqual(calls,[2]*10) # five16-byte-or-smaller EEPROM requests; macOS Feature enum2
        def badsize(device,kind,rid,buf,size):C.cast(size,C.POINTER(C.c_long))[0]=999;return 0
        io.get_report=badsize
        with self.assertRaises(ValueError):io.read(0xff000000,1)
        self.assertTrue(io.failed)
    def test_watchdog_deadline_and_error_lockout(self):
        io=r.NativeHID(self.plan);io.last_refresh=time.monotonic()-6.1
        with self.assertRaises(RuntimeError):io.set(r.read_frame(0x200000,1))
        self.assertTrue(io.failed)
        io.last_refresh=None
        with self.assertRaises(RuntimeError):io.set(r.read_frame(0x200000,1))
    def test_journal_persists_fresh_backup_privately(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'test.jsonl';journal=r.Journal(path)
            journal.backup(self.plan.baseline);journal.event(action='before-enable');journal.close()
            self.assertEqual(path.with_suffix('.eeprom.bin').read_bytes(),self.plan.baseline)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(path.with_suffix('.eeprom.bin').stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):r.Journal(path)
    def test_cli_plan_and_apply_refusal_use_no_hardware(self):
        for mode,code in (('--plan',0),('--apply',2),('--erase',2),('--launch',2)):
            out=subprocess.run([sys.executable,str(Path(r.__file__)),mode],capture_output=True,text=True)
            self.assertEqual(out.returncode,code,out.stderr)
            if mode=='--plan':self.assertFalse(json.loads(out.stdout)['hardware_updating_enabled'])
            if mode=='--apply':self.assertIn('No device opened',out.stderr)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'methods_run':result.testsRun,'passed':result.wasSuccessful(),'hardware_updates_enabled':False,
            'device_access':False,'flashed':False,'source_sha256':r.digest(Path(r.__file__).read_bytes()),
            'candidate_sha256':r.EXPECTED_CANDIDATE_SHA,
            'limits':'Memory transport; no electrical interruption, HID timing or physical reset validation.'}
    (r.ROOT/'artifacts/k2-initial-release/radio-installer-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
