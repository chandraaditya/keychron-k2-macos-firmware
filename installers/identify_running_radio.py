"""Short read-only resume check. No report34 queries, update enable or writes."""
import json
import sys
import radio_installer as r
import radio_rollback_preflight as p
import radio_keyhole_trial as k
from apple_raw_hid import AppleRawHID
from verify_radio_apple_trial import verify as verify_A87
from verify_radio_keyhole_trial import verify as verify_A88

def identify(io,plan):
    identity=io.read(0x208f02,14)
    known={p.IDENTITY:'A86',k.A87_IDENTITY:'A87',bytes.fromhex('b125880ac0023230323631303238'):'A88'}
    version=known.get(identity)
    if version is None:raise ValueError('Unexpected radio firmware identity; no update attempted')
    r.guard_context(io,expected_identity=identity)
    if version=='A86':p.guard_context(io)
    elif version=='A87':verify_A87(io,plan)
    else:verify_A88(io,plan)
    bank=int.from_bytes(io.read(0x205e1c,4),'little')
    ss0=io.read(0xff000000,40);ss100=io.read(0xff000100,40)
    if ss0!=b'\0'+plan.new_ss[1:]or ss100!=plan.backup_ss:
        raise ValueError('Boot entries differ from the prepared A88 update state')
    if (version=='A86' and bank!=0x8000)or (version in ('A87','A88')and bank!=0x4000):
        raise ValueError('Running firmware bank differs from expected trial/fallback')
    return {'running_firmware':version,'runtime_verified':True,'running_bank':hex(bank),
            'trial_boot_entry_invalid':True,'A86_fallback_entry_valid':True,
            'update_enabled':False,'firmware_writes':False}

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments; this check is read-only')
    if r.ALLOW_HARDWARE_UPDATES:raise ValueError('Expected updates disabled')
    plan=k.Plan();io=AppleRawHID(plan,write=False)
    try:io.__enter__()
    except RuntimeError as error:
        # Retry discovery only, before any report. Never retry a failed read.
        if str(error)!='Expected one Bluetooth diagnostic collection; found0':raise
        io=r.NativeHID(plan,write=False);io.__enter__()
    try:result=identify(io,plan)
    finally:io.__exit__(None,None,None)
    path=r.ROOT/'artifacts/k2-initial-release/radio-resume-identification.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
