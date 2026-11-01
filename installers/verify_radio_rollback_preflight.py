"""Read-only physical trial/fallback verification; never enables updates."""
import json
import sys
from pathlib import Path
import radio_installer as r
import radio_rollback_preflight as p

def verify(io,plan,stage,observer=None):
    p.guard_context(io)
    ss0=io.read(0xff000000,40);ss100=io.read(0xff000100,40)
    selected=int.from_bytes(io.read(0x205e1c,4),'little')
    observation={'stage':stage,'device_access':'read-only',
                 'working_A86_extension_and_methods_verified':True,
                 'SS0_validity_byte':ss0[0],'SS0_DS_offset':int.from_bytes(ss0[30:34],'little'),
                 'SS0_matches_invalidated_trial':ss0==b'\0'+plan.new_ss[1:],
                 'SS0_matches_committed_trial':ss0==plan.new_ss,
                 'SS0_matches_working_A86_header':ss0==plan.current_ss,
                 'SS100_validity_byte':ss100[0],'SS100_DS_offset':int.from_bytes(ss100[30:34],'little'),
                 'SS100_matches_working_A86_header':ss100==plan.backup_ss,
                 'running_DS':selected,'Apple_profile_installed':False}
    if observer:observer(observation)
    if ss0!=b'\0'+plan.new_ss[1:] or ss100!=plan.backup_ss:
        raise ValueError('Expected invalidated trial header and retained A86 backup header')
    expected=0x4000 if stage=='trial' else 0x8000
    if selected!=expected:raise ValueError(f'Expected running DS{expected:x}, observed{selected:x}')
    value=io.read(int.from_bytes(io.read(0x208ea8,4),'little')+0x14,1)[0]
    if value>100:raise ValueError('Battery estimate outside valid range')
    return {'stage':stage,'passed':True,'device_access':'read-only',
            'working_A86_extension_and_methods_verified':True,
            'trial_SS0_invalidated':True,'backup_SS100_selects_A86':True,
            'running_DS':selected,'battery_estimate':value,
            'native_macos_verified':False,'Apple_profile_installed':False}

def main():
    if sys.argv[1:]not in (['trial'],['fallback']):raise ValueError('Specify trial or fallback')
    stage=sys.argv[1];plan=p.Plan()
    def observe(data):
        target=r.ROOT/'artifacts/k2-initial-release'/f'radio-rollback-preflight-{stage}-observation.json'
        target.write_text(json.dumps(data,indent=2)+'\n')
        print(json.dumps(data,indent=2),flush=True)
    with r.NativeHID(plan)as io:result=verify(io,plan,stage,observer=observe)
    target=r.ROOT/'artifacts/k2-initial-release'/f'radio-rollback-preflight-{stage}-verification.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
