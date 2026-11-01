"""A86 -> one-boot A86 rollback trial. No Apple profile and no default writes.

Preserves active A86 DS8000 and original DS3C0. Replaces failed inactive A85
DS4000; sets backup SS100 to working A86 before activating the guarded trial.
"""
from pathlib import Path
import json
import struct
import types
import radio_installer as r

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_CANDIDATE_SHA='efdfece539163056d3f9e2314471c61000fb92ad7da8a63a26fe668b27450bf2'
EXPECTED_INSTALLED_BACKUP_SHA='767dd6fe973c11aa6be53c204cb52330c6b2f78be6bfcb7d31c74bac53afe840'
HISTORICAL_INSTALLED_BACKUP_SHA='cde4157a285d53590e828f8c39b845bb0253f71419fd360748de829b39d9a740'
EXPECTED_ACTIVE_SHA='272c7f60a926c65dab10685375aadbb94bc1ddaff88ebfedaa00e84dcd69be3f'
EXPECTED_EXTENSION_SHA='6f6f744b898e9787c0d7edab6077a71c73a5087bfdbf3e925dc95657523b33f8'
IDENTITY=bytes.fromhex('b125860ac0023230323631303238')

class Plan:
    def __init__(self):
        self.baseline=(ROOT/'private/bt-eeprom-A86-preflight-reviewed-64k.bin').read_bytes()
        if len(self.baseline)!=65536 or r.digest(self.baseline)!=EXPECTED_INSTALLED_BACKUP_SHA:
            raise ValueError('Reviewed installed A86 backup differs')
        historical=(ROOT/'private/bt-eeprom-installed-A86-64k.bin').read_bytes()
        if r.digest(historical)!=HISTORICAL_INSTALLED_BACKUP_SHA:
            raise ValueError('Historical A86 backup differs')
        changes=[i for i,(a,b) in enumerate(zip(historical,self.baseline)) if a!=b]
        outside=[i for i in changes if not r.VS.start<=i<r.VS.stop]
        if len(outside)!=26 or any(not 0xf027<=i<0xf04d for i in outside):
            raise ValueError('Reviewed baseline transition exceeds the second Bluetooth slot')
        self.candidate=(ROOT/'private/candidates/radio-rollback-preflight/dynamic-section.bin').read_bytes()
        if len(self.candidate)!=14528 or r.digest(self.candidate)!=EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed guarded preflight differs')
        r.records(self.candidate)
        self.active=self.baseline[0x8000:0xb7f2]
        if r.digest(self.active)!=EXPECTED_ACTIVE_SHA:raise ValueError('Retained A86 differs')
        self.current_ss=self.baseline[:40]
        if self.current_ss[0]!=1 or struct.unpack_from('<IIH',self.current_ss,30)!=(0x8000,0x1c0,0x200):
            raise ValueError('Installed boot selection differs')
        self.backup_ss=self.current_ss
        new=bytearray(self.current_ss);struct.pack_into('<I',new,30,0x4000);self.new_ss=bytes(new)
        self.ranges=((0,40),(0x100,0x128),(0x4000,0x4000+len(self.candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'required_current_build':'A86/20261028','inactive_DS_start':0x4000,
                'retained_working_DS_start':0x8000,'backup_SS_target':0x8000,
                'changes_apple_identity_or_reports':False,'requires_physical_power_cycle_check':True,
                'boot_guard':'SS0 invalidated and read back before remaining DS loads',
                'physical_bus_failure_recovery_guaranteed':False,'live_VS_preserved':True}

def guard_context(io):
    r.guard_context(io,expected_identity=IDENTITY)
    if r.digest(io.read(0x209014,440))!=EXPECTED_EXTENSION_SHA:
        raise ValueError('Working A86 extension differs')
    if io.read(0x206aa8,4)!=bytes.fromhex('02f0d3fa'):
        raise ValueError('Working A86 hook differs')
    battery=int.from_bytes(io.read(0x208ea8,4),'little')
    if battery&3 or not 0x209000<=battery<=0x20ef00-0x74:raise ValueError('Battery object invalid')
    table=int.from_bytes(io.read(battery,4),'little')
    if table&3 or not 0x209000<=table<=0x20ef00-68:raise ValueError('Shadow table invalid')
    expected=(0x28a9,0x28dd,0x209141,0x209119,0x209145,0x2949,0x296d,
              0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1)
    if io.read(table,60)!=struct.pack('<15I',*expected):raise ValueError('Working A86 methods differ')

class Runner(r.Runner):
    def run(self):
        guard_context(self.io)
        fresh=self.io.read(0xff000000,65536)
        self.journal.backup(fresh)
        try:self.plan.fresh_matches(fresh)
        except ValueError:
            self.journal.event(action='preflight-rejected',reason='EEPROM comparison differs',
                               update_enabled=False,fresh_capture_saved=True)
            raise
        self.journal.event(action='preflight-complete',fresh_backup_sha256=r.digest(fresh),**self.plan.summary())
        self.journal.event(action='before-enable',outcome_if_no_completion='unknown; timer may be armed')
        self.enable_attempted=True
        try:
            self.io.set(b'\x70');self.enabled=True
            self.journal.event(action='enabled',expected_inactivity_reset_seconds=10)
            self.block(0x4000,self.plan.candidate);self.verify(0x4000,self.plan.candidate)
            self.verify(0x8000,self.plan.active)
            # Current SS0 still selects A86 while backup SS100 is replaced.
            self.write(0x100,b'\0');self.block(0x101,self.plan.backup_ss[1:])
            self.verify(0x100,b'\0'+self.plan.backup_ss[1:]);self.write(0x100,b'\1')
            self.verify(0x100,self.plan.backup_ss);self.verify(0,self.plan.current_ss)
            self.verify(0x3c0,fresh[0x3c0:0x39f3]);self.verify(r.VS.start,fresh[r.VS])
            self.verify(0x8000,self.plan.active);self.verify(0xf000,fresh[0xf000:])
            # SS0 activation is last; either selectable bank is complete.
            self.write(0,b'\0');self.block(1,self.plan.new_ss[1:])
            self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.verify(0x4000,self.plan.candidate);self.verify(0x100,self.plan.backup_ss)
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.backup_ss)
            self.verify(r.VS.start,fresh[r.VS])
            self.journal.event(action='committed-and-verified',activation='watchdog-reset-then-one-boot-A86')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,commit_readback_verified=self.committed,
                               warning='Unknown write outcome possible; inspect journal before retry')
            raise

def runtime_view():
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
             load_plan=Plan,NativeHID=r.NativeHID,guard_context=guard_context,Journal=r.Journal,
             Runner=Runner,RESULT_NAME='radio-rollback-preflight-flash-result.json')

if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
