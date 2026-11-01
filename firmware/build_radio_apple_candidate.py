"""Offline A87 Apple-management profile. No transport or installer imports.

This is a research image, NOT cleared for physical installation. In particular
it does not implement or establish an independent recovery mechanism.
"""
import hashlib
import json
import struct
from pathlib import Path
from build_radio_candidate import ROOT, CAPTURE, EXPECTED_DS_SHA, EXPECTED_ROM_SHA
from build_radio_candidate import records, encode, assemble
from build_candidate import bl

OUT=ROOT/'private/candidates/radio-apple-profile'
BASE=0x209014

def sha(data):return hashlib.sha256(data).hexdigest()

def build_apple(*,out=OUT,component_path=None,version=0x87):
    if not 0<=version<=255:raise ValueError('Invalid version')
    original=CAPTURE.read_bytes()[0x3c0:]
    if sha(original)!=EXPECTED_DS_SHA:raise ValueError('Original DS mismatch')
    if sha((ROOT/'private/bt-rom-000000-050000.bin').read_bytes())!=EXPECTED_ROM_SHA:
        raise ValueError('ROM mismatch')
    items=records(original)
    if items[-2:]!=[(0xb,struct.pack('<I',0x2067ed)),(0xfe,b'')]:
        raise ValueError('Original startup mismatch')
    bf=(ROOT/'private/apple-profile/grouped-bf-record.bin').read_bytes()
    # Pinned reviewed profile fixture, not a general arbitrary config loader.
    if sha(bf)!='2639e809c89d583beedd5c74c76ac867ed7a0bed09d0ffdef60f117ccb545c31':
        raise ValueError('Reviewed SDP fixture mismatch')
    if bf[0]!=0xbf or len(bf)!=int.from_bytes(bf[1:3],'little')+3:
        raise ValueError('Bad BF record framing')
    boot,bs=assemble(ROOT/'research/radio_boot_phase1.S')
    component_path=Path(component_path) if component_path is not None else ROOT/'firmware/radio_apple_component.S'
    component,cs=assemble(component_path)
    component_base=BASE+len(boot)
    for slot,target in [('address_getter','get_report'),('address_notify','notify'),
                        ('address_connect','connected')]:
        struct.pack_into('<I',component,cs[slot],component_base+cs[target] | 1)
    if 'address_setter' in cs:
        struct.pack_into('<I',component,cs['address_setter'],component_base+cs['root_set_report'] | 1)
    end=component_base+len(component)
    if end%4 or end+152>=0x20ef00:raise ValueError('Extension reserve overflow')
    old_call=bl(0x206aa8,0x208380)
    new_call=bl(0x206aa8,BASE+bs['constructor_wrapper'])
    for slot,value in [('original_call_word',int.from_bytes(old_call,'little')),
                       ('replacement_call_word',int.from_bytes(new_call,'little')),
                       ('reserved_end',end),('component_entry',component_base|1)]:
        struct.pack_into('<I',boot,bs[slot],value)
    for i,(kind,payload) in enumerate(items):
        if kind==0xa and int.from_bytes(payload[:4],'little')==0x208e80:
            p=bytearray(payload)
            if p[4+0x84]!=5:raise ValueError('Unexpected identity')
            p[4+0x84]=version;p[4+0x88:4+0x90]=b'20261028'
            items[i]=(kind,bytes(p))
    extension=bytes(boot+component)
    # BF is processed before constructor callback; standard ROM reads it later.
    items[-2:]=[(0xbf,bf[3:]),(0xa,struct.pack('<I',BASE)+extension),
                (0xb,struct.pack('<I',BASE|1)),(0xfe,b'')]
    dynamic=encode(items)
    if len(dynamic)>0x4000:raise ValueError('Candidate does not fit inactive16KiB bank')
    manifest={'status':'offline-only-recovery-not-cleared','version':version,
              'dynamic_sha256':sha(dynamic),'dynamic_bytes':len(dynamic),
              'extension_sha256':sha(extension),'extension_start':BASE,
              'extension_bytes':len(extension),'heap_start':end,'shadow_bytes':152,
              'component_base':component_base,'component_symbols':cs,
              'boot_symbols':bs,'runtime_hook_bytes':new_call.hex(),
              'profile_bf_sha256':sha(bf),'source_sha256':sha(component_path.read_bytes()),
              'original_dynamic_sha256':EXPECTED_DS_SHA,'phase_guard':1,
              'preserves_original_reports':True,'new_input_reports':[0x90,0xe0,0x9a],
              'implemented_new_input_reports':[0x90],
              'implemented_feature_reports':[0x34],
              'status_flags':0,'native_macos_verified':False,'recovery_verified':False,
              'device_access':False,'flashed':False,
              'limits':['Apple VID004C/PID0267 is a temporary compatibility experiment.',
                        'Optional E0/9A are declared as on observed accessory but not emitted.',
                        'Unreviewed status/charging bits are zero.',
                        'Independent physical recovery is not verified.',
                        'No one-boot rollback prefix is included in this research image.']}
    out=Path(out);out.mkdir(parents=True,exist_ok=True);out.chmod(0o700)
    for name,data in [('dynamic-section.bin',dynamic),('extension.bin',extension),
                      ('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
        p=out/name;p.write_bytes(data);p.chmod(0o600)
    return manifest

if __name__=='__main__':
    m=build_apple()
    print(json.dumps({k:m[k] for k in ['status','dynamic_bytes','extension_bytes','heap_start','dynamic_sha256']}))
