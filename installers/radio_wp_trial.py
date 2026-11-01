"""Failed neutral prefix -> corrected WP-aware neutral prefix; default offline.

Invalidate current SS0 BEFORE changing its DS4000. Retain SS100/A86 DS8000,
original DS and pairing/settings. Final activation changes only SS0 byte0.
"""
import json
import struct
import types
import radio_installer as r
import radio_rollback_preflight as p

EXPECTED_CANDIDATE_SHA='9994716588b3c9309c219c807d6c99fb797341d8229077d59c5ab64c27b2d5ff'

class Plan:
    def __init__(self):
        old=p.Plan()
        # The previous transaction's exact read-back-verified completed state.
        expected=bytearray(old.baseline)
        expected[0x4000:0x4000+len(old.candidate)]=old.candidate
        expected[:40]=old.new_ss;expected[0x100:0x128]=old.backup_ss
        self.baseline=bytes(expected)
        self.active=old.active;self.backup_ss=old.backup_ss;self.new_ss=old.new_ss
        self.current_ss=old.current_ss
        self.candidate=(r.ROOT/'private/candidates/radio-rollback-wp/dynamic-section.bin').read_bytes()
        if len(self.candidate)!=14595 or r.digest(self.candidate)!=EXPECTED_CANDIDATE_SHA:
            raise ValueError('Corrected write-protect candidate differs')
        r.records(self.candidate)
        # No backup header, settings, original/working bank or SS0-body writes.
        self.ranges=((0,1),(0x4000,0x4000+len(self.candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'required_current_build':'A86-fallback-from-failed-neutral-prefix',
                'retained_working_DS':0x8000,'backup_SS100_never_written':True,
                'SS0_body_never_written':True,'SS0_invalidated_before_staging':True,
                'changes_apple_identity_or_reports':False,
                'exact_original_A7_before_guard':True,'original_GPIO_callback_brackets_write':True,
                'live_VS_and_metadata_preserved':True,'physical_power_cycle_check_required':True}

def guard_context(io):
    p.guard_context(io)
    if io.read(0x205e1c,4)!=struct.pack('<I',0x8000):
        raise ValueError('Expected known A86 fallback currently running')

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
            # Bank4000 is selected by a valid header, even while A86 runs from
            #8000. Make the verified backup the sole selection before staging.
            self.verify(0x100,self.plan.backup_ss);self.verify(0x8000,self.plan.active)
            self.write(0,b'\0');self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.block(0x4000,self.plan.candidate);self.verify(0x4000,self.plan.candidate)
            self.verify(0x100,self.plan.backup_ss);self.verify(0x8000,self.plan.active)
            self.verify(0x3c0,fresh[0x3c0:0x39f3]);self.verify(r.VS.start,fresh[r.VS])
            self.verify(0xf000,fresh[0xf000:]);self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.backup_ss)
            self.journal.event(action='committed-and-verified',activation='watchdog-reset-then-WP-neutral-trial')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Unknown write outcome possible; inspect journal before retry')
            raise

def runtime_view():
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
             load_plan=Plan,NativeHID=r.NativeHID,guard_context=guard_context,Journal=r.Journal,
             Runner=Runner,RESULT_NAME='radio-wp-trial-flash-result.json')

if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
