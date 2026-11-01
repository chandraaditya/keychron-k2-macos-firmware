"""Read-only current A87 raw-path verification and private full EEPROM backup.

No update-enable or write calls exist here. No long Feature34 probe is made.
"""
import json
import os
from pathlib import Path
import stat
import sys
import time
import radio_installer as r
import radio_apple_trial as a
from apple_raw_hid import AppleRawHID
from verify_radio_apple_trial import verify,radio_profile,published_hid_profile,native_battery_services
from diagnose_radio_preflight import save

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments; read-only')
    if os.geteuid()==0:raise ValueError('Run without sudo')
    if r.ALLOW_HARDWARE_UPDATES:raise ValueError('Expected hardware update gate disabled')
    plan=a.Plan()
    parent=r.ROOT/'private/apple-raw-captures';parent.mkdir(mode=0o700,exist_ok=True)
    info=parent.lstat()
    if not stat.S_ISDIR(info.st_mode)or info.st_uid!=os.getuid()or info.st_mode&0o077:
        raise ValueError('Private raw-capture folder differs')
    folder=parent/str(time.time_ns());folder.mkdir(mode=0o700)
    with AppleRawHID(plan,write=False)as io:
        result,_=verify(io,plan)
        result.update(radio_profile(io));result['published_raw_interface']=published_hid_profile(io)
        result['raw_maintenance_access_verified']=True
        save(folder/'runtime.json',(json.dumps(result,indent=2)+'\n').encode())
        print('A87 and read-only maintenance access verified. Saving memory backup.',flush=True)
        io.progress=lambda used,total:print(f'Read {used}/{total} bytes.',flush=True)
        fresh=io.read(0xff000000,65536)
        save(folder/'eeprom.bin',fresh)
        # Verify identity-bearing/protected storage without printing raw data.
        expected=bytearray(plan.baseline)
        expected[0x4000:0x4000+len(plan.candidate)]=plan.candidate
        changed=[i for i,(x,y)in enumerate(zip(expected,fresh))if x!=y]
        outside=[i for i in changed if not r.VS.start<=i<r.VS.stop]
        blocks=sorted({i//16*16 for i in outside});stable=True
        for offset in blocks:
            if io.read(0xff000000+offset,16)!=fresh[offset:offset+16]:stable=False
        result.update(snapshot_sha256=r.digest(fresh),snapshot=str(folder/'eeprom.bin'),
                      changed_outside_VS_bytes=len(outside),changed_outside_VS_offsets=[hex(i)for i in outside],
                      changed_chunks_stable=stable,protected_code_and_headers_match=all(0xf000<=i<0xf073 or 0xf074<=i<0xf076 for i in outside),
                      update_enabled=False,firmware_writes=False)
        save(folder/'result.json',(json.dumps(result,indent=2)+'\n').encode())
    target=r.ROOT/'artifacts/k2-initial-release/Apple-raw-maintenance-probe.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ['A87_active','raw_maintenance_access_verified',
          'snapshot_sha256','snapshot','changed_outside_VS_bytes','changed_chunks_stable',
          'protected_code_and_headers_match','firmware_writes']},indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
