"""A88 -> A89 keyboard configuration via verified Apple raw maintenance interface.

Retains the same verified one-boot guard and A86 fallback. Default offline.
"""
import json
import struct
import types
import radio_installer as r
import radio_keyhole_trial as a
from apple_raw_hid import AppleRawHID

EXPECTED_CANDIDATE_SHA='84b9a586ae905ca57bebeebf2d1d6d1d1e14e94cb0a4c6c7a46a74781104f87d'
A88_EXTENSION_SHA='34b17627521810fc57a2fcfa0fb9646c4621cab971b3873f9736c2e32e48b346'
A88_IDENTITY=bytes.fromhex('b125880ac0023230323631303238')
A88_METHODS=(0x28a9,0x28dd,0x209291,0x20919b,0x209295,0x2949,0x296d,
             0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)

class Plan:
    def __init__(self):
        previous=a.Plan();expected=bytearray(previous.baseline)
        expected[0x4000:0x4000+len(previous.candidate)]=previous.candidate
        self.baseline=bytes(expected)
        self.active=previous.active;self.backup_ss=previous.backup_ss
        self.new_ss=previous.new_ss;self.current_ss=previous.current_ss
        self.candidate=(r.ROOT/'private/candidates/radio-keyboard-config-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate)!=16103 or r.digest(self.candidate)!=EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A89 keyboard configuration differs')
        r.records(self.candidate)
        self.ranges=((0,1),(0x4000,0x4000+len(self.candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'required_current_build':'A88 with verified Apple raw maintenance access',
                'same_physical_recovery_guard':True,'keyboard_Feature2_via_F1_added':True,
                'backup_header_original_and_A86_banks_preserved':True,
                'pairing_settings_and_SS0_body_never_written':True}

def maintenance_proof():
    a.maintenance_proof()

def guard_context(io):
    maintenance_proof()
    r.guard_context(io,expected_identity=A88_IDENTITY)
    if r.digest(io.read(0x209014,816))!=A88_EXTENSION_SHA:raise ValueError('Expected A88 extension')
    if io.read(0x206aa8,4)!=bytes.fromhex('02f0d3fa')or io.read(0x208d30,4)!=struct.pack('<I',0x20914b):
        raise ValueError('Expected A88 root hooks')
    battery=int.from_bytes(io.read(0x208ea8,4),'little')
    if battery&3 or not 0x209000<=battery<=0x20ef00-0x74:raise ValueError('A88 object pointer invalid')
    table=int.from_bytes(io.read(battery,4),'little')
    if table&3 or not 0x209000<=table<=0x20ef00-152:raise ValueError('A88 shadow pointer invalid')
    if io.read(table,60)!=struct.pack('<15I',*A88_METHODS):raise ValueError('A88 method table differs')
    if io.read(0x205e1c,4)!=struct.pack('<I',0x4000):raise ValueError('Expected A88 trial bank4000')

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
            self.journal.event(action='committed-and-verified',activation='watchdog-reset-then-A89-keyboard-configuration-trial')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Unknown write outcome possible; inspect journal before retry')
            raise

def runtime_view():
    def checked_plan():maintenance_proof();return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
             load_plan=checked_plan,NativeHID=AppleRawHID,guard_context=guard_context,Journal=r.Journal,
             Runner=Runner,RESULT_NAME='radio-keyboard-config-trial-flash-result.json')

if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
