"""A86 -> A94 sparse transition and one-byte re-arm/un-arm tests. No hardware."""
import struct
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_rearm_trial as m
import radio_c6_trial as c6
from test_radio_frow_trial import ChunkedDevice
from test_radio_installer import MemoryJournal, selected


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = m.Plan()

    def make(self, plan=None, eeprom=None):
        plan = plan or self.plan
        dev = ChunkedDevice(plan)
        if eeprom is not None:
            dev.eeprom = bytearray(eeprom)
        dev.ram[0x8f02:0x8f10] = bytes.fromhex('b125860ac0023230323631303238')
        dev.ram[0x9014:0x9014 + 440] = (r.ROOT / 'private/candidates/radio-battery-phase1/extension.bin').read_bytes()
        dev.ram[0x6aa8:0x6aac] = bytes.fromhex('02f0d3fa')
        dev.ram[0x8ea8:0x8eac] = struct.pack('<I', 0x20c9d4)
        dev.ram[0xc9d4:0xc9d8] = struct.pack('<I', 0x20d800)
        methods = (0x28a9, 0x28dd, 0x209141, 0x209119, 0x209145, 0x2949,
                   0x296d, 0x298b, 0x298f, 0x2993, 0x29cd, 0x2a11, 0x2a2f, 0x2aaf, 0x2ac1)
        dev.ram[0xd800:0xd83c] = struct.pack('<15I', *methods)
        dev.ram[0x5e1c:0x5e20] = struct.pack('<I', 0x8000)
        journal = MemoryJournal()
        return dev, journal, m.Runner(dev, plan, journal)

    def test_baseline_is_A93_bank_with_invalidated_header(self):
        a92 = c6.Plan().candidate
        self.assertEqual(self.plan.baseline[0x4000:0x4000 + len(a92)], a92)
        self.assertEqual(self.plan.baseline[0], 0)
        self.assertEqual(selected(self.plan.baseline), 0x8000)

    def test_frames_are_bounded_and_verifiable(self):
        for lo, hi in self.plan.patches:
            self.assertLessEqual(hi - lo, 14)
            self.assertEqual(lo // 16, (hi - 1) // 16)
            self.assertNotEqual(self.plan.candidate[lo - 0x4000:hi - 0x4000], b'\xaa' * (hi - lo))

    def test_complete_image_and_one_commit(self):
        dev, journal, runner = self.make()
        runner.run()
        writes = [frame for frame in dev.calls if frame[0] == 0x74]
        self.assertEqual(len(writes), len(self.plan.patches) + 1)
        self.assertEqual(dev.eeprom[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)
        self.assertEqual(selected(dev.eeprom), 0x4000)
        self.assertIn({'action': 'committed-and-verified',
                       'activation': 'watchdog-reset-then-A94-rearm-trial'}, journal.events)
        for address, (old, new) in enumerate(zip(self.plan.baseline, dev.eeprom)):
            if not any(lo <= address < hi for lo, hi in self.plan.ranges):
                self.assertEqual(old, new)

    def test_every_completed_byte_cut_keeps_fallback_until_activation(self):
        dev, _, runner = self.make()
        runner.run()
        state = bytearray(self.plan.baseline)
        total = sum(hi - lo for lo, hi in self.plan.patches) + 1
        count = 0
        for frame in dev.calls:
            if frame[0] != 0x74:
                continue
            start, _ = struct.unpack_from('<IH', frame, 1)
            start -= 0xff000000
            for i, value in enumerate(frame[7:-1]):
                state[start + i] = value
                count += 1
                self.assertEqual(selected(state), 0x8000 if count < total else 0x4000)
        self.assertEqual(count, total)

    def test_resume_after_partial_write(self):
        state = bytearray(self.plan.baseline)
        for lo, hi in self.plan.patches[:10]:
            state[lo:hi] = self.plan.candidate[lo - 0x4000:hi - 0x4000]
        plan = m.Plan()
        dev, _, runner = self.make(plan, state)
        runner.run()
        self.assertEqual(dev.eeprom[0x4000:0x4000 + len(plan.candidate)], plan.candidate)
        self.assertEqual(selected(dev.eeprom), 0x4000)

    def test_unexpected_storage_rejects_before_enable(self):
        for address in [0, 0x100, 0x4000, 0x7666, 0x8000, 0xf030]:
            dev, _, runner = self.make(m.Plan())
            dev.eeprom[address] ^= 0x40
            with self.assertRaises(ValueError):
                runner.run()
            self.assertEqual(dev.calls, [])

    def test_trial_runtime_rejects_before_enable(self):
        for address, data in [(0x208f04, b'\x91'), (0x205e1c, struct.pack('<I', 0x4000))]:
            dev, _, runner = self.make()
            dev.ram[address - 0x200000:address - 0x200000 + len(data)] = data
            with self.assertRaises(ValueError):
                runner.run()
            self.assertEqual(dev.calls, [])

    def test_loss_before_or_after_every_write_never_retries(self):
        complete, _, runner = self.make()
        runner.run()
        for number in range(1, len(complete.calls) + 1):
            for after in (False, True):
                dev, _, runner = self.make()
                dev.after_write = after
                dev.fail = lambda frame, device: len(device.calls) == number
                with self.assertRaises(OSError):
                    runner.run()
                self.assertEqual(len(dev.calls), number)
                self.assertEqual(dev.eeprom[0x100:0x128], self.plan.backup_ss)
                if selected(dev.eeprom) == 0x4000:
                    self.assertEqual(dev.eeprom[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)

    def test_full_readback_failure_never_commits(self):
        dev, _, runner = self.make()
        dev.read_fault = lambda address, length: address == 0xff004000 and length == 16
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(selected(dev.eeprom), 0x8000)
        self.assertFalse(runner.committed)

    def test_A93_install_proof_is_required(self):
        dev, _, runner = self.make()
        with patch.object(m, 'a93_install_proof', side_effect=ValueError('missing proof')):
            with self.assertRaises(ValueError):
                runner.run()
        self.assertEqual(dev.calls, [])


class BootByteTests(unittest.TestCase):
    def make(self, mode, *, version=None, armed=None, eeprom=None, ds=0x4000):
        view = m.runtime_view(mode)
        plan = view.load_plan()
        dev = ChunkedDevice(plan)
        state = bytearray(plan.baseline)
        state[0x4000:0x4000 + len(plan.candidate)] = plan.candidate
        state[0] = 1 if (armed if armed is not None else plan.value == 0) else 0
        dev.eeprom = bytearray(eeprom if eeprom is not None else state)
        dev.ram[0x8f02:0x8f10] = m.IDENTITY[version or plan.version]
        dev.ram[0x5e1c:0x5e20] = struct.pack('<I', ds)
        journal = MemoryJournal()
        return dev, journal, view.Runner(dev, plan, journal), plan

    def check_one_byte(self, mode, before, after, label):
        dev, journal, runner, plan = self.make(mode)
        original = bytes(dev.eeprom)
        self.assertEqual(original[0], before)
        runner.run()
        writes = [frame for frame in dev.calls if frame[0] == 0x74]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][1:7], struct.pack('<IH', 0xff000000, 1))
        self.assertEqual(writes[0][7:-1], bytes([after]))
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, dev.eeprom)) if a != b], [0])
        self.assertEqual(selected(dev.eeprom), 0x4000 if after else 0x8000)
        self.assertIn({'action': 'committed-and-verified', 'activation': label}, journal.events)

    def test_rearm_running_A93(self):
        self.check_one_byte('rearm-a93', 0, 1, 'watchdog-reset-then-A93-rearmed')

    def test_rearm_running_A94(self):
        self.check_one_byte('rearm', 0, 1, 'watchdog-reset-then-A94-rearmed')

    def test_unarm_running_A94(self):
        self.check_one_byte('unarm', 1, 0, 'watchdog-reset-then-A86-unarmed-from-A94')

    def test_wrong_runtime_or_storage_rejects_before_enable(self):
        for mode in ['rearm-a93', 'rearm', 'unarm']:
            other = 0x94 if mode == 'rearm-a93' else 0x93
            cases = [dict(version=other), dict(ds=0x8000),
                     dict(armed=mode != 'unarm')]
            for case in cases:
                with self.subTest(mode=mode, case=case):
                    dev, _, runner, _ = self.make(mode, **case)
                    with self.assertRaises(ValueError):
                        runner.run()
                    self.assertEqual(dev.calls, [])
            for address in [0x100, 0x4000, 0x4000 + 0x3f00, 0x8000, 0xf030]:
                with self.subTest(mode=mode, address=address):
                    dev, _, runner, _ = self.make(mode)
                    dev.eeprom[address] ^= 0x40
                    with self.assertRaises(ValueError):
                        runner.run()
                    self.assertEqual(dev.calls, [])

    def test_only_the_boot_byte_can_be_framed(self):
        _, _, _, plan = self.make('rearm')
        for offset, data in [(0, b'\0'), (1, b'\1'), (0x4000, b'\1'), (0, b'\1\1')]:
            with self.assertRaises(ValueError):
                plan.write_frame(offset, data)

    def test_loss_never_retries(self):
        for number in (1, 2):
            for after in (False, True):
                dev, _, runner, plan = self.make('unarm')
                dev.after_write = after
                dev.fail = lambda frame, device: len(device.calls) == number
                with self.assertRaises(OSError):
                    runner.run()
                self.assertEqual(len(dev.calls), number)
                self.assertEqual(dev.eeprom[0x100:0x128], plan.backup_ss)


if __name__ == '__main__':
    unittest.main()
