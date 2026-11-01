"""Explicit A86 -> A92 Fn-translation trial; strict baseline, sparse writes, no retries.

Precondition: the keyboard was power-cycled after the A91 one-boot trial, so A86
runs from fallback 0x8000, SS0 is the invalidated header and bank 0x4000 holds
the exact A91 image committed by journal radio-1793183520453584000. Only bytes
that differ between A91 and A92 are written, then one activation byte. Planning,
AA-safe framing and resume tolerance are A91's (radio_frow_trial.Plan).
"""
import json
import types
import radio_installer as r
import radio_rollback_preflight as a86
import radio_mtu_recovery as previous
import radio_frow_trial as frow

EXPECTED_CANDIDATE_SHA = 'b2d13ebfc4358f38e71a3f9b88f9fc0c403aebe89d59454d4eea114803fe0f73'
A91_JOURNAL = r.ROOT / 'private/update-sessions/radio-1793183520453584000.jsonl'


def a91_install_proof():
    events = [json.loads(line) for line in A91_JOURNAL.read_text().splitlines()]
    backup = A91_JOURNAL.with_suffix('.eeprom.bin').read_bytes()
    record = next(event for event in events if event['action'] == 'fresh-backup-saved')
    if len(backup) != 65536 or r.digest(backup) != record['sha256']:
        raise ValueError('A91 pre-install backup differs')
    if [event for event in events if event['action'] == 'committed-and-verified'] != \
            [{'action': 'committed-and-verified', 'activation': frow.Plan.activation_label}]:
        raise ValueError('Expected exactly one committed A91 install')
    return backup


class Plan(frow.Plan):
    activation_label = 'watchdog-reset-then-A92-fn-trial'

    def __init__(self):
        a90 = previous.Plan()
        self.active = a90.active
        self.backup_ss = a90.backup_ss
        self.new_ss = a90.new_ss
        self.current_ss = a90.current_ss
        a91 = frow.Plan().candidate
        baseline = bytearray(a91_install_proof())
        baseline[0x4000:0x4000 + len(a91)] = a91
        baseline[0] = 0  # A91's guard invalidated SS0 on its startup.
        if bytes(baseline[:40]) != b'\0' + self.new_ss[1:]:
            raise ValueError('Expected invalidated A91 header')
        self.baseline = bytes(baseline)
        self.candidate = (r.ROOT / 'private/candidates/radio-fn-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate) != 16136 or r.digest(self.candidate) != EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A92 candidate differs')
        r.records(self.candidate)
        if 0x4000 + len(self.candidate) > 0x8000:
            raise ValueError('A92 exceeds inactive bank')
        for i in range(0, len(self.candidate), 16):
            if self.candidate[i:i + 16] == b'\xaa' * len(self.candidate[i:i + 16]):
                raise ValueError('A92 contains an unverifiable all-AA chunk')
        self._plan_from(self.baseline)

    def summary(self):
        return dict(super().summary(), candidate_sha256=EXPECTED_CANDIDATE_SHA)


def guard_context(io):
    a91_install_proof()
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
        a91_install_proof()
        return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                 load_plan=checked_plan, NativeHID=previous.RecoveryHID,
                                 guard_context=guard_context, Journal=r.Journal,
                                 Runner=Runner, RESULT_NAME='radio-fn-trial-flash-result.json')


if __name__ == '__main__':
    print(json.dumps(Plan().summary(), indent=2))
