"""Read-only A86 EEPROM mismatch capture. No update-enable/write capability.

Saves the first full capture before comparison. Re-reads changed32-byte blocks
as independent16-byte requests, checking the ROM's partial-I2C-read weakness.
Private captures contain addresses/pairings; stdout contains only ranges/counts.
"""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import stat
import sys
import time
import radio_installer as r
import radio_rollback_preflight as p

REGIONS=((0,0x28,'SS0'),(0x28,0x100,'SS0-padding'),(0x100,0x128,'SS100'),
         (0x128,0x1c0,'SS100-padding'),(0x1c0,0x3c0,'pairing-VS'),
         (0x3c0,0x39f3,'original-DS'),(0x39f3,0x4000,'original-DS-padding'),
         (0x4000,0x77f2,'inactive-A85'),(0x77f2,0x8000,'inactive-bank-padding'),
         (0x8000,0xb7f2,'active-A86'),(0xb7f2,0xf000,'upper-unused-or-unknown'),
         (0xf000,0x10000,'upper-metadata'))

def runs(offsets):
    result=[]
    for i in offsets:
        if result and result[-1][1]==i:result[-1][1]=i+1
        else:result.append([i,i+1])
    return [{'start':hex(a),'end_exclusive':hex(b),'bytes':b-a} for a,b in result]

def analyze(baseline,fresh):
    if len(baseline)!=65536 or len(fresh)!=65536:raise ValueError('Expected full64KiB captures')
    diff=[i for i,(a,b) in enumerate(zip(baseline,fresh)) if a!=b]
    outside=[i for i in diff if not r.VS.start<=i<r.VS.stop]
    summary=[]
    for a,b,label in REGIONS:
        changed=[i for i in diff if a<=i<b]
        if changed:summary.append({'region':label,'changed_bytes':len(changed),'ranges':runs(changed)})
    blocks=sorted({i//32*32 for i in outside})
    partial_aa=[]
    for a in blocks:
        data=fresh[a:a+32];old=baseline[a:a+32]
        if (data[:16]==old[:16] and data[16:]==b'\xaa'*16 and old[16:]!=b'\xaa'*16):
            partial_aa.append(hex(a))
    return {'changed_bytes':len(diff),'outside_pairing_changed_bytes':len(outside),
            'regions':summary,'suspected_second_half_AA_reads':partial_aa,
            'active_A86_DS_matches':fresh[0x8000:0xb7f2]==baseline[0x8000:0xb7f2],
            'original_DS_matches':fresh[0x3c0:0x39f3]==baseline[0x3c0:0x39f3],
            'SS0_matches':fresh[:40]==baseline[:40],
            'SS100_matches':fresh[0x100:0x128]==baseline[0x100:0x128]},blocks

def save(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())

def capture(io,plan,folder):
    p.guard_context(io)
    fresh=io.read(0xff000000,65536)
    # Preserve even a rejected capture, before equality checks or rereads.
    snapshot=folder/'eeprom-first.bin';save(snapshot,fresh)
    result,blocks=analyze(plan.baseline,fresh)
    result.update(at_utc=datetime.now(timezone.utc).isoformat(),firmware_writes=False,
                  update_enabled=False,baseline_sha256=r.digest(plan.baseline),
                  snapshot_sha256=r.digest(fresh),snapshot=str(snapshot),
                  reread_complete=False,reread_request_bytes=16)
    save(folder/'first-comparison.json',(json.dumps(result,indent=2)+'\n').encode())
    rereads=[]
    try:
        for a in blocks:
            data=io.read(0xff000000+a,16)+io.read(0xff000000+a+16,16)
            rereads.append({'offset':a,'hex':data.hex(),'matches_first':data==fresh[a:a+32],
                            'matches_baseline':data==plan.baseline[a:a+32]})
        result.update(reread_complete=True,reread_blocks=len(rereads),
                      rereads_matching_first=sum(x['matches_first'] for x in rereads),
                      rereads_matching_baseline=sum(x['matches_baseline'] for x in rereads),
                      all_changed_blocks_stable=all(x['matches_first'] for x in rereads),
                      all_changed_blocks_returned_to_baseline=bool(rereads) and all(x['matches_baseline'] for x in rereads))
    except BaseException as error:
        result['reread_error']=str(error)
        raise
    finally:
        save(folder/'rereads-private.json',(json.dumps(rereads,indent=2)+'\n').encode())
        save(folder/'result.json',(json.dumps(result,indent=2)+'\n').encode())
    return result

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments; this command is read-only')
    if os.geteuid()==0:raise ValueError('Run without sudo; administrator access is unnecessary')
    if r.ALLOW_HARDWARE_UPDATES:raise ValueError('Expected hardware updates disabled')
    plan=p.Plan();parent=r.ROOT/'private/radio-preflight-diagnostics'
    parent.mkdir(mode=0o700,exist_ok=True)
    info=parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('Diagnostic folder permissions differ')
    folder=parent/str(time.time_ns());folder.mkdir(mode=0o700)
    print('Reading only; updates remain disabled.',flush=True)
    with r.NativeHID(plan,write=False)as io:
        io.progress=lambda used,total:print(f'Read {used}/{total} bytes.',flush=True)
        result=capture(io,plan,folder)
    output={k:result[k] for k in ('firmware_writes','outside_pairing_changed_bytes',
             'active_A86_DS_matches','SS0_matches','SS100_matches',
             'suspected_second_half_AA_reads','reread_complete',
             'rereads_matching_first','rereads_matching_baseline','snapshot')}
    output['changed_regions']=[{'region':x['region'],'bytes':x['changed_bytes']} for x in result['regions']]
    print(json.dumps(output,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
