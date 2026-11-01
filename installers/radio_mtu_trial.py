"""A89 -> A90 control-channel size repair via verified Apple raw maintenance interface.

Retains the same verified one-boot guard and A86 fallback. Default offline.
"""
import json
import struct
import types
import radio_installer as r
import radio_keyboard_config_trial as a
from apple_raw_hid import AppleRawHID

EXPECTED_CANDIDATE_SHA='a700e0c2386c2e617fc26fcf7938fc7f94af61e322ad790d954953b4494535d6'
BASELINE_SHA='b0824a4b3c6195c9e510bcf8fa9fb3bfa057d6171c5977cfcb112058549574e5'
A89_EXTENSION_SHA='23469bcb877690b272ef87c2a2b8422bc16d1cc1f114ca19eedcdb5062c48eb9'
A89_IDENTITY=bytes.fromhex('b125890ac0023230323631303238')
A89_METHODS=(0x28a9,0x28dd,0x2092cf,0x2091a1,0x2092d3,0x2949,0x296d,
             0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

class Plan:
    def __init__(self):
        previous=a.Plan();expected=bytearray(previous.baseline)
        expected[0x4000:0x4000+len(previous.candidate)]=previous.candidate
        self.baseline=(r.ROOT/'private/bt-eeprom-A89-postpair-reviewed-64k.bin').read_bytes()
        if len(self.baseline)!=65536 or r.digest(self.baseline)!=BASELINE_SHA:
            raise ValueError('Reviewed post-pairing A89 snapshot differs')
        changed=[i for i,(x,y) in enumerate(zip(expected,self.baseline))
                 if x!=y and not r.VS.start<=i<r.VS.stop]
        if any(not 0xf001<=i<0xf027 for i in changed):
            raise ValueError('A89 baseline transition exceeds reviewed pairing slot')
        self.active=previous.active;self.backup_ss=previous.backup_ss
        self.new_ss=previous.new_ss;self.current_ss=previous.current_ss
        self.candidate=(r.ROOT/'private/candidates/radio-control-mtu-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate)!=16112 or r.digest(self.candidate)!=EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A90 MTU repair differs')
        r.records(self.candidate)
        self.ranges=((0,1),(0x4000,0x4000+len(self.candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'required_current_build':'A89 with verified Apple raw maintenance access',
                'same_physical_recovery_guard':True,'control_ceiling_128':True,
                'backup_header_original_and_A86_banks_preserved':True,
                'pairing_settings_and_SS0_body_never_written':True}

def maintenance_proof():
    a.maintenance_proof()
    proof=json.loads((r.ROOT/'artifacts/k2-initial-release/A89-postpairing-backup-review.json').read_text())
    if not (proof.get('A89_active') is True and proof.get('sha256')==BASELINE_SHA and
            proof.get('changed_outside_VS_limited_to_repaired_slot0') is True and
            proof.get('changed_chunks_stable') is True and proof.get('protected_code_and_headers_match') is True):
        raise ValueError('A89 post-pairing read-only backup proof differs')

def guard_context(io):
    maintenance_proof()
    r.guard_context(io,expected_identity=A89_IDENTITY)
    if r.digest(io.read(0x209014,892))!=A89_EXTENSION_SHA:raise ValueError('Expected A89 extension')
    if io.read(0x206aa8,4)!=bytes.fromhex('02f0d3fa')or io.read(0x208d30,4)!=struct.pack('<I',0x20914b):
        raise ValueError('Expected A89 root hooks')
    battery=int.from_bytes(io.read(0x208ea8,4),'little')
    if battery&3 or not 0x209000<=battery<=0x20ef00-0x74:raise ValueError('A89 object pointer invalid')
    table=int.from_bytes(io.read(battery,4),'little')
    if table&3 or not 0x209000<=table<=0x20ef00-152:raise ValueError('A89 shadow pointer invalid')
    if io.read(table,60)!=struct.pack('<15I',*A89_METHODS):raise ValueError('A89 method table differs')
    if io.read(0x205e1c,4)!=struct.pack('<I',0x4000):raise ValueError('Expected A89 trial bank4000')

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
            self.verify(0,b'\0'+self.plan.new_ss[1:]);self.verify(0x100,self.plan.backup_ss)
            self.block(0x4000,self.plan.candidate);self.verify(0x4000,self.plan.candidate)
            self.verify(0x8000,self.plan.active);self.verify(0x100,self.plan.backup_ss)
            self.verify(0x3c0,fresh[0x3c0:0x39f3]);self.verify(r.VS.start,fresh[r.VS])
            self.verify(0xf000,fresh[0xf000:]);self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.backup_ss)
            self.journal.event(action='committed-and-verified',activation='watchdog-reset-then-A90-control-MTU-trial')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Unknown write outcome possible; inspect journal before retry')
            raise

def runtime_view():
    def checked_plan():maintenance_proof();return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
             load_plan=checked_plan,NativeHID=AppleRawHID,guard_context=guard_context,Journal=r.Journal,
             Runner=Runner,RESULT_NAME='radio-control-mtu-trial-flash-result.json')

if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
