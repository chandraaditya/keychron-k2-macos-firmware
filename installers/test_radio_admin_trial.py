"""Offline control-flow checks; fake HID and fake identity changes only."""
import contextlib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import radio_admin_trial as admin


class Tests(unittest.TestCase):
    def exercise(self,fail_drop=False,fail_guard=False):
        events=[];state={'uid':0,'gid':0};runtime=types.SimpleNamespace(EXPECTED_CANDIDATE_SHA='reviewed')
        runtime.load_plan=lambda:events.append('load-plan')or object()
        @contextlib.contextmanager
        def hid(plan,write,lock_owner_uid):
            self.assertTrue(write);self.assertEqual(lock_owner_uid,501)
            events.append('claim')
            try:yield object()
            finally:events.append('release')
        runtime.NativeHID=hid
        def guard(io):
            events.append('read-only-target-check')
            if fail_guard:raise RuntimeError('guard failed')
        runtime.guard_context=guard
        class Journal:
            def __init__(self,path):self.path=path;events.append('journal')
            def event(self,**data):events.append('journal-event')
            def close(self):events.append('close-journal')
        runtime.Journal=Journal
        class Runner:
            def __init__(self,*args):pass
            def run(self):
                self_outer.assertEqual(state,{'uid':501,'gid':20});events.append('run-update')
        self_outer=self;runtime.Runner=Runner
        def uid(value):
            events.append('setuid')
            if fail_drop:raise OSError('drop failed')
            state['uid']=value
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'artifacts/k2-initial-release').mkdir(parents=True)
            with patch.object(admin,'ROOT',root),patch.object(admin.os,'setgroups',lambda x:events.append('clear-groups')),patch.object(admin.os,'setgid',lambda x:state.update(gid=x)or events.append('setgid')),patch.object(admin.os,'setuid',uid),patch.object(admin.os,'getuid',lambda:state['uid']),patch.object(admin.os,'geteuid',lambda:state['uid']),patch.object(admin.os,'getgid',lambda:state['gid']):
                if fail_drop or fail_guard:
                    with self.assertRaises((OSError,RuntimeError)):admin.apply_trial(runtime,501,20)
                else:admin.apply_trial(runtime,501,20)
        return events
    def test_claim_release_then_permanent_drop_before_transaction(self):
        events=self.exercise()
        self.assertEqual(events[:5],['load-plan','claim','read-only-target-check','release','claim'])
        self.assertLess(events.index('clear-groups'),events.index('setuid'))
        self.assertLess(events.index('setuid'),events.index('journal'))
        self.assertLess(events.index('journal'),events.index('run-update'))
        self.assertEqual(events[-1],'release')
    def test_failed_privilege_drop_never_runs_update(self):
        events=self.exercise(fail_drop=True);self.assertNotIn('journal',events);self.assertNotIn('run-update',events)
        self.assertEqual(events[-1],'release')
    def test_failed_target_guard_releases_and_never_reopens(self):
        events=self.exercise(fail_guard=True);self.assertEqual(events.count('claim'),1)
        self.assertNotIn('setuid',events);self.assertNotIn('run-update',events);self.assertEqual(events[-1],'release')
    def test_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_installer.py').read_bytes()).hexdigest(),admin.EXPECTED_UPDATER_SHA)
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_rollback_preflight.py').read_bytes()).hexdigest(),admin.EXPECTED_ROLLBACK_PREFLIGHT_SHA)
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_wp_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_WP_TRIAL_SHA)
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_apple_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_APPLE_TRIAL_SHA)
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/apple_raw_hid.py').read_bytes()).hexdigest(),admin.EXPECTED_APPLE_RAW_SHA)
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_keyhole_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_KEYHOLE_TRIAL_SHA)
    def test_keyboard_config_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_keyboard_config_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_KEYBOARD_CONFIG_TRIAL_SHA)
    def test_mtu_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_mtu_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_MTU_TRIAL_SHA)
    def test_mtu_recovery_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_mtu_recovery.py').read_bytes()).hexdigest(),admin.EXPECTED_MTU_RECOVERY_SHA)
    def test_frow_trial_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_frow_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_FROW_TRIAL_SHA)
    def test_fn_trial_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_fn_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_FN_TRIAL_SHA)
    def test_c6_trial_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_c6_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_C6_TRIAL_SHA)
    def test_rearm_trial_source_pin_matches(self):
        self.assertEqual(hashlib.sha256((admin.ROOT/'installers/radio_rearm_trial.py').read_bytes()).hexdigest(),admin.EXPECTED_REARM_TRIAL_SHA)
    def test_unprivileged_cli_stops_before_open(self):
        if admin.os.geteuid()==0:self.skipTest('Owner-side refusal case requires non-root')
        result=subprocess.run(['/usr/bin/python3','-I',str(Path(admin.__file__)),'--apply'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertIn('no device opened',result.stderr)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report={'methods_run':result.testsRun,'passed':result.wasSuccessful(),'device_access':False,'privileged_execution':False,
            'admin_helper_sha256':hashlib.sha256(Path(admin.__file__).read_bytes()).hexdigest()}
    (admin.ROOT/'artifacts/k2-initial-release/radio-admin-helper-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
