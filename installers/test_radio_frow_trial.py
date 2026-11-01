"""A86 -> A91 sparse transition tests. No hardware."""
import struct
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_frow_trial as m
import radio_mtu_recovery as previous
from test_radio_installer import MemoryDevice, MemoryJournal, selected


STOPPED = r.ROOT / 'private/update-sessions/radio-1793181640523702000.jsonl'


class ChunkedDevice(MemoryDevice):
    """Real EEPROM reads: 16-byte requests, each refused when wholly AA."""
    def read(self, address, length):
        out = bytearray()
        while len(out) < length:
            a = address + len(out)
            n = min(16 if 0xff000000 <= a < 0xff010000 else 32, length - len(out))
            chunk = MemoryDevice.read(self, a, n)
            if 0xff000000 <= a < 0xff010000 and chunk == b'\xaa' * n:
                raise ValueError('All-AA read cannot establish underlying I2C success; refusing')
            out += chunk
        return bytes(out)


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

    def test_no_frame_is_all_AA(self):
        for lo, hi in self.plan.patches:
            self.assertNotEqual(self.plan.candidate[lo - 0x4000:hi - 0x4000], b'\xaa' * (hi - lo))
        self.assertIn(0x7c21, [a for lo, hi in self.plan.patches for a in range(lo, hi)])

    def test_resume_from_real_stopped_session(self):
        import json
        events = [json.loads(line) for line in STOPPED.read_text().splitlines()]
        fresh = bytearray(STOPPED.with_suffix('.eeprom.bin').read_bytes())
        for event in events:
            if event['action'] == 'write-readback-verified':
                o, n = event['offset'], event['bytes']
                fresh[o:o + n] = self.plan.candidate[o - 0x4000:o - 0x4000 + n]
        for stalled in (0xa6, 0xaa):  # The unverified 0x7c21 write may or may not have landed.
            state = bytearray(fresh)
            state[0x7c21] = stalled
            plan = m.Plan()
            dev, _, runner = self.make(plan, state)
            runner.run()
            self.assertTrue(runner.committed)
            self.assertEqual(dev.eeprom[0x4000:0x4000 + len(plan.candidate)], plan.candidate)
            self.assertEqual(selected(dev.eeprom), 0x4000)
            self.assertLess(plan.changed_bytes, 103)

    def test_bank_byte_with_neither_A90_nor_A91_value_rejects(self):
        state = bytearray(self.plan.baseline)
        state[0x7c21] = 0x55
        dev, _, runner = self.make(m.Plan(), state)
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(dev.calls, [])

    def test_baseline_is_A90_bank_with_invalidated_header(self):
        a90 = previous.Plan()
        self.assertEqual(self.plan.baseline[0x4000:0x4000 + len(a90.candidate)], a90.candidate)
        self.assertEqual(self.plan.baseline[0], 0)
        self.assertEqual(selected(self.plan.baseline), 0x8000)

    def test_frames_respect_boundary_and_size(self):
        for lo, hi in self.plan.patches:
            self.assertLessEqual(hi - lo, 14)
            self.assertEqual(lo // 16, (hi - 1) // 16)
            self.assertTrue(0x4000 <= lo < hi <= 0x4000 + len(self.plan.candidate))

    def test_complete_image_with_only_changed_bytes_and_one_commit(self):
        dev, journal, runner = self.make()
        runner.run()
        writes = [frame for frame in dev.calls if frame[0] == 0x74]
        self.assertEqual(len(writes), len(self.plan.patches) + 1)
        self.assertEqual(sum(len(frame) - 8 for frame in writes),
                         sum(hi - lo for lo, hi in self.plan.patches) + 1)
        self.assertEqual(journal.saved, self.plan.baseline)
        self.assertEqual(dev.eeprom[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)
        self.assertEqual(selected(dev.eeprom), 0x4000)
        self.assertTrue(runner.committed)
        self.assertIn({'action': 'committed-and-verified',
                       'activation': 'watchdog-reset-then-A91-full-frow-trial'}, journal.events)
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
                if count < total:
                    self.assertEqual(selected(state), 0x8000)
                else:
                    self.assertEqual(selected(state), 0x4000)
                    self.assertEqual(state[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)
        self.assertEqual(count, total)

    def test_unexpected_storage_saves_and_rejects_before_enable(self):
        for address in [0, 0x100, 0x4000, 0x7666, 0x7e93, 0x8000, 0xf030]:
            dev, journal, runner = self.make()
            dev.eeprom[address] ^= 0x40
            with self.assertRaises(ValueError):
                runner.run()
            self.assertEqual(dev.calls, [])
        for address in [0x250, 0xf002]:  # VS and reviewed pairing slot may change on re-pair.
            dev, _, runner = self.make()
            dev.eeprom[address] ^= 1
            before = bytes(dev.eeprom)
            runner.run()
            self.assertEqual(dev.eeprom[address], before[address])

    def test_A90_or_A89_runtime_rejects_before_enable(self):
        for address, data in [(0x208f04, b'\x90'), (0x205e1c, struct.pack('<I', 0x4000)),
                              (0x209014, b'\0'), (0x20d80c, b'\0' * 4)]:
            dev, journal, runner = self.make()
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

    def test_only_exact_patch_bytes_are_allowed(self):
        lo, hi = self.plan.patches[0]
        for address, data in [(0, b'\0'), (0x4000, b'x'), (0x8000, b'x'),
                              (lo, bytes(b ^ 1 for b in self.plan.candidate[lo - 0x4000:hi - 0x4000])),
                              (0x100, b'\1')]:
            with self.assertRaises(ValueError):
                self.plan.write_frame(address, data)
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)

    def test_A90_install_proof_is_required(self):
        m.a90_install_proof()
        dev, _, runner = self.make()
        with patch.object(m, 'a90_install_proof', side_effect=ValueError('missing proof')):
            with self.assertRaises(ValueError):
                runner.run()
        self.assertEqual(dev.calls, [])


if __name__ == '__main__':
    unittest.main()
