"""One-shot owner-authorized trial: root only for HID claim, then permanent drop.

No updater capability is enabled in the default source on disk. No account,
permission database, lock ownership or security-setting changes are made.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_UPDATER_SHA='f2f0aacbdb101f76aab90b448fcdcd6fe88ca3f94ef0b6010d654b3ed91d47f6'
EXPECTED_PHASE1_INSTALLER_SHA='3ecec73dc044091c81b097bd64ac80153c113fc7b25e561a094b201375d2f08a'
EXPECTED_ROLLBACK_PREFLIGHT_SHA='e9067a73d2039f516ee175a6d2f7d9676605fc8b0424744fb9c9fc033e018555'
EXPECTED_WP_TRIAL_SHA='55a4689c111aef2bd134611c72f147957623dfb306aa74c4b9069c3f0ee8e197'
EXPECTED_APPLE_TRIAL_SHA='a85bb117b69e2cb2d064b83bc428b8ca7220b697b94e419984155c9d42ebfc8b'
EXPECTED_APPLE_RAW_SHA='29f27cdf8fd2c7d1f863b39863e42d42b585f30ad53539b23210a51f0a9045de'
EXPECTED_MTU_RECOVERY_SHA='5d03eb3a15149fa3e95bb90213d7718d109daabc049ee46c8a6f153d4db8f035'
EXPECTED_FROW_TRIAL_SHA='0377c5cfedd96333fffa36285ca9fbbb8c5d973d85322dd700a818df8fe3106e'
EXPECTED_FN_TRIAL_SHA='654fe4681b5065d7bdb9a1e204c1f6c205e37f731d1e47e65c76e9b6865097e3'
EXPECTED_C6_TRIAL_SHA='91da3f425cae7939317ab6a25c3f5eedc445dbf5a99b4c2c78fb74f73f9583e2'
EXPECTED_REARM_TRIAL_SHA='29eae9a92d741941b771d14a31e09ddc20219b5288b466c4a4a7a3731d5a75bf'
REARM_MODES={'--apply-rearm-trial':'install','--rearm-a93':'rearm-a93','--rearm':'rearm','--unarm':'unarm'}
EXPECTED_MTU_TRIAL_SHA='ca8d5f90bd7961eae6a8c8e192798de98e210ec6df3a111417a84d86fdf840ce'
EXPECTED_KEYBOARD_CONFIG_TRIAL_SHA='72a9ee54c88019652590bec7c538df4e6a970f7db21e79fe6327e49f8118eb01'
EXPECTED_KEYHOLE_TRIAL_SHA='0e7ae7b3cfc6e65fde14e1d1c25eadb09b918021072a5bcc237ac3d4674095a1'


def load_checked_module(name,path,expected_sha,owner_uid):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode)or info.st_uid!=owner_uid or info.st_mode&0o022:
        raise RuntimeError('Updater source ownership differs')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha:
        raise RuntimeError('Reviewed updater source differs; no device opened')
    # Use only checked bytes, without user-owned bytecode/project search paths.
    runtime=types.ModuleType(name);runtime.__file__=str(path)
    sys.modules[name]=runtime
    exec(compile(payload,str(path),'exec'),runtime.__dict__)
    return runtime


def apply_trial(runtime,owner_uid,owner_gid):
    runtime.ALLOW_HARDWARE_UPDATES=True
    plan=runtime.load_plan()
    # First prove privileged claim, target validation and release, without70.
    with runtime.NativeHID(plan,write=True,lock_owner_uid=owner_uid)as io:
        runtime.guard_context(io)
    print('Exclusive claim, read-only target check and release passed.',flush=True)
    with runtime.NativeHID(plan,write=True,lock_owner_uid=owner_uid)as io:
        # The reviewed HID connection is the only capability retained. Files,
        # backups and the transaction run as the normal owner, not as root.
        os.setgroups([]);os.setgid(owner_gid);os.setuid(owner_uid)
        if os.getuid()!=owner_uid or os.geteuid()!=owner_uid or os.getgid()!=owner_gid:
            raise RuntimeError('Privilege drop did not match owner; no updater enabled')
        if hasattr(io,'progress'):
            io.progress=lambda used,total:print(f'Read {used}/{total} bytes.',flush=True)
        folder=ROOT/'private/update-sessions'
        class ProgressJournal(runtime.Journal):
            def event(self,**data):
                super().event(**data)
                action=data.get('action')
                messages={'preflight-complete':'Fresh backup saved and preflight passed.',
                          'enabled':'Update enabled; writing and verifying.',
                          'ready-to-commit':'Full application verified; committing boot selection.',
                          'committed-and-verified':'Boot selection committed and verified.'}
                if action in messages:print(messages[action],flush=True)
                if action=='write-readback-verified':
                    before=getattr(self,'progress_bytes',0);self.progress_bytes=before+data['bytes']
                    if before//2048!=self.progress_bytes//2048:
                        print(f'Verified {self.progress_bytes} staged bytes.',flush=True)
        journal=ProgressJournal(folder/f'radio-{time.time_ns()}.jsonl')
        try:
            journal.event(action='exclusive-claim-verified-and-root-dropped',uid=os.getuid(),gid=os.getgid())
            runtime.Runner(io,plan,journal).run()
        finally:journal.close()
    result={'at_utc':datetime.now(timezone.utc).isoformat(),'owner_authorized':True,
            'EEPROM_transaction_returned_success':True,'application_startup_verified':False,
            'native_macos_UI_verified':False,'candidate_DS_sha256':runtime.EXPECTED_CANDIDATE_SHA,
            'exclusive_claim_verified':True,'root_dropped_before_backup_or_enable':True,
            'journal':str(journal.path.relative_to(ROOT))}
    result_name=getattr(runtime,'RESULT_NAME','radio-flash-result.json')
    (ROOT/'artifacts/k2-initial-release'/result_name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


def main():
    if sys.argv[1:]not in (['--apply'],['--apply-phase1'],['--apply-rollback-preflight'],['--apply-wp-trial'],['--apply-apple-trial'],['--apply-keyhole-trial'],['--apply-keyboard-config-trial'],['--apply-mtu-trial'],['--apply-mtu-recovery'],['--apply-frow-trial'],['--apply-fn-trial'],['--apply-c6-trial'])and not(len(sys.argv)==2 and sys.argv[1] in REARM_MODES):
        print('Usage: radio_admin_trial.py --apply|--apply-phase1|--apply-rollback-preflight|--apply-wp-trial|--apply-apple-trial|--apply-keyhole-trial|--apply-keyboard-config-trial|--apply-mtu-trial|--apply-mtu-recovery|--apply-frow-trial|--apply-fn-trial|--apply-c6-trial|--apply-rearm-trial|--rearm-a93|--rearm|--unarm',file=sys.stderr);return 2
    if not sys.flags.isolated:
        raise RuntimeError('Use the isolated system interpreter; no device opened')
    if os.getuid()!=0 or os.geteuid()!=0:
        raise RuntimeError('Administrator authentication is required; no device opened')
    owner=ROOT.stat();owner_uid=owner.st_uid;owner_gid=owner.st_gid
    if owner_uid==0 or owner.st_mode&0o022:
        raise RuntimeError('Expected non-root owner and no group/other write on project')
    # Preserve the same existing cooperative lock; never create a root-owned
    # replacement or silently change its ownership/permissions.
    for path,regular in ((ROOT/'private',False),(ROOT/'private/update-sessions',False),(ROOT/'private/read.lock',True)):
        info=path.lstat()
        if info.st_uid!=owner_uid or info.st_mode&0o077 or (not stat.S_ISREG(info.st_mode)if regular else not stat.S_ISDIR(info.st_mode)):
            raise RuntimeError('Private folder/lock ownership or permissions differ')
    runtime=load_checked_module('radio_installer',ROOT/'installers/radio_installer.py',EXPECTED_UPDATER_SHA,owner_uid)
    if sys.argv[1]=='--apply-phase1':
        repair=load_checked_module('radio_phase1_installer',ROOT/'installers/radio_phase1_installer.py',EXPECTED_PHASE1_INSTALLER_SHA,owner_uid)
        runtime.ALLOW_HARDWARE_UPDATES=True
        runtime=repair.runtime_view()
    elif sys.argv[1]=='--apply-rollback-preflight':
        preflight=load_checked_module('radio_rollback_preflight',ROOT/'installers/radio_rollback_preflight.py',EXPECTED_ROLLBACK_PREFLIGHT_SHA,owner_uid)
        runtime.ALLOW_HARDWARE_UPDATES=True
        runtime=preflight.runtime_view()
    elif sys.argv[1]=='--apply-wp-trial':
        load_checked_module('radio_rollback_preflight',ROOT/'installers/radio_rollback_preflight.py',EXPECTED_ROLLBACK_PREFLIGHT_SHA,owner_uid)
        corrected=load_checked_module('radio_wp_trial',ROOT/'installers/radio_wp_trial.py',EXPECTED_WP_TRIAL_SHA,owner_uid)
        runtime.ALLOW_HARDWARE_UPDATES=True
        runtime=corrected.runtime_view()
    elif sys.argv[1]=='--apply-apple-trial':
        load_checked_module('radio_rollback_preflight',ROOT/'installers/radio_rollback_preflight.py',EXPECTED_ROLLBACK_PREFLIGHT_SHA,owner_uid)
        load_checked_module('radio_wp_trial',ROOT/'installers/radio_wp_trial.py',EXPECTED_WP_TRIAL_SHA,owner_uid)
        apple=load_checked_module('radio_apple_trial',ROOT/'installers/radio_apple_trial.py',EXPECTED_APPLE_TRIAL_SHA,owner_uid)
        runtime.ALLOW_HARDWARE_UPDATES=True
        runtime=apple.runtime_view()
    elif sys.argv[1] in ('--apply-keyhole-trial','--apply-keyboard-config-trial','--apply-mtu-trial','--apply-mtu-recovery','--apply-frow-trial','--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
        load_checked_module('radio_rollback_preflight',ROOT/'installers/radio_rollback_preflight.py',EXPECTED_ROLLBACK_PREFLIGHT_SHA,owner_uid)
        load_checked_module('radio_wp_trial',ROOT/'installers/radio_wp_trial.py',EXPECTED_WP_TRIAL_SHA,owner_uid)
        load_checked_module('radio_apple_trial',ROOT/'installers/radio_apple_trial.py',EXPECTED_APPLE_TRIAL_SHA,owner_uid)
        load_checked_module('apple_raw_hid',ROOT/'installers/apple_raw_hid.py',EXPECTED_APPLE_RAW_SHA,owner_uid)
        keyhole=load_checked_module('radio_keyhole_trial',ROOT/'installers/radio_keyhole_trial.py',EXPECTED_KEYHOLE_TRIAL_SHA,owner_uid)
        runtime.ALLOW_HARDWARE_UPDATES=True
        runtime=keyhole.runtime_view()
        if sys.argv[1] in ('--apply-keyboard-config-trial','--apply-mtu-trial','--apply-mtu-recovery','--apply-frow-trial','--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
            keyboard=load_checked_module('radio_keyboard_config_trial',ROOT/'installers/radio_keyboard_config_trial.py',EXPECTED_KEYBOARD_CONFIG_TRIAL_SHA,owner_uid)
            runtime=keyboard.runtime_view()
            if sys.argv[1] in ('--apply-mtu-trial','--apply-mtu-recovery','--apply-frow-trial','--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
                mtu=load_checked_module('radio_mtu_trial',ROOT/'installers/radio_mtu_trial.py',EXPECTED_MTU_TRIAL_SHA,owner_uid)
                runtime=mtu.runtime_view()
                if sys.argv[1] in ('--apply-mtu-recovery','--apply-frow-trial','--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
                    recovery=load_checked_module('radio_mtu_recovery',ROOT/'installers/radio_mtu_recovery.py',EXPECTED_MTU_RECOVERY_SHA,owner_uid)
                    runtime=recovery.runtime_view()
                    if sys.argv[1] in ('--apply-frow-trial','--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
                        frow=load_checked_module('radio_frow_trial',ROOT/'installers/radio_frow_trial.py',EXPECTED_FROW_TRIAL_SHA,owner_uid)
                        runtime=frow.runtime_view()
                        if sys.argv[1] in ('--apply-fn-trial','--apply-c6-trial',*REARM_MODES):
                            fn=load_checked_module('radio_fn_trial',ROOT/'installers/radio_fn_trial.py',EXPECTED_FN_TRIAL_SHA,owner_uid)
                            runtime=fn.runtime_view()
                            if sys.argv[1] in ('--apply-c6-trial',*REARM_MODES):
                                c6=load_checked_module('radio_c6_trial',ROOT/'installers/radio_c6_trial.py',EXPECTED_C6_TRIAL_SHA,owner_uid)
                                runtime=c6.runtime_view()
                                if sys.argv[1] in REARM_MODES:
                                    rearm=load_checked_module('radio_rearm_trial',ROOT/'installers/radio_rearm_trial.py',EXPECTED_REARM_TRIAL_SHA,owner_uid)
                                    runtime=rearm.runtime_view(REARM_MODES[sys.argv[1]])
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    apply_trial(runtime,owner_uid,owner_gid)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
