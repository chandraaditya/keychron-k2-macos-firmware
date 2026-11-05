"""Make A94 the only boot target by pointing the backup section SS100 at bank 0x4000.

The ROM boots the first valid static section. A94's guard clears SS0 byte 0 on
every boot and re-arms it only after the host reads F1, so a boot that dies early
(a flat battery) falls back to SS100. Today SS100 selects A86 at 0x8000.

make-default: A94 runs from 0x4000 with SS0 armed. Write only SS100's DS-address
byte (0x11F) from 0x80 to 0x40; SS100 then equals the SS0 header A94 already
boots from. A86 stays at 0x8000, but nothing selects it, so there is no
automatic fallback any more. A94's re-arm then declines (flag 1), as designed for
a layout it did not install; SS100 boots it.

undo-default: with A94 running, write 0x11F back to 0x80. SS0 byte 0 is
already 0 by then (re-arm declined on every boot), so the next power-on boots
A86; run --reactivate from there to get A94 back as a one-boot trial.

repair-default: with A94 running, write 0x11F = 0x40 whatever it holds now. For
a make-default write that was cut off and left another value; SS0 stays armed
until the next reset, so this has to run before powering off.

After make-default the probe should show A94, DS 0x4000, SS0 byte 0 = 0 (after
the first reboot), SS100 = the A94 header and re-arm flag 1. Flag 1 is expected:
A94 declines to re-arm a layout it did not install.
"""
import types
import radio_installer as r
import radio_mtu_recovery as previous
import radio_rearm_trial as rearm

OFFSET = 0x11f
VALUES = {'make-default': (0x80, 0x40), 'undo-default': (0x40, 0x80), 'repair-default': (None, 0x40)}


class SectionBytePlan:
    """Only SS100 byte 31 changes; everything else must be the installed A94 layout."""
    patches = ()

    def __init__(self, mode):
        self.image = rearm.Plan()
        self.mode = mode
        self.before, self.value = VALUES[mode]
        self.baseline = self.image.baseline
        self.candidate = self.image.candidate
        self.active = self.image.active
        self.new_ss = self.image.new_ss
        self.backup_ss = self.image.backup_ss
        self.ranges = ((OFFSET, OFFSET + 1),)
        self.activation_label = ('watchdog-reset-then-A94-with-SS100-to-A94' if self.value == 0x40
                                 else 'watchdog-reset-then-A94-with-SS100-to-A86')

    def ss100(self, value):
        ss = bytearray(self.backup_ss)
        ss[OFFSET - 0x100] = value
        return bytes(ss)

    def ss100_ok(self, data, value):
        """SS100 as expected; value None accepts any byte 31."""
        if value is None:
            return data[:31] == self.backup_ss[:31] and data[32:] == self.backup_ss[32:]
        return data == self.ss100(value)

    def fresh_matches(self, fresh):
        if len(fresh) != 65536:
            raise ValueError('Unexpected EEPROM capture size')
        if fresh[0x4000:0x4000 + len(self.candidate)] != self.candidate:
            raise ValueError('Bank 4000 does not hold the exact A94 image')
        if not self.ss100_ok(fresh[0x100:0x128], self.before):
            raise ValueError('SS100 is not in the expected starting state')
        state = bytearray(fresh)
        state[0] = 0
        state[0x100:0x128] = self.backup_ss
        self.image.fresh_matches(bytes(state))
        if self.image.patches:
            raise ValueError('EEPROM differs from the installed A94 layout')

    def write_frame(self, offset, data):
        if offset != OFFSET or data != bytes([self.value]):
            raise ValueError('Only the reviewed SS100 byte may be written')
        return r.Plan.write_frame(self, offset, data)

    def summary(self):
        return {'candidate_sha256': rearm.EXPECTED_CANDIDATE_SHA, 'running_build': 'A94',
                'application_write_frames': 0, 'offset': OFFSET, 'value': self.value,
                'fallback_after': 'A94 (no automatic A86 fallback)' if self.value == 0x40 else 'A86',
                'activation_label': self.activation_label, 'automatic_retry': False}


def running_guard(mode):
    before = VALUES[mode][0]

    def guard(io):
        r.guard_context(io, expected_identity=rearm.IDENTITY[0x94])
        plan = io.plan
        if io.read(0x205e1c, 4) != (0x4000).to_bytes(4, 'little'):
            raise ValueError('Expected A94 running from bank 4000')
        ss0 = io.read(0xff000000, 40)
        if ss0[1:] != plan.new_ss[1:] or (mode == 'make-default' and ss0[0] != 1):
            raise ValueError('Expected the A94 SS0 header (armed for make-default)')
        if not plan.ss100_ok(io.read(0xff000100, 40), before):
            raise ValueError('Expected SS100 starting state')
    return guard


class Runner(previous.Runner):
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
        ss0 = fresh[:40]
        try:
            self.journal.event(action='before-enable', outcome_if_no_completion='unknown')
            self.io.set(b'\x70')
            self.enabled = True
            self.io.trace_context = None
            self.journal.event(action='enabled', expected_inactivity_reset_seconds=10)
            self.verify(0, ss0)
            self.verify(0x100, fresh[0x100:0x128])
            self.verify(0x4000, self.plan.candidate)
            self.verify(0x8000, self.plan.active)
            self.journal.event(action='ready-to-commit')
            self.write(OFFSET, bytes([self.plan.value]))
            self.committed = True
            self.verify(0, ss0)
            self.verify(0x100, self.plan.ss100(self.plan.value))
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


def runtime_view(mode):
    guard = running_guard(mode)

    class ModeRunner(Runner):
        pass
    ModeRunner.guard = staticmethod(guard)
    return types.SimpleNamespace(ALLOW_HARDWARE_UPDATES=False,
                                 EXPECTED_CANDIDATE_SHA=rearm.EXPECTED_CANDIDATE_SHA,
                                 load_plan=lambda: SectionBytePlan(mode),
                                 NativeHID=previous.RecoveryHID, guard_context=guard,
                                 Journal=r.Journal, Runner=ModeRunner,
                                 RESULT_NAME=f'radio-{mode}-flash-result.json')
