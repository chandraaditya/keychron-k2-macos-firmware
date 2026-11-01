"""Read-only acceptance check for the exact installed trial, not an updater."""
import json
from pathlib import Path
import signal
import struct
import subprocess
import sys

import radio_installer as r


def verify(io,plan,*,phase1=False):
    identity=io.read(0x208f02,14)
    expected=bytes.fromhex('b125860ac0023230323631303238')if phase1 else bytes.fromhex('b125850ac0023230323631303237')
    build='A86/20261028'if phase1 else'A85/20261027'
    if identity!=expected:raise ValueError(f'Expected custom {build} identity')
    # Extract the extension from the hash-pinned DS itself, not editable metadata.
    offset=0;extension=None
    while offset<len(plan.candidate):
        kind=plan.candidate[offset];n=int.from_bytes(plan.candidate[offset+1:offset+3],'little')
        payload=plan.candidate[offset+3:offset+3+n];offset+=3+n
        if kind==10 and payload[:4]==struct.pack('<I',0x209014):extension=payload[4:]
    if extension is None or len(extension)!=440:raise ValueError('Unexpected reviewed extension')
    if io.read(0x209014,440)!=extension:raise ValueError('Installed extension differs')
    hook='02f0d3fa'if phase1 else'02f0d2fa'
    if io.read(0x206aa8,4)!=bytes.fromhex(hook):raise ValueError('Constructor hook not installed')
    ptr=int.from_bytes(io.read(0x208ea8,4),'little')
    if ptr&3 or not 0x2091cc<=ptr<=0x20ef00-0x74:raise ValueError('Battery pointer invalid')
    table=int.from_bytes(io.read(ptr,4),'little')
    if table&3 or not 0x2091cc<=table<=0x20ef00-68:raise ValueError('Shadow table pointer invalid')
    original=bytearray(r.ROM.read_bytes()[0x4c2f4:0x4c2f4+60])
    for at,value in ((8,0x209141),(12,0x209119),(16,0x209145)):struct.pack_into('<I',original,at,value)
    if io.read(table,60)!=original:raise ValueError('Battery method table differs')
    percent=io.read(ptr+20,1)[0]
    if percent>100:raise ValueError('Internal battery estimate invalid')
    if int.from_bytes(io.read(0x208ea8,4),'little')!=ptr:raise ValueError('Battery object changed during check')
    result={'custom_build':build,'extension_and_constructor_hook_verified':True,
            'shadow_battery_methods_verified':True,'firmware_indicator_estimate_percent':percent,
            'read_only':True,'native_macos_UI_verified':False}
    # Resolve the application through the captured ROM's stable global, never
    # through its historical heap address. Report only a recognized type/flag.
    app=int.from_bytes(io.read(0x200414,4),'little')
    if not app&3 and 0x2091cc<=app<=0x20ef00-0x16c and io.read(app,4)==struct.pack('<I',0x208d04):
        sleep=io.read(app+0x12c,1)[0]
        if sleep in (0xaa,0x55):result['radio_auto_sleep_disabled']=sleep==0xaa
    return result


def main():
    if sys.argv[1:]not in([],['--phase1']):raise ValueError('Usage: verify_radio.py [--phase1]')
    phase1=sys.argv[1:]==['--phase1']
    if phase1:
        from radio_phase1_installer import Plan
        plan=Plan()
    else:plan=r.load_plan()
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    with r.NativeHID(plan)as io:result=verify(io,plan,phase1=phase1)
    # This independent existing utility selects the declared battery collection.
    raw=subprocess.run([str(r.ROOT/'build/keychron-raw-battery')],capture_output=True,text=True,timeout=15)
    result['standard_battery_read_returncode']=raw.returncode
    if raw.returncode==0:
        value=json.loads(raw.stdout)['raw_battery_percent'];result['standard_battery_percent']=value
        result['standard_report_matches_internal_sample']=value==result['firmware_indicator_estimate_percent']
    else:result['standard_battery_read_error']=raw.stderr.strip()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
