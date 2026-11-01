"""Explicit A86 -> A90 recovery trial; strict baseline, sparse writes, no retries.

Uses the reviewed unchanged A90 image. The three-second request alarm and
six-second conservative device-watchdog margin remain unchanged.
"""
import json
import ctypes as C
import struct
import time
import types
import radio_installer as r
import radio_rollback_preflight as a86
import radio_mtu_trial as previous
from apple_raw_hid import AppleRawHID

EXPECTED_CANDIDATE_SHA = previous.EXPECTED_CANDIDATE_SHA
EXPECTED_PATCH_RANGES = ((0x7666, 0x7667), (0x7edd, 0x7edf),
                         (0x7ee0, 0x7ee2), (0x7ee4, 0x7ee5),
                         (0x7ee6, 0x7ee8), (0x7ee9, 0x7eec),
                         (0x7eed, 0x7eee))


class Plan(previous.Plan):
    def __init__(self):
        super().__init__()
        changes = [0x4000 + i for i, value in enumerate(self.candidate)
                   if self.baseline[0x4000 + i] != value]
        spans = []
        for address in changes:
            if spans and address == spans[-1][1]:
                spans[-1][1] += 1
            else:
                spans.append([address, address + 1])
        self.patches = tuple(tuple(span) for span in spans)
        if self.patches != EXPECTED_PATCH_RANGES or len(changes) != 12:
            raise ValueError('Reviewed twelve-byte A90 transition differs')
        self.ranges = ((0, 1),) + self.patches

    def write_frame(self, offset, data):
        expected = (b'\1' if offset == 0 else
                    self.candidate[offset - 0x4000:offset - 0x4000 + len(data)])
        if data != expected:
            raise ValueError('Write data differs from exact reviewed transition')
        return r.Plan.write_frame(self, offset, data)

    def summary(self):
        return {'candidate_sha256': EXPECTED_CANDIDATE_SHA,
                'candidate_bytes': len(self.candidate), 'required_current_build': 'A86',
                'changed_application_bytes': 12, 'application_write_frames': 7,
                'activation_bytes': 1, 'same_verified_recovery_guard': True,
                'whole_image_and_protected_storage_verified_before_activation': True,
                'automatic_retry': False, 'request_alarm_seconds': 3,
                'watchdog_margin_seconds': 6}


def recovery_proof():
    previous.maintenance_proof()
    journal = r.ROOT / 'private/update-sessions/radio-1793176512582940000.jsonl'
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    backup = journal.with_suffix('.eeprom.bin').read_bytes()
    record = next(event for event in events if event['action'] == 'fresh-backup-saved')
    if len(backup) != 65536 or r.digest(backup) != record['sha256']:
        raise ValueError('Interrupted-session backup differs')
    if any(event.get('action') in ('ready-to-commit', 'committed-and-verified')
           for event in events):
        raise ValueError('Expected uncommitted interrupted update')
    plan = Plan()
    writes = [event for event in events if event['action'] == 'before-write']
    if not writes or writes[-1]['offset'] != 0x5f50 or writes[-1]['bytes'] != 14:
        raise ValueError('Interrupted session endpoint differs')
    for event in writes:
        start, length = event['offset'], event['bytes']
        if not 0x4000 <= start < start + length <= 0x4000 + len(plan.candidate):
            raise ValueError('Interrupted session touched an unexpected range')
        old = backup[start:start + length]
        new = plan.candidate[start - 0x4000:start - 0x4000 + length]
        if old != new or r.digest(new) != event['sha256']:
            raise ValueError('Interrupted prefix is not the reviewed unchanged data')


def guard_context(io):
    recovery_proof()
    a86.guard_context(io)
    plan = io.plan
    if io.read(0x205e1c, 4) != (0x8000).to_bytes(4, 'little'):
        raise ValueError('Expected A86 running from fallback8000')
    if io.read(0xff000000, 40) != b'\0' + plan.new_ss[1:] or \
       io.read(0xff000100, 40) != plan.backup_ss:
        raise ValueError('Expected invalid trial and intact A86 backup headers')


class RecoveryHID(AppleRawHID):
    """Accept the exact cached Apple raw interface or original B2 collection."""
    def _matches_diagnostic_device(self, device):
        return (super()._matches_diagnostic_device(device) or
                r.NativeHID._matches_diagnostic_device(self, device))

    def _enter(self):
        super()._enter()
        self.request_journal = None
        self.trace_context = None
        self.pending_read = None
        for name, operation in [('set_report', 'SET'), ('get_report', 'GET')]:
            original = getattr(self, name)
            def observed(*args, _original=original, _operation=operation):
                context = self.trace_context
                journal = self.request_journal
                if context is None or journal is None:
                    return _original(*args)
                detail = dict(context, operation=_operation, report_id=int(args[2]))
                setup = None
                if _operation == 'SET' and int(args[2]) == 0x71 and args[3] is not None and int(args[4]) == 8:
                    frame = C.string_at(args[3], 8)
                    setup = struct.unpack_from('<IH', frame, 1)
                    detail.update(read_address=hex(setup[0]), read_bytes=setup[1])
                elif _operation == 'GET' and int(args[2]) == 0x72 and self.pending_read is not None:
                    detail.update(read_address=hex(self.pending_read[0]), read_bytes=self.pending_read[1])
                started = time.monotonic()
                journal.event(action='native-request-start', **detail)
                result = _original(*args)
                if setup is not None and result == 0:
                    self.pending_read = setup
                journal.event(action='native-request-complete', **detail,
                              status=int(result) & 0xffffffff,
                              elapsed_seconds=time.monotonic() - started)
                return result
            setattr(self, name, observed)
        return self


class Runner(r.Runner):
    guard = staticmethod(guard_context)
    activation_label = 'watchdog-reset-then-A90-control-MTU-trial'

    def verify(self, offset, expected):
        context = getattr(self.io, 'trace_context', None)
        if context is None:
            self.io.trace_context = {'phase': 'verification', 'target_offset': offset,
                                     'target_bytes': len(expected)}
        try:
            super().verify(offset, expected)
        finally:
            self.io.trace_context = context

    def write(self, offset, data):
        frame = self.plan.write_frame(offset, data)
        self.journal.event(action='before-write', offset=offset, bytes=len(data),
                           sha256=r.digest(data))
        self.io.trace_context = {'phase': 'write', 'target_offset': offset,
                                 'target_bytes': len(data)}
        try:
            self.io.set(frame)
            self.io.trace_context = dict(self.io.trace_context, phase='write-readback')
            self.verify(offset, data)
            self.journal.event(action='write-readback-verified', offset=offset, bytes=len(data))
        finally:
            self.io.trace_context = None

    def run(self):
        self.io.request_journal = self.journal
        self.guard(self.io)
        fresh = self.io.read(0xff000000, 65536)
        self.journal.backup(fresh)
        try:
            self.plan.fresh_matches(fresh)
        except ValueError:
            self.journal.event(action='preflight-rejected', update_enabled=False,
                               fresh_capture_saved=True)
            raise
        self.journal.event(action='preflight-complete', **self.plan.summary())
        self.enable_attempted = True
        self.io.trace_context = {'phase': 'enable'}
        try:
            self.journal.event(action='before-enable', outcome_if_no_completion='unknown')
            self.io.set(b'\x70')
            self.enabled = True
            self.io.trace_context = None
            self.journal.event(action='enabled', expected_inactivity_reset_seconds=10)
            self.verify(0, b'\0' + self.plan.new_ss[1:])
            self.verify(0x100, self.plan.backup_ss)
            for start, end in self.plan.patches:
                self.write(start, self.plan.candidate[start - 0x4000:end - 0x4000])
            self.journal.event(action='full-readback-start')
            self.verify(0x4000, self.plan.candidate)
            self.verify(0x8000, self.plan.active)
            self.verify(0x100, self.plan.backup_ss)
            self.verify(0x3c0, fresh[0x3c0:0x39f3])
            self.verify(r.VS.start, fresh[r.VS])
            self.verify(0xf000, fresh[0xf000:])
            self.verify(0, b'\0' + self.plan.new_ss[1:])
            self.journal.event(action='ready-to-commit')
            self.write(0, b'\1')
            self.committed = True
            self.verify(0, self.plan.new_ss)
            self.verify(0x100, self.plan.backup_ss)
            self.journal.event(action='committed-and-verified',
                               activation=self.activation_label)
        except BaseException:
            self.journal.event(action='stopped', enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,
                               commit_readback_verified=self.committed,
                               warning='No retry; inspect request journal and live fallback')
            raise
        finally:
            self.io.trace_context = None


def runtime_view():
    def checked_plan():
        recovery_proof()
        return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                 load_plan=checked_plan, NativeHID=RecoveryHID,
                                 guard_context=guard_context, Journal=r.Journal,
                                 Runner=Runner, RESULT_NAME='radio-mtu-recovery-flash-result.json')


if __name__ == '__main__':
    print(json.dumps(Plan().summary(), indent=2))
