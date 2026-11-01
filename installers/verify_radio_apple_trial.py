"""Read-only A87 activation, report protocol and native service observations.

Never enables updates. No raw addresses/serials/Feature34 are printed or saved.
Actual widget visibility requires owner observation separately.
"""
import ctypes as C
import json
import plistlib
import signal
import struct
import subprocess
import sys
import radio_installer as r
import radio_apple_trial as a

EXTENSION_SHA='aec7fbf5a20dfc309d7cad1711d5b5ebebacf711905426d7e12ab228e72a3abb'
IDENTITY=bytes.fromhex('b125870ac0023230323631303238')
SDP_SHA='6d7bbbf0b7db0837ddb3819fe978607460b40f5ecf00695e4d77f9c630ed1813'
METHODS=(0x28a9,0x28dd,0x2091ad,0x209137,0x2091b1,0x2949,0x296d,
         0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

def get_report(io,kind,rid,n):
    io._before_request()
    buf=C.create_string_buffer(bytes([rid])+bytes(n-1),n);length=C.c_long(n)
    signal.alarm(3)
    try:status=io.get_report(io.device,kind,rid,buf,C.byref(length))
    finally:signal.alarm(0)
    if status or length.value!=n or buf.raw[0]!=rid:
        io.failed=True
        raise ValueError(f'Report{rid:02x} failed or had unexpected length: status{status&0xffffffff:08x}')
    return bytes(buf.raw)

def native_battery_services(address,tree):
    matches=[]
    def walk(node):
        if isinstance(node,dict):
            if node.get('IOObjectClass')=='AppleDeviceManagementHIDEventService' and node.get('BD_ADDR')==address:
                value=node.get('BatteryPercent')
                matches.append({'class':node['IOObjectClass'],'battery_percent':value,
                                'battery_status_flags':node.get('BatteryStatusFlags'),
                                'valid_battery_percent':type(value)is int and 0<=value<=100})
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(tree)
    return matches

def published_hid_profile(io):
    cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    get=io.hid.IOHIDDeviceGetProperty;get.argtypes=[C.c_void_p,C.c_void_p];get.restype=C.c_void_p
    number=cf.CFNumberGetValue;number.argtypes=[C.c_void_p,C.c_int,C.c_void_p];number.restype=C.c_bool
    datalen=cf.CFDataGetLength;datalen.argtypes=[C.c_void_p];datalen.restype=C.c_long
    data=cf.CFDataGetBytePtr;data.argtypes=[C.c_void_p];data.restype=C.c_void_p
    result={}
    for name in ['VendorID','VendorIDSource','ProductID','PrimaryUsagePage','PrimaryUsage','ReportDescriptor']:
        key=io.string(None,name.encode(),0x08000100)
        try:value=get(io.device,key)
        finally:io.release(key)
        if not value:continue
        if name=='ReportDescriptor':
            raw=C.string_at(data(value),datalen(value))
            result['descriptor_bytes']=len(raw);result['descriptor_sha256']=r.digest(raw)
        else:
            out=C.c_longlong()
            if number(value,4,C.byref(out)):result[name]=out.value # kCFNumberSInt64Type
    return result

def radio_profile(io):
    # BF config stores EEPROM pointer, uint16 length and cached SDP RAM pointer.
    config=io.read(0x202c6c,12)
    length=int.from_bytes(config[4:6],'little');cached=int.from_bytes(config[8:12],'little')
    valid=length==1053 and not cached&3 and 0x200000<=cached<=0x20ef00-length
    result={'firmware_SDP_bytes':length,'firmware_SDP_override_verified':False}
    if valid:result['firmware_SDP_override_verified']=r.digest(io.read(cached,length))==SDP_SHA
    slot=io.read(0xff00f000,1)[0]
    if slot<=2:result['active_pairing_slot']=slot+1
    return result

def verify(io,plan):
    if io.read(0x208f02,14)!=IDENTITY:raise ValueError('Expected Apple trial A87 identity')
    if r.digest(io.read(0x209014,572))!=EXTENSION_SHA:raise ValueError('A87 extension differs')
    if io.read(0x206aa8,4)!=bytes.fromhex('02f0d3fa'):raise ValueError('A87 constructor hook differs')
    battery=int.from_bytes(io.read(0x208ea8,4),'little')
    if battery&3 or not 0x209000<=battery<=0x20ef00-0x74:raise ValueError('A87 battery pointer invalid')
    table=int.from_bytes(io.read(battery,4),'little')
    if table&3 or not 0x209000<=table<=0x20ef00-152:raise ValueError('A87 shadow pointer invalid')
    if io.read(table,60)!=struct.pack('<15I',*METHODS):raise ValueError('A87 methods differ')
    if io.read(0x205e1c,4)!=struct.pack('<I',0x4000):raise ValueError('Expected current trial bank4000')
    if io.read(0xff000000,40)!=b'\0'+plan.new_ss[1:] or io.read(0xff000100,40)!=plan.backup_ss:
        raise ValueError('Apple trial rollback headers differ')
    internal=io.read(battery+0x14,1)[0]
    if internal>100:raise ValueError('Internal estimate invalid')
    address=io.read(battery+6,6)
    return {'A87_active':True,'extension_and_methods_verified':True,'trial_SS0_invalidated':True,
            'backup_SS100_selects_A86':True,'battery_estimate':internal,'firmware_writes':False},address

def main():
    if sys.argv[1:]not in ([],['--runtime-only']):raise ValueError('Use no arguments or --runtime-only; read-only')
    runtime_only=sys.argv[1:]==['--runtime-only']
    plan=a.Plan()
    with r.NativeHID(plan)as io:
        result,address=verify(io,plan)
        result.update(radio_profile(io))
        result['published_HID_profile']=published_hid_profile(io)
        # Runtime/header evidence is retained even if an optional host GET fails.
        filename='radio-apple-trial-runtime-only-verification.json' if runtime_only else 'radio-apple-trial-live-verification.json'
        target=r.ROOT/'artifacts/k2-initial-release'/filename
        result['direct_report_queries_skipped']=runtime_only
        target.write_text(json.dumps(result,indent=2)+'\n')
        reports=[] if runtime_only else [('Input90',0,0x90,3),('Feature34',2,0x34,77)]
        for key,kind,rid,n in reports:
            try:
                raw=get_report(io,kind,rid,n)
                if key=='Input90':
                    result[key]={'percent':raw[2],'status_flags':raw[1],'valid_percent':raw[2]<=100}
                else:result[key]={'bytes':len(raw),'version':raw[1],'address_matches':raw[4:10]==address}
            except (ValueError,RuntimeError,OSError)as error:
                result[key]={'error':str(error)}
                break
    output=subprocess.run(['/usr/sbin/ioreg','-a','-r','-c','AppleDeviceManagementHIDEventService'],capture_output=True,check=True)
    result['native_management_services']=native_battery_services(address,plistlib.loads(output.stdout))
    result['native_widget_visibility_verified']=False
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
