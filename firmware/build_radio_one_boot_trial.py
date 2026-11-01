"""Build guarded OFFLINE research trials; no device/installer imports."""
import json
import struct
from pathlib import Path
from build_radio_candidate import ROOT,assemble,encode,records,sha
from build_radio_apple_candidate import build_apple

BASE=0x209014

def guarded(dynamic,*,budget=100000):
    code,symbols=assemble(ROOT/'research/radio_one_boot_guard.S')
    struct.pack_into('<I',code,symbols['redirect_address'],BASE+symbols['redirect_once']|1)
    struct.pack_into('<I',code,symbols['poll_budget'],budget)
    prefix=[(0xa,struct.pack('<I',BASE)+bytes(code)),(0xb,struct.pack('<I',BASE|1))]
    image=encode(prefix+records(dynamic))
    if len(image)>0x4000:raise ValueError('Guarded image overlaps retained A86 bank')
    return image,{'guard_bytes':len(code),'guard_symbols':symbols,'guard_base':BASE,
                  'guard_sha256':sha(code),'bounded_poll_budget':budget}

def build_trials():
    apple=build_apple()
    results={}
    for name,source in [('radio-rollback-preflight',ROOT/'private/candidates/radio-battery-phase1'),
                        ('radio-apple-one-boot',ROOT/'private/candidates/radio-apple-profile')]:
        image,guard=guarded((source/'dynamic-section.bin').read_bytes())
        m={'status':'offline-only-physical-recovery-trial-not-run',**guard,
           'dynamic_bytes':len(image),'dynamic_sha256':sha(image),
           'source_dynamic_sha256':sha((source/'dynamic-section.bin').read_bytes()),
           'source_extension_sha256':sha((source/'extension.bin').read_bytes()),
           'source_extension_bytes':len((source/'extension.bin').read_bytes()),
           'candidate_bank':0x4000,'retained_fallback_bank':0x8000,
           'requires_verified_SS100_fallback':True,'fallback_preflight_observed':False,
           'independent_external_recovery_verified':False,'flashed':False,
           'native_macos_verified':False,
           'physical_bus_failure_recoverable_by_software':False}
        out=ROOT/'private/candidates'/name;out.mkdir(exist_ok=True);out.chmod(0o700)
        for filename,data in [('dynamic-section.bin',image),
                              ('manifest.json',(json.dumps(m,indent=2)+'\n').encode())]:
            p=out/filename;p.write_bytes(data);p.chmod(0o600)
        results[name]=m
    return results

if __name__=='__main__':
    print(json.dumps({k:{n:m[n] for n in ['status','dynamic_bytes','dynamic_sha256']} for k,m in build_trials().items()}))
