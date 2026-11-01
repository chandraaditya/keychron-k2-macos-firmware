"""Explicit A86 -> A93 connection-interval trial; strict baseline, sparse writes, no retries.

Precondition: the keyboard was power-cycled after the A92 one-boot trial, so A86
runs from fallback 0x8000, SS0 is the invalidated header and bank 0x4000 holds
the exact A92 image committed by journal radio-1793184566954073000. Only bytes
that differ between A92 and A93 are written, then one activation byte. Planning,
AA-safe framing and resume tolerance are A91's (radio_frow_trial.Plan).
"""
import json
import types
import radio_installer as r
import radio_rollback_preflight as a86
import radio_mtu_recovery as previous
import radio_frow_trial as frow
import radio_fn_trial as fn

EXPECTED_CANDIDATE_SHA = '37db6e7de86a1a1bbce87b1d95c0efaea4be3f336897df7be2b8ec3d16446264'
A92_JOURNAL = r.ROOT / 'private/update-sessions/radio-1793184566954073000.jsonl'


def a92_install_proof():
    events = [json.loads(line) for line in A92_JOURNAL.read_text().splitlines()]
    backup = A92_JOURNAL.with_suffix('.eeprom.bin').read_bytes()
    record = next(event for event in events if event['action'] == 'fresh-backup-saved')
    if len(backup) != 65536 or r.digest(backup) != record['sha256']:
        raise ValueError('A92 pre-install backup differs')
    if [event for event in events if event['action'] == 'committed-and-verified'] != \
            [{'action': 'committed-and-verified', 'activation': fn.Plan.activation_label}]:
        raise ValueError('Expected exactly one committed A92 install')
    return backup


class Plan(frow.Plan):
    activation_label = 'watchdog-reset-then-A93-c6-trial'

    def __init__(self):
        a90 = previous.Plan()
        self.active = a90.active
        self.backup_ss = a90.backup_ss
        self.new_ss = a90.new_ss
        self.current_ss = a90.current_ss
        a92 = fn.Plan().candidate
        baseline = bytearray(a92_install_proof())
        baseline[0x4000:0x4000 + len(a92)] = a92
        baseline[0] = 0  # A92's guard invalidated SS0 on its startup.
        if bytes(baseline[:40]) != b'\0' + self.new_ss[1:]:
            raise ValueError('Expected invalidated A92 header')
        self.baseline = bytes(baseline)
        self.candidate = (r.ROOT / 'private/candidates/radio-c6-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate) != 16144 or r.digest(self.candidate) != EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A93 candidate differs')
        r.records(self.candidate)
        if 0x4000 + len(self.candidate) > 0x8000:
            raise ValueError('A93 exceeds inactive bank')
        for i in range(0, len(self.candidate), 16):
            if self.candidate[i:i + 16] == b'\xaa' * len(self.candidate[i:i + 16]):
                raise ValueError('A93 contains an unverifiable all-AA chunk')
        self._plan_from(self.baseline)

    def summary(self):
        return dict(super().summary(), candidate_sha256=EXPECTED_CANDIDATE_SHA)


def guard_context(io):
    a92_install_proof()
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


def runtime_view():
    def checked_plan():
        a92_install_proof()
        return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                 load_plan=checked_plan, NativeHID=previous.RecoveryHID,
                                 guard_context=guard_context, Journal=r.Journal,
                                 Runner=Runner, RESULT_NAME='radio-c6-trial-flash-result.json')


if __name__ == '__main__':
    print(json.dumps(Plan().summary(), indent=2))
