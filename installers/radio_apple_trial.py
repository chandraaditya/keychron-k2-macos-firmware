"""One-boot Apple profile from physically verified neutral recovery fallback.

Default has no hardware capability. Requires both neutral physical checks;
only DS4000 and the SS0 activation byte can change. A86 fallback is retained.
"""
import json
import struct
import types
import radio_installer as r
import radio_wp_trial as wp
import radio_rollback_preflight as p

EXPECTED_CANDIDATE_SHA='a9e1a7af26709794e3023518e0f192f60c0c8dbfe72ce4c9f4ba93715ffdb7a6'

def physical_recovery_verified():
    for stage,bank in [('trial',0x4000),('fallback',0x8000)]:
        path=r.ROOT/'artifacts/k2-initial-release'/f'radio-wp-{stage}-verification.json'
        if not path.exists():raise ValueError(f'Physical WP {stage} verification is missing')
        result=json.loads(path.read_text())
        if not (result.get('passed') is True and result.get('corrected_WP_trial') is True and
                result.get('candidate_DS_sha256')==wp.EXPECTED_CANDIDATE_SHA and
                result.get('stage')==stage and result.get('running_DS')==bank and
                result.get('trial_SS0_invalidated') is True and
                result.get('backup_SS100_selects_A86') is True and
                result.get('working_A86_extension_and_methods_verified') is True):
            raise ValueError(f'Physical WP {stage} verification did not pass exact checks')

class Plan:
    def __init__(self):
        previous=wp.Plan()
        expected=bytearray(previous.baseline)
        expected[0x4000:0x4000+len(previous.candidate)]=previous.candidate
        expected[0]=0  # Expected after successful neutral invalidation.
        self.baseline=bytes(expected)
        self.active=previous.active;self.backup_ss=previous.backup_ss
        self.new_ss=previous.new_ss;self.current_ss=previous.current_ss
        self.candidate=(r.ROOT/'private/candidates/radio-apple-wp-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate)!=15783 or r.digest(self.candidate)!=EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed Apple one-boot candidate differs')
        r.records(self.candidate)
        self.ranges=((0,1),(0x4000,0x4000+len(self.candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'required_current_build':'A86-after-verified-neutral-power-cycle',
                'changes_apple_identity_and_descriptor':True,'one_boot_trial':True,
                'backup_SS100_and_A86_DS8000_never_written':True,
                'SS0_body_pairings_and_metadata_never_written':True,
                'same_corrected_guard_as_neutral_trial':True,
                'native_macos_display_verified':False}

def guard_context(io):
    physical_recovery_verified()
    p.guard_context(io)
    if io.read(0x205e1c,4)!=struct.pack('<I',0x8000):
        raise ValueError('Expected A86 running after physical fallback check')

class Runner(r.Runner):
    def run(self):
        guard_context(self.io)
        fresh=self.io.read(0xff000000,65536);self.journal.backup(fresh)
        try:self.plan.fresh_matches(fresh)
        except ValueError:
            self.journal.event(action='preflight-rejected',update_enabled=False,fresh_capture_saved=True)
            raise
        self.journal.event(action='preflight-complete',fresh_backup_sha256=r.digest(fresh),**self.plan.summary())
        self.journal.event(action='before-enable',outcome_if_no_completion='unknown; timer may be armed')
        self.enable_attempted=True
        try:
            self.io.set(b'\x70');self.enabled=True
            self.journal.event(action='enabled',expected_inactivity_reset_seconds=10)
            # The verified SS0 is already invalid, so interrupted staging
            # continues to select the untouched known working backup bank.
            self.verify(0,b'\0'+self.plan.new_ss[1:]);self.verify(0x100,self.plan.backup_ss)
            self.block(0x4000,self.plan.candidate);self.verify(0x4000,self.plan.candidate)
            self.verify(0x8000,self.plan.active);self.verify(0x100,self.plan.backup_ss)
            self.verify(0x3c0,fresh[0x3c0:0x39f3]);self.verify(r.VS.start,fresh[r.VS])
            self.verify(0xf000,fresh[0xf000:]);self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.backup_ss)
            self.journal.event(action='committed-and-verified',activation='watchdog-reset-then-one-boot-Apple-profile')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Unknown write outcome possible; inspect journal before retry')
            raise

def runtime_view():
    def checked_plan():
        physical_recovery_verified()
        return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
             load_plan=checked_plan,NativeHID=r.NativeHID,guard_context=guard_context,Journal=r.Journal,
             Runner=Runner,RESULT_NAME='radio-apple-trial-flash-result.json')

if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
