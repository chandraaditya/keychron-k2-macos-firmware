"""Explicit A86 -> A94 re-arm trial, and one-byte boot changes of a running A9x.

install: precondition A86 runs from fallback 0x8000, SS0 is the invalidated
header and bank 0x4000 holds the exact A93 image committed by journal
radio-1793457212404055000. Only bytes that differ between A93 and A94 are
written, then one activation byte (A91's sparse planning and framing).

A94 keeps the one-boot guard, then sets SS0 byte 0 back to 1 itself when the
host first reads the F1 keyboard configuration, so it survives power-off.

rearm-a93 / rearm / unarm: with A93 or A94 already running from bank 0x4000,
write only SS0 byte 0 (1 = boot the bank again, 0 = boot A86 from SS100).
reactivate: A86 runs from 0x8000 because an A94 boot died before re-arming (for
example a flat battery); bank 0x4000 still holds A94. Write only SS0 byte 0 = 1.
The bank must already hold the exact image. The updater's inactivity reset
then restarts the radio from the selected section.
"""
import json
import types
import radio_installer as r
import radio_rollback_preflight as a86
import radio_mtu_recovery as previous
import radio_frow_trial as frow
import radio_c6_trial as c6

EXPECTED_CANDIDATE_SHA = '3dd71d8deaecb23927423c9121a67ff5c5322de105c5f0a969519e53dbfd17c2'
A93_JOURNAL = r.ROOT / 'private/update-sessions/radio-1793457212404055000.jsonl'
IDENTITY = {0x93: bytes.fromhex('b125930ac0023230323631303238'),
            0x94: bytes.fromhex('b125940ac0023230323631303238')}


def a93_install_proof():
    events = [json.loads(line) for line in A93_JOURNAL.read_text().splitlines()]
    backup = A93_JOURNAL.with_suffix('.eeprom.bin').read_bytes()
    record = next(event for event in events if event['action'] == 'fresh-backup-saved')
    if len(backup) != 65536 or r.digest(backup) != record['sha256']:
        raise ValueError('A93 pre-install backup differs')
    if [event for event in events if event['action'] == 'committed-and-verified'] != \
            [{'action': 'committed-and-verified', 'activation': c6.Plan.activation_label}]:
        raise ValueError('Expected exactly one committed A93 install')
    return backup


class Plan(frow.Plan):
    activation_label = 'watchdog-reset-then-A94-rearm-trial'

    def __init__(self):
        a90 = previous.Plan()
        self.active = a90.active
        self.backup_ss = a90.backup_ss
        self.new_ss = a90.new_ss
        self.current_ss = a90.current_ss
        a93 = c6.Plan().candidate
        baseline = bytearray(a93_install_proof())
        baseline[0x4000:0x4000 + len(a93)] = a93
        baseline[0] = 0  # A93's guard invalidated SS0 on its startup.
        if bytes(baseline[:40]) != b'\0' + self.new_ss[1:]:
            raise ValueError('Expected invalidated A93 header')
        self.baseline = bytes(baseline)
        self.candidate = (r.ROOT / 'private/candidates/radio-rearm-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate) != 16364 or r.digest(self.candidate) != EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A94 candidate differs')
        r.records(self.candidate)
        if 0x4000 + len(self.candidate) > 0x8000:
            raise ValueError('A94 exceeds inactive bank')
        for i in range(0, len(self.candidate), 16):
            if self.candidate[i:i + 16] == b'\xaa' * len(self.candidate[i:i + 16]):
                raise ValueError('A94 contains an unverifiable all-AA chunk')
        self._plan_from(self.baseline)

    def summary(self):
        return dict(super().summary(), candidate_sha256=EXPECTED_CANDIDATE_SHA,
                    survives_power_off_after_host_keyboard_configuration_read=True)


def guard_context(io):
    a93_install_proof()
    a86.guard_context(io)
    plan = io.plan
    if io.read(0x205e1c, 4) != (0x8000).to_bytes(4, 'little'):
        raise ValueError('Expected A86 running from fallback8000')
    if io.read(0xff000000, 40) != b'\0' + plan.new_ss[1:] or \
       io.read(0xff000100, 40) != plan.backup_ss:
        raise ValueError('Expected invalid trial and intact A86 backup headers')


class Runner(previous.Runner):
    guard = staticmethod(guard_context)
    activation_label = Plan.activation_label


class BootBytePlan:
    """Only SS0 byte 0 of an installed A9x changes; the bank must already hold it."""
    ranges = ((0, 1),)
    patches = ()

    def __init__(self, image, version, value):
        self.image = image
        self.version = version
        self.value = value
        self.baseline = image.baseline
        self.candidate = image.candidate
        self.active = image.active
        self.new_ss = image.new_ss
        self.backup_ss = image.backup_ss
        self.activation_label = (f'watchdog-reset-then-A{version:x}-rearmed' if value else
                                 f'watchdog-reset-then-A86-unarmed-from-A{version:x}')

    def fresh_matches(self, fresh):
        if len(fresh) != 65536:
            raise ValueError('Unexpected EEPROM capture size')
        if fresh[0x4000:0x4000 + len(self.candidate)] != self.candidate:
            raise ValueError('Bank 4000 does not hold the exact reviewed image')
        if fresh[0] != 1 - self.value:
            raise ValueError('SS0 byte 0 is not in the expected starting state')
        state = bytearray(fresh)
        state[0] = 0
        self.image.fresh_matches(bytes(state))
        if self.image.patches:
            raise ValueError('EEPROM differs from the installed image')

    def write_frame(self, offset, data):
        if offset != 0 or data != bytes([self.value]):
            raise ValueError('Only the reviewed boot byte may be written')
        return r.Plan.write_frame(self, offset, data)

    def summary(self):
        return {'candidate_sha256': r.digest(self.candidate), 'running_build': f'A{self.version:x}',
                'application_write_frames': 0, 'boot_byte': self.value,
                'next_boot': 'bank 4000' if self.value else 'A86 from SS100',
                'activation_label': self.activation_label, 'automatic_retry': False}


def running_guard(version, armed):
    def guard(io):
        r.guard_context(io, expected_identity=IDENTITY[version])
        plan = io.plan
        if io.read(0x205e1c, 4) != (0x4000).to_bytes(4, 'little'):
            raise ValueError('Expected A9x running from bank 4000')
        ss0 = plan.new_ss if armed else b'\0' + plan.new_ss[1:]
        if io.read(0xff000000, 40) != ss0 or io.read(0xff000100, 40) != plan.backup_ss:
            raise ValueError('Expected trial header state and intact A86 backup header')
    return guard


class BootByteRunner(previous.Runner):
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
        value = self.plan.value
        try:
            self.journal.event(action='before-enable', outcome_if_no_completion='unknown')
            self.io.set(b'\x70')
            self.enabled = True
            self.io.trace_context = None
            self.journal.event(action='enabled', expected_inactivity_reset_seconds=10)
            self.verify(0, bytes([1 - value]) + self.plan.new_ss[1:])
            self.verify(0x100, self.plan.backup_ss)
            self.verify(0x4000, self.plan.candidate)
            self.verify(0x8000, self.plan.active)
            self.journal.event(action='ready-to-commit')
            self.write(0, bytes([value]))
            self.committed = True
            self.verify(0, bytes([value]) + self.plan.new_ss[1:])
            self.verify(0x100, self.plan.backup_ss)
            self.journal.event(action='committed-and-verified',
                               activation=self.plan.activation_label)
        except BaseException:
            self.journal.event(action='stopped', enable_attempted=self.enable_attempted,
                               enable_acknowledged=self.enabled,
                               commit_readback_verified=self.committed,
                               warning='No retry; inspect request journal and live state')
            raise
        finally:
            self.io.trace_context = None


MODES = {'rearm-a93': (0x93, 1), 'rearm': (0x94, 1), 'unarm': (0x94, 0), 'reactivate': (0x94, 1)}


def runtime_view(mode='install'):
    if mode == 'install':
        def checked_plan():
            a93_install_proof()
            return Plan()
        return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                     EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                     load_plan=checked_plan, NativeHID=previous.RecoveryHID,
                                     guard_context=guard_context, Journal=r.Journal,
                                     Runner=Runner, RESULT_NAME='radio-rearm-trial-flash-result.json')
    version, value = MODES[mode]
    guard = guard_context if mode == 'reactivate' else running_guard(version, armed=not value)

    def boot_byte_plan():
        return BootBytePlan(c6.Plan() if version == 0x93 else Plan(), version, value)

    class ModeRunner(BootByteRunner):
        pass
    ModeRunner.guard = staticmethod(guard)
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=(c6.EXPECTED_CANDIDATE_SHA if version == 0x93
                                                         else EXPECTED_CANDIDATE_SHA),
                                 load_plan=boot_byte_plan, NativeHID=previous.RecoveryHID,
                                 guard_context=guard, Journal=r.Journal, Runner=ModeRunner,
                                 RESULT_NAME=f'radio-{mode}-flash-result.json')


if __name__ == '__main__':
    print(json.dumps(Plan().summary(), indent=2))
