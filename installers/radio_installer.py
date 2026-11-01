"""Exact-build radio staging engine. Hardware updating is disabled by default.

--plan uses files only. --check is explicitly read-only.
No erase73, RAM-write or LAUNCH75 implementation. Successful enable70 arms
the radio's inactivity watchdog, so an approved update has no user prompts.
"""
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
# No analysis-library imports in the installer. These hashes bind the reviewed
# installed reference and emitted candidate, independently of editable metadata.
EXPECTED_DS_SHA='50f2e98ac2aef18e7f41425fcd1c1d4639ab834c5f1872f58f28f0fef15b36b9'
EXPECTED_ROM_SHA='07532fa29dccc635926f3e97a8333d08b9ecb0130221078699a3e98cce5bc1bf'
EXPECTED_RAM_SHA='d82d0363ad8f74cf5dbeab63efd2511168cfd877a0bf3be7a6ce4a5d9053d508'
EXPECTED_BACKUP_SHA='e28a298f40343df5b53f5ec0ce4903ac6434b22b0c76d99a11545ac826b08467'
EXPECTED_CANDIDATE_SHA='b3f34bdbe1e5c32ff65707482cbddf621efee8fe705a63e1e7a82f7d8d8806ea'


def records(data):
    offset=0
    while offset+3<=len(data):
        kind=data[offset];size=int.from_bytes(data[offset+1:offset+3],'little')
        offset+=3+size
        if offset>len(data):raise ValueError('Truncated configuration record')
        if kind==0xfe:
            if size or offset!=len(data):raise ValueError('Invalid terminator or trailing data')
            return
    raise ValueError('Missing configuration terminator')

# Change only after explicit owner authorization and reviewed write-enabled tests.
ALLOW_HARDWARE_UPDATES=False
DS=ROOT/'private/candidates/radio-battery-initial/dynamic-section.bin'
MANIFEST=ROOT/'private/candidates/radio-battery-initial/manifest.json'
BACKUP=ROOT/'private/bt-eeprom-address-window-64k.bin'
RAM=ROOT/'private/ram-200000.bin'
ROM=ROOT/'private/bt-rom-000000-050000.bin'
VS=slice(0x1c0,0x3c0)
NEW_START=0x4000


def digest(data):return hashlib.sha256(data).hexdigest()
def checksum(frame):return bytes(frame)+bytes([(-sum(frame))&255])


def read_frame(address,length):
    if not 1<=length<=32:raise ValueError('Read length outside1..32')
    allowed=(0<=address<0x50000 and address+length<=0x50000) or \
            (0x200000<=address and address+length<=0x210000) or \
            (0xff000000<=address and address+length<=0xff010000)
    if not allowed:raise ValueError('Read outside approved ROM/RAM/EEPROM windows')
    return checksum(b'\x71'+struct.pack('<IH',address,length))


def parse_read(frame,address,length):
    if len(frame)!=length+8 or frame[0]!=0x72 or struct.unpack_from('<IH',frame,1)!=(address,length) or sum(frame)&255:
        raise ValueError('Read reply header/length/checksum mismatch')
    data=frame[7:-1]
    if 0xff000000<=address<0xff010000 and data==b'\xaa'*length:
        raise ValueError('All-AA read cannot establish underlying I2C success; refusing')
    return data


class Plan:
    def __init__(self,baseline,candidate,manifest):
        if len(baseline)!=65536 or digest(baseline)!=EXPECTED_BACKUP_SHA:raise ValueError('Expected reviewed full64KiB EEPROM backup')
        if len(candidate)!=14322:raise ValueError('Unexpected candidate size')
        if digest(candidate)!=EXPECTED_CANDIDATE_SHA or manifest['candidate_dynamic_sha256']!=EXPECTED_CANDIDATE_SHA:raise ValueError('Candidate hash mismatch')
        if digest(baseline[0x3c0:0x39f3])!=EXPECTED_DS_SHA:raise ValueError('Original DS differs')
        if baseline[0]!=1 or baseline[1:3]!=b'\x08\x00' or sum(baseline[3:11])&255:raise ValueError('Original SS invalid')
        if struct.unpack_from('<IIH',baseline,30)!=(0x3c0,0x1c0,0x200):raise ValueError('Unexpected SS/DS/VS layout')
        if any(baseline[0x100:0x128]):raise ValueError('Backup SS slot is not the reviewed empty slot')
        records(candidate)
        if NEW_START+len(candidate)>0x7800 or any(baseline[NEW_START:NEW_START+len(candidate)]):
            raise ValueError('Inactive DS slot is not the reviewed empty region')
        self.baseline=baseline;self.candidate=candidate;self.manifest=manifest
        self.old_ss=baseline[:40]
        new=bytearray(self.old_ss);struct.pack_into('<I',new,30,NEW_START);self.new_ss=bytes(new)
        self.ranges=((0,40),(0x100,0x128),(NEW_START,NEW_START+len(candidate)))

    def write_frame(self,offset,data):
        if not data or len(data)>14 or not any(lo<=offset and offset+len(data)<=hi for lo,hi in self.ranges):
            raise ValueError('Write outside exact planned SS/DS windows')
        if offset//16!=(offset+len(data)-1)//16:raise ValueError('Write crosses conservative16-byte boundary')
        return checksum(b'\x74'+struct.pack('<IH',0xff000000+offset,len(data))+data)

    def fresh_matches(self,fresh):
        if len(fresh)!=65536 or fresh[:VS.start]!=self.baseline[:VS.start] or fresh[VS.stop:]!=self.baseline[VS.stop:]:
            raise ValueError('EEPROM outside pairing/VS differs from reviewed backup')

    def summary(self):
        return {'candidate_sha256':digest(self.candidate),'candidate_bytes':len(self.candidate),
                'inactive_DS_start':NEW_START,'inactive_DS_end_exclusive':NEW_START+len(self.candidate),
                'backup_SS':0x100,'preserves_VS_and_old_DS':True,'ordinary_write_chunk_max':14,
                'software_boundary':16,'physical_page_bytes':128,'nominal_inactivity_reset_seconds':10,
                'activation':'Watchdog full-reset boot after activity stops; no direct LAUNCH',
                'hardware_updating_enabled':ALLOW_HARDWARE_UPDATES,'automatic_crashing_DS_rollback':False}


def load_plan():
    if digest(ROM.read_bytes())!=EXPECTED_ROM_SHA:raise ValueError('Reviewed ROM differs')
    manifest=json.loads(MANIFEST.read_text());return Plan(BACKUP.read_bytes(),DS.read_bytes(),manifest)


def guard_context(io,*,expected_identity=bytes.fromhex('b125050ac0023230313931303235')):
    if io.read(0x208f02,14)!=expected_identity:raise ValueError('Expected radio application identity differs')
    ram=RAM.read_bytes()
    if digest(ram)!=EXPECTED_RAM_SHA:raise ValueError('Reviewed RAM fingerprint source differs')
    for address,length in ((0x206676,0x1c),(0x206794,0x1c),(0x2066a4,0x3e)):
        if io.read(address,length)!=ram[address-0x200000:address-0x200000+length]:raise ValueError('Updater code/table fingerprint differs')
    pointer=int.from_bytes(io.read(0x2067bc,4),'little')
    if pointer&3 or not 0x209000<=pointer<=0x20ef00-36:raise ValueError('Updater object pointer invalid')
    obj=io.read(pointer,36)
    if int.from_bytes(obj[:4],'little')!=0x206794 or obj[4:10]!=bytes(range(0x70,0x76)) or \
       obj[12:20]!=b'\0'*8 or int.from_bytes(obj[20:22],'little')!=10 or obj[30]!=0:
        raise ValueError('Updater base/IDs/interval/enable context differs')
    if (io.read(0x205e10,1)[0]>>4)&7!=1:raise ValueError('Expected EEPROM storage mode1')
    if io.read(0x20102c,1)!=b'\x10':raise ValueError('Expected16-byte configured write boundary')
    timer=int.from_bytes(obj[32:36],'little')
    if timer&3 or not 0x209000<=timer<=0x20ef00-4 or io.read(timer,4)!=b'\0'*4:
        raise ValueError('Updater timer is not initially inactive')


class Journal:
    def __init__(self,path):
        self.path=Path(path)
        self.file=os.fdopen(os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w')
    def event(self,**data):
        self.file.write(json.dumps(data)+'\n');self.file.flush();os.fsync(self.file.fileno())
    def backup(self,data):
        path=self.path.with_suffix('.eeprom.bin')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        # Persist directory entries before enabling the updater.
        parent=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(parent)
        finally:os.close(parent)
        self.event(action='fresh-backup-saved',bytes=len(data),sha256=digest(data),file=path.name)
    def close(self):self.file.close()


class Runner:
    def __init__(self,io,plan,journal):self.io=io;self.plan=plan;self.journal=journal;self.enable_attempted=False;self.enabled=False;self.committed=False
    def verify(self,offset,expected):
        if self.io.read(0xff000000+offset,len(expected))!=expected:raise ValueError('Exact EEPROM readback differs')
    def write(self,offset,data):
        frame=self.plan.write_frame(offset,data)
        self.journal.event(action='before-write',offset=offset,bytes=len(data),sha256=digest(data))
        self.io.set(frame)
        self.verify(offset,data)
        self.journal.event(action='write-readback-verified',offset=offset,bytes=len(data))
    def block(self,offset,data):
        used=0
        while used<len(data):
            n=min(14,16-((offset+used)%16),len(data)-used)
            self.write(offset+used,data[used:used+n]);used+=n
    def run(self):
        guard_context(self.io)
        fresh=self.io.read(0xff000000,65536);self.plan.fresh_matches(fresh)
        self.journal.backup(fresh)
        self.journal.event(action='preflight-complete',fresh_backup_sha256=digest(fresh),**self.plan.summary())
        # No prompts or filesystem preparation after this point. A native hard
        # timeout exits without unwinding: an unmatched intent means UNKNOWN.
        self.journal.event(action='before-enable',outcome_if_no_completion='unknown; timer may be armed')
        self.enable_attempted=True
        try:
            self.io.set(b'\x70');self.enabled=True
            self.journal.event(action='enabled',expected_inactivity_reset_seconds=10)
            self.write(0x100,b'\0');self.block(0x101,self.plan.old_ss[1:])
            self.verify(0x100,b'\0'+self.plan.old_ss[1:]);self.write(0x100,b'\1')
            self.verify(0x100,self.plan.old_ss)
            self.block(NEW_START,self.plan.candidate);self.verify(NEW_START,self.plan.candidate)
            self.verify(0x3c0,self.plan.baseline[0x3c0:0x39f3])
            self.verify(VS.start,fresh[VS]);self.verify(0xf000,fresh[0xf000:])
            self.write(0,b'\0');self.block(1,self.plan.new_ss[1:])
            self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.verify(NEW_START,self.plan.candidate);self.verify(0x100,self.plan.old_ss)
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.old_ss)
            self.verify(VS.start,fresh[VS])
            self.journal.event(action='committed-and-verified',activation='expected-watchdog-full-reset')
        except BaseException:
            # No blind rewrite, automatic rollback, direct launch or keepalive.
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Write may have happened; timer may reset radio. Inspect journal before retry.')
            raise


class NativeHID:
    """Standard-library macOS HID bridge. All mutating reports are gated twice."""
    def __init__(self,plan,write=False,lock_owner_uid=None):
        if write and not ALLOW_HARDWARE_UPDATES:raise ValueError('Hardware updates are disabled; no device opened')
        self.lock_owner_uid=os.getuid()
        if lock_owner_uid is not None:
            if os.geteuid()!=0 or lock_owner_uid!=ROOT.stat().st_uid or lock_owner_uid==0:
                raise ValueError('Explicit lock owner requires root and the non-root project owner')
            self.lock_owner_uid=lock_owner_uid
        self.plan=plan;self.write=write;self.device=None;self.manager=None;self.devices=None;self.lock=None;self.seized=False;self.refs=[];self.last_refresh=None;self.failed=False;self.progress=None
    def __enter__(self):
        try:return self._enter()
        except BaseException:
            self.__exit__();raise
    def _enter(self):
        self.lock=os.open(ROOT/'private/read.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        info=os.fstat(self.lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.lock_owner_uid or info.st_nlink!=1 or info.st_mode&0o077:
            raise ValueError('Unsafe radio operation lock')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.hid=C.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
        def declare(lib,name,args,result):
            fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
        P=C.c_void_p;L=C.c_long;I=C.c_int32;U=C.c_uint32
        self.string=declare(self.cf,'CFStringCreateWithCString',[P,C.c_char_p,U],P)
        self.release=declare(self.cf,'CFRelease',[P],None)
        self.dict_create=declare(self.cf,'CFDictionaryCreate',[P,C.POINTER(P),C.POINTER(P),L,P,P],P)
        self.set_count=declare(self.cf,'CFSetGetCount',[P],L)
        self.set_values=declare(self.cf,'CFSetGetValues',[P,C.POINTER(P)],None)
        self.array_count=declare(self.cf,'CFArrayGetCount',[P],L)
        self.array_value=declare(self.cf,'CFArrayGetValueAtIndex',[P,L],P)
        self.create=declare(self.hid,'IOHIDManagerCreate',[P,U],P)
        self.match=declare(self.hid,'IOHIDManagerSetDeviceMatching',[P,P],None)
        self.open=declare(self.hid,'IOHIDManagerOpen',[P,U],I)
        self.close=declare(self.hid,'IOHIDManagerClose',[P,U],I)
        self.copy=declare(self.hid,'IOHIDManagerCopyDevices',[P],P)
        self.elements=declare(self.hid,'IOHIDDeviceCopyMatchingElements',[P,P,U],P)
        self.element_id=declare(self.hid,'IOHIDElementGetReportID',[P],U)
        self.element_type=declare(self.hid,'IOHIDElementGetType',[P],U)
        self.device_open=declare(self.hid,'IOHIDDeviceOpen',[P,U],I)
        self.device_close=declare(self.hid,'IOHIDDeviceClose',[P,U],I)
        self.set_report=declare(self.hid,'IOHIDDeviceSetReport',[P,U,L,P,L],I)
        self.get_report=declare(self.hid,'IOHIDDeviceGetReport',[P,U,L,P,C.POINTER(L)],I)
        refs=self.refs=[self.string(None,s,0x08000100)for s in [b'Product',b'Transport',b'Keychron K2',b'Bluetooth']]
        if any(not ref for ref in refs):raise RuntimeError('HID matching string allocation failed')
        # CFType callbacks compare string values and retain the entries.
        keys=(P*2)(refs[0],refs[1]);vals=(P*2)(refs[2],refs[3])
        key_callbacks=C.addressof(C.c_byte.in_dll(self.cf,'kCFTypeDictionaryKeyCallBacks'))
        value_callbacks=C.addressof(C.c_byte.in_dll(self.cf,'kCFTypeDictionaryValueCallBacks'))
        match=self.dict_create(None,keys,vals,2,key_callbacks,value_callbacks)
        if not match:raise RuntimeError('HID matching allocation failed')
        self.manager=self.create(None,0)
        if not self.manager:self.release(match);raise RuntimeError('HID manager allocation failed')
        self.match(self.manager,match)
        self.release(match)
        status=self.open(self.manager,0)
        if status:raise RuntimeError(f'HID access failed0x{status&0xffffffff:08x}')
        self.devices=self.copy(self.manager);count=self.set_count(self.devices)if self.devices else 0
        values=(P*count)()
        if count:self.set_values(self.devices,values)
        candidates=[]
        for device in values:
            if self._matches_diagnostic_device(device):candidates.append(device)
        if len(candidates)!=1:raise RuntimeError(f'Expected one Bluetooth diagnostic collection; found{len(candidates)}')
        self.device=candidates[0]
        if self.write:
            claim_status=self.device_open(self.device,1)
            if claim_status:raise RuntimeError(f'Exclusive device claim failed0x{claim_status&0xffffffff:08x}; no update enabled')
            self.seized=True
        return self
    def _matches_diagnostic_device(self,device):
        elements=self.elements(device,None,0)
        if not elements:return False
        try:
            for i in range(self.array_count(elements)):
                item=self.array_value(elements,i)
                if self.element_id(item)==0xb2 and self.element_type(item)==129:return True
            return False
        finally:self.release(elements)
    def __exit__(self,*args):
        if self.seized:self.device_close(self.device,1);self.seized=False
        if self.devices:self.release(self.devices);self.devices=None
        if self.manager:self.close(self.manager,0);self.release(self.manager);self.manager=None
        for ref in self.refs:
            if ref:self.release(ref)
        self.refs=[]
        if self.lock is not None:os.close(self.lock);self.lock=None
    def _before_request(self):
        if self.failed:raise RuntimeError('Transport already failed; no further requests')
        if self.last_refresh is not None and time.monotonic()-self.last_refresh>=6:
            self.failed=True
            raise RuntimeError('Conservative watchdog deadline exceeded; stop without retry')
    def set(self,frame):
        self._before_request()
        if not frame:raise ValueError('Empty report')
        if frame[0]==0x71:
            if len(frame)!=8 or sum(frame)&255:raise ValueError('Invalid read-setup packet')
            addr,n=struct.unpack_from('<IH',frame,1)
            if read_frame(addr,n)!=frame:raise ValueError('Invalid read request')
        elif frame==b'\x70' or frame[0]==0x74:
            if not self.write or not ALLOW_HARDWARE_UPDATES:raise ValueError('Hardware update capability disabled')
            if frame[0]==0x74:
                addr,n=struct.unpack_from('<IH',frame,1)
                if addr>>16!=0xff00 or len(frame)!=n+8 or self.plan.write_frame(addr-0xff000000,frame[7:-1])!=frame:
                    raise ValueError('Rejected write packet')
        else:raise ValueError('Report is not in the updater allowlist')
        buf=C.create_string_buffer(frame,len(frame));started=time.monotonic();signal.alarm(3)
        try:status=self.set_report(self.device,2,frame[0],buf,len(frame))
        finally:signal.alarm(0)
        if status:
            self.failed=True
            raise RuntimeError(f'SET_REPORT failed0x{status&0xffffffff:08x}; no retry')
        if self.last_refresh is not None or frame==b'\x70':self.last_refresh=started
    def read(self,address,length):
        if not 1<=length<=65536:raise ValueError('Read length outside1..65536')
        result=bytearray()
        while len(result)<length:
            addr=address+len(result)
            # ROM GET72 ignores I2C adapter failure. A32-byte EEPROM read can
            # return a real first16 plus AA-prefilled tail with valid checksum.
            # One physical16-byte transfer per request lets parse_read reject
            # a wholly AA failed transfer instead of accepting a partial read.
            limit=16 if 0xff000000<=addr<0xff010000 else 32
            n=min(limit,length-len(result))
            self.set(read_frame(addr,n));buf=C.create_string_buffer(n+8);size=C.c_long(n+8)
            self._before_request();started=time.monotonic();signal.alarm(3)
            try:status=self.get_report(self.device,2,0x72,buf,C.byref(size))
            finally:signal.alarm(0)
            if status:
                self.failed=True
                raise RuntimeError(f'GET_REPORT failed0x{status&0xffffffff:08x}; no retry')
            if size.value!=n+8:
                self.failed=True;raise ValueError('Native GET_REPORT size mismatch')
            try:result.extend(parse_read(bytes(buf.raw),addr,n))
            except ValueError:
                self.failed=True;raise
            if self.last_refresh is not None:self.last_refresh=started
            if self.progress and length>=4096 and (len(result)%4096==0 or len(result)==length):
                self.progress(len(result),length)
        return bytes(result)


def main():
    if len(sys.argv)!=2 or sys.argv[1]not in ['--plan','--check','--apply']:
        print('Usage: radio_installer.py --plan|--check|--apply',file=sys.stderr);return 2
    mode=sys.argv[1]
    if mode=='--apply' and not ALLOW_HARDWARE_UPDATES:
        print('Hardware updates are disabled. No device opened.',file=sys.stderr);return 2
    plan=load_plan()
    if mode=='--plan':print(json.dumps(plan.summary(),indent=2));return 0
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    with NativeHID(plan,write=(mode=='--apply'))as io:
        if mode=='--check':
            guard_context(io);fresh=io.read(0xff000000,65536);plan.fresh_matches(fresh)
            print(json.dumps({'mode':'read-only-preflight','passed':True,'update_enabled':False,'flashed':False}));return 0
        folder=ROOT/'private/update-sessions';folder.mkdir(mode=0o700,exist_ok=True)
        journal=Journal(folder/f'radio-{time.time_ns()}.jsonl')
        try:Runner(io,plan,journal).run()
        finally:journal.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
