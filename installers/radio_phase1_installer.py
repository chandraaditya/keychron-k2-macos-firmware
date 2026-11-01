"""Exact A85 inactive-patch -> corrected A86 staging plan. File-only by default.

Preserves original DS3C0, original backup SS100, A85 DS4000 and live pairings.
Only SS0 and the previously empty DS8000 slot may be written.
"""
from pathlib import Path
import json
import struct
import types

import radio_installer as r

ROOT=Path(__file__).resolve().parents[1]
NEW_START=0x8000
EXPECTED_CANDIDATE_SHA='272c7f60a926c65dab10685375aadbb94bc1ddaff88ebfedaa00e84dcd69be3f'
DS=ROOT/'private/candidates/radio-battery-phase1/dynamic-section.bin'
IDENTITY=bytes.fromhex('b125850ac0023230323631303237')


class Plan:
    def __init__(self):
        initial=r.load_plan();candidate=DS.read_bytes()
        if len(candidate)!=14322 or r.digest(candidate)!=EXPECTED_CANDIDATE_SHA:raise ValueError('Corrected candidate differs')
        r.records(candidate)
        if initial.baseline[NEW_START:NEW_START+len(candidate)]!=b'\xff'*len(candidate):raise ValueError('New inactive bank was not the reviewed all-FF erased region')
        expected=bytearray(initial.baseline)
        expected[:40]=initial.new_ss;expected[0x100:0x128]=initial.old_ss
        expected[0x4000:0x4000+len(initial.candidate)]=initial.candidate
        self.baseline=bytes(expected);self.candidate=candidate
        self.old_ss=initial.old_ss;self.current_ss=initial.new_ss
        new=bytearray(initial.old_ss);struct.pack_into('<I',new,30,NEW_START);self.new_ss=bytes(new)
        self.retained_candidate=initial.candidate
        self.ranges=((0,40),(NEW_START,NEW_START+len(candidate)))
    write_frame=r.Plan.write_frame
    fresh_matches=r.Plan.fresh_matches
    def summary(self):
        return {'candidate_sha256':EXPECTED_CANDIDATE_SHA,'candidate_bytes':len(self.candidate),
                'inactive_DS_start':NEW_START,'inactive_DS_end_exclusive':NEW_START+len(self.candidate),
                'original_SS100_preserved_without_writes':True,'original_DS3C0_and_A85_DS4000_preserved':True,
                'live_VS_preserved':True,'ordinary_write_chunk_max':14,'software_boundary':16,
                'physical_page_bytes':128,'nominal_inactivity_reset_seconds':10,
                'activation':'Watchdog full-reset boot after activity stops; no direct LAUNCH',
                'automatic_crashing_DS_rollback':False,'required_current_build':'A85/20261027'}


def guard_context(io):
    r.guard_context(io,expected_identity=IDENTITY)
    if io.read(0x206aa8,4)!=bytes.fromhex('01f06afc') or io.read(0x201350,4)!=struct.pack('<I',0x209014):
        raise ValueError('Expected inactive A85 patch and original arena')
    pointer=int.from_bytes(io.read(0x208ea8,4),'little')
    if pointer&3 or not 0x209000<=pointer<=0x20ef00-0x74 or io.read(pointer,4)!=struct.pack('<I',0x4c2f4):
        raise ValueError('Expected original battery methods still active')


class Runner(r.Runner):
    def run(self):
        guard_context(self.io)
        fresh=self.io.read(0xff000000,65536);self.plan.fresh_matches(fresh)
        self.journal.backup(fresh)
        self.journal.event(action='preflight-complete',fresh_backup_sha256=r.digest(fresh),**self.plan.summary())
        self.journal.event(action='before-enable',outcome_if_no_completion='unknown; timer may be armed')
        self.enable_attempted=True
        try:
            self.io.set(b'\x70');self.enabled=True
            self.journal.event(action='enabled',expected_inactivity_reset_seconds=10)
            # Existing SS100 already selects the original application. It is
            # never rewritten or invalidated by this repair.
            self.verify(0x100,self.plan.old_ss)
            self.block(NEW_START,self.plan.candidate);self.verify(NEW_START,self.plan.candidate)
            self.verify(0x3c0,self.plan.baseline[0x3c0:0x39f3])
            self.verify(0x4000,self.plan.retained_candidate)
            self.verify(r.VS.start,fresh[r.VS]);self.verify(0xf000,fresh[0xf000:])
            self.verify(0x100,self.plan.old_ss)
            self.write(0,b'\0');self.block(1,self.plan.new_ss[1:])
            self.verify(0,b'\0'+self.plan.new_ss[1:])
            self.verify(NEW_START,self.plan.candidate);self.verify(0x100,self.plan.old_ss)
            self.journal.event(action='ready-to-commit')
            self.write(0,b'\1');self.committed=True
            self.verify(0,self.plan.new_ss);self.verify(0x100,self.plan.old_ss)
            self.verify(r.VS.start,fresh[r.VS])
            self.journal.event(action='committed-and-verified',activation='expected-watchdog-full-reset',target='A86/20261028')
        except BaseException:
            self.journal.event(action='stopped',enable_attempted=self.enable_attempted,enable_acknowledged=self.enabled,
                               commit_readback_verified=self.committed,
                               warning='Write may have happened; timer may reset radio. Inspect journal before retry.')
            raise


def runtime_view():
    # The privileged helper separately enables the base module's native gate
    # after source verification. No CLI in this module can enable hardware.
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                 load_plan=Plan,NativeHID=r.NativeHID,guard_context=guard_context,
                                 Journal=r.Journal,Runner=Runner,RESULT_NAME='radio-phase1-flash-result.json')


if __name__=='__main__':print(json.dumps(Plan().summary(),indent=2))
