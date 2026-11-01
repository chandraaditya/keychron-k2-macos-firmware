"""Explicit A86 -> A91 full F-row trial; strict baseline, sparse writes, no retries.

Precondition: the keyboard was power-cycled after the A90 one-boot trial, so A86
runs from fallback 0x8000, SS0 is the invalidated A90 header and bank 0x4000
still holds the exact A90 image committed by journal radio-1793178020153517000.
Only bytes that differ between A90 and A91 are written, then one activation byte.
Reuses the A90 recovery runner, request journaling and guard checks.
"""
import json
import types
import radio_installer as r
import radio_rollback_preflight as a86
import radio_mtu_recovery as previous

EXPECTED_CANDIDATE_SHA = 'eba838d55855babb02209cacd1a412cdceffbc7142351d74ced0fd2bd6f7e3e6'
A90_JOURNAL = r.ROOT / 'private/update-sessions/radio-1793178020153517000.jsonl'
A90_BACKUP_SHA = 'b0824a4b3c6195c9e510bcf8fa9fb3bfa057d6171c5977cfcb112058549574e5'
# Re-pairing may rewrite this reviewed slot outside VS (see A89 post-pairing review).
PAIRING_SLOT = range(0xf001, 0xf027)


def a90_install_proof():
    events = [json.loads(line) for line in A90_JOURNAL.read_text().splitlines()]
    backup = A90_JOURNAL.with_suffix('.eeprom.bin').read_bytes()
    record = next(event for event in events if event['action'] == 'fresh-backup-saved')
    if len(backup) != 65536 or r.digest(backup) != record['sha256'] or record['sha256'] != A90_BACKUP_SHA:
        raise ValueError('A90 pre-install backup differs')
    if [event for event in events if event['action'] == 'committed-and-verified'] != \
            [{'action': 'committed-and-verified', 'activation': 'watchdog-reset-then-A90-control-MTU-trial'}]:
        raise ValueError('Expected exactly one committed A90 install')
    return backup


def frames(start, end):
    """Split a span at the 16-byte software boundary and the 14-byte frame limit."""
    while start < end:
        stop = min(end, (start // 16 + 1) * 16, start + 14)
        yield start, stop
        start = stop


class Plan(previous.Plan):
    def __init__(self):
        a90 = previous.Plan()
        self.active = a90.active
        self.backup_ss = a90.backup_ss
        self.new_ss = a90.new_ss
        self.current_ss = a90.current_ss
        baseline = bytearray(a90_install_proof())
        baseline[0x4000:0x4000 + len(a90.candidate)] = a90.candidate
        baseline[0] = 0  # A90's guard invalidated SS0 on its startup.
        if bytes(baseline[:40]) != b'\0' + self.new_ss[1:]:
            raise ValueError('Expected invalidated A90 header')
        self.baseline = bytes(baseline)
        self.candidate = (r.ROOT / 'private/candidates/radio-frow-one-boot/dynamic-section.bin').read_bytes()
        if len(self.candidate) != 16128 or r.digest(self.candidate) != EXPECTED_CANDIDATE_SHA:
            raise ValueError('Reviewed A91 candidate differs')
        r.records(self.candidate)
        if 0x4000 + len(self.candidate) > 0x8000:
            raise ValueError('A91 exceeds inactive bank')
        # parse_read refuses an all-AA EEPROM read (indistinguishable from a
        # failed I2C transfer); full-image verification reads 16-byte chunks.
        for i in range(0, len(self.candidate), 16):
            if self.candidate[i:i + 16] == b'\xaa' * len(self.candidate[i:i + 16]):
                raise ValueError('A91 contains an unverifiable all-AA chunk')
        self._plan_from(self.baseline)

    def _plan_from(self, state):
        changes = [0x4000 + i for i, value in enumerate(self.candidate)
                   if state[0x4000 + i] != value]
        spans = []
        for address in changes:
            if spans and address == spans[-1][1]:
                spans[-1][1] += 1
            else:
                spans.append([address, address + 1])
        self.patches = tuple(self._verifiable(lo, hi)
                             for lo0, hi0 in spans for lo, hi in frames(lo0, hi0))
        self.changed_bytes = len(changes)
        self.ranges = ((0, 1),) + self.patches

    def _verifiable(self, lo, hi):
        """Widen an all-AA frame with neighbouring candidate bytes in its 16-byte block.

        Neighbours already hold their candidate value, so rewriting them is a no-op.
        """
        block = lo // 16 * 16
        end = 0x4000 + len(self.candidate)
        while self.candidate[lo - 0x4000:hi - 0x4000] == b'\xaa' * (hi - lo):
            if hi - lo >= 14:
                raise ValueError('Cannot make A91 frame verifiable')
            if hi < min(block + 16, end):
                hi += 1
            elif lo > max(block, 0x4000):
                lo -= 1
            else:
                raise ValueError('Cannot make A91 frame verifiable')
        return lo, hi

    def write_frame(self, offset, data):
        expected = (b'\1' if offset == 0 else
                    self.candidate[offset - 0x4000:offset - 0x4000 + len(data)])
        if data != expected:
            raise ValueError('Write data differs from exact reviewed transition')
        return r.Plan.write_frame(self, offset, data)

    def fresh_matches(self, fresh):
        if len(fresh) != 65536:
            raise ValueError('Unexpected EEPROM capture size')
        bank = range(0x4000, 0x4000 + len(self.candidate))
        for i, (x, y) in enumerate(zip(fresh, self.baseline)):
            if x == y or r.VS.start <= i < r.VS.stop or i in PAIRING_SLOT:
                continue
            # A stopped earlier A91 run may have left any bank byte already at A91.
            if i in bank and x == self.candidate[i - 0x4000]:
                continue
            raise ValueError(f'EEPROM differs from reviewed post-A90 state at {i:#06x}')
        self._plan_from(fresh)

    def summary(self):
        return {'candidate_sha256': EXPECTED_CANDIDATE_SHA,
                'candidate_bytes': len(self.candidate), 'required_current_build': 'A86',
                'changed_application_bytes': self.changed_bytes,
                'application_write_frames': len(self.patches), 'activation_bytes': 1,
                'activation_label': self.activation_label,
                'same_verified_recovery_guard': True,
                'whole_image_and_protected_storage_verified_before_activation': True,
                'automatic_retry': False, 'request_alarm_seconds': 3,
                'watchdog_margin_seconds': 6}

    activation_label = 'watchdog-reset-then-A91-full-frow-trial'


def guard_context(io):
    a90_install_proof()
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
        a90_install_proof()
        return Plan()
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_SHA,
                                 load_plan=checked_plan, NativeHID=previous.RecoveryHID,
                                 guard_context=guard_context, Journal=r.Journal,
                                 Runner=Runner, RESULT_NAME='radio-frow-trial-flash-result.json')


if __name__ == '__main__':
    print(json.dumps(Plan().summary(), indent=2))
