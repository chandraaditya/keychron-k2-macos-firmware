"""A88 verification through raw diagnostics and native management bridge.

Read-only. No raw addresses/serials printed; widget acceptance remains manual.
"""
import json
import plistlib
import struct
import subprocess
import sys
import radio_installer as r
import radio_keyhole_trial as k
from apple_raw_hid import AppleRawHID,AppleManagementHID
from verify_radio_apple_trial import get_report,radio_profile,published_hid_profile,native_battery_services

IDENTITY=bytes.fromhex('b125880ac0023230323631303238')
EXTENSION_SHA='34b17627521810fc57a2fcfa0fb9646c4621cab971b3873f9736c2e32e48b346'
METHODS=(0x28a9,0x28dd,0x209291,0x20919b,0x209295,0x2949,0x296d,
         0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

def verify(io,plan):
    if io.read(0x208f02,14)!=IDENTITY:raise ValueError('Expected active A88 identity')
    if r.digest(io.read(0x209014,816))!=EXTENSION_SHA:raise ValueError('A88 extension differs')
    if io.read(0x206aa8,4)!=bytes.fromhex('02f0d3fa')or io.read(0x208d30,4)!=struct.pack('<I',0x20914b):
        raise ValueError('A88 GET/SET hooks differ')
    battery=int.from_bytes(io.read(0x208ea8,4),'little')
    if battery&3 or not 0x209000<=battery<=0x20ef00-0x74:raise ValueError('A88 battery pointer invalid')
    table=int.from_bytes(io.read(battery,4),'little')
    if table&3 or not 0x209000<=table<=0x20ef00-152:raise ValueError('A88 table pointer invalid')
    if io.read(table,60)!=struct.pack('<15I',*METHODS):raise ValueError('A88 methods differ')
    if io.read(0x205e1c,4)!=struct.pack('<I',0x4000):raise ValueError('Expected A88 running bank4000')
    if io.read(0xff000000,40)!=b'\0'+plan.new_ss[1:]or io.read(0xff000100,40)!=plan.backup_ss:
        raise ValueError('Expected A88 one-boot recovery headers')
    percent=io.read(battery+0x14,1)[0]
    if percent>100:raise ValueError('Battery estimate invalid')
    return {'A88_active':True,'extension_and_GET_SET_methods_verified':True,'trial_SS0_invalidated':True,
            'backup_SS100_selects_A86':True,'battery_estimate':percent,'firmware_writes':False},io.read(battery+6,6)

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments; read-only')
    plan=k.Plan();target=r.ROOT/'artifacts/k2-initial-release/radio-keyhole-trial-live-verification.json'
    with AppleRawHID(plan,write=False)as io:
        result,address=verify(io,plan)
        result.update(radio_profile(io));result['published_raw_interface']=published_hid_profile(io)
    target.write_text(json.dumps(result,indent=2)+'\n')
    # Releasing the raw reader's lock first avoids two simultaneous handles.
    with AppleManagementHID(plan,write=False)as io:
        result['published_management_interface']=published_hid_profile(io)
        for key,kind,rid,n in [('Input90',0,0x90,3),('Feature34',2,0x34,77)]:
            try:
                raw=get_report(io,kind,rid,n)
                if rid==0x90:result[key]={'percent':raw[2],'status_flags':raw[1],'valid_percent':raw[2]<=100}
                else:result[key]={'bytes':len(raw),'version':raw[1],'address_matches':raw[4:10]==address}
            except (ValueError,RuntimeError,OSError)as error:
                result[key]={'error':str(error)};break
    output=subprocess.run(['/usr/sbin/ioreg','-a','-r','-c','AppleDeviceManagementHIDEventService'],capture_output=True,check=True)
    result['native_management_services']=native_battery_services(address,plistlib.loads(output.stdout))
    result['native_widget_visibility_verified']=False
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
