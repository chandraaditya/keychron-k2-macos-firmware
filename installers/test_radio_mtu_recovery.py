"""Recovery/sparse transition and native request boundary tests. No hardware."""
import struct
import ctypes as C
import unittest
from unittest.mock import patch
import radio_installer as r
import radio_mtu_recovery as m
from apple_raw_hid import AppleRawHID
from test_radio_installer import MemoryDevice, MemoryJournal, selected


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = m.Plan()

    def make(self):
        dev = MemoryDevice(self.plan)
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
        return dev, journal, m.Runner(dev, self.plan, journal)

    def test_complete_image_with_only_twelve_data_bytes_and_one_commit(self):
        dev, journal, runner = self.make()
        runner.run()
        writes = [frame for frame in dev.calls if frame[0] == 0x74]
        self.assertEqual(len(writes), 8)
        self.assertEqual(sum(len(frame) - 8 for frame in writes), 13)
        self.assertEqual(journal.saved, self.plan.baseline)
        self.assertEqual(dev.eeprom[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)
        self.assertEqual(selected(dev.eeprom), 0x4000)
        self.assertTrue(runner.committed)
        for address, (old, new) in enumerate(zip(self.plan.baseline, dev.eeprom)):
            if not any(lo <= address < hi for lo, hi in self.plan.ranges):
                self.assertEqual(old, new)

    def test_every_completed_byte_cut_keeps_fallback_until_complete_activation(self):
        dev, _, runner = self.make()
        runner.run()
        state = bytearray(self.plan.baseline)
        count = 0
        for frame in dev.calls:
            if frame[0] != 0x74:
                continue
            start, _ = struct.unpack_from('<IH', frame, 1)
            start -= 0xff000000
            for i, value in enumerate(frame[7:-1]):
                state[start + i] = value
                count += 1
                if count < 13:
                    self.assertEqual(selected(state), 0x8000)
                else:
                    self.assertEqual(selected(state), 0x4000)
                    self.assertEqual(state[0x4000:0x4000 + len(self.plan.candidate)], self.plan.candidate)
        self.assertEqual(count, 13)

    def test_unexpected_storage_saves_and_rejects_before_enable(self):
        for address in [0, 0x100, 0x4000, 0x5f50, 0x7666, 0x8000, 0xf002]:
            dev, journal, runner = self.make()
            dev.eeprom[address] ^= 1
            with self.assertRaises(ValueError):
                runner.run()
            self.assertEqual(dev.calls, [])
        dev, _, runner = self.make()
        dev.eeprom[0x250] ^= 1
        before = bytes(dev.eeprom)
        runner.run()
        self.assertEqual(dev.eeprom[r.VS], before[r.VS])

    def test_A89_runtime_or_other_headers_reject_before_enable(self):
        for address, data in [(0x208f04, b'\x89'), (0x205e1c, struct.pack('<I', 0x4000)),
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
        dev.read_fault = lambda address, length: address == 0xff004000 and length == len(self.plan.candidate)
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(selected(dev.eeprom), 0x8000)
        self.assertFalse(runner.committed)

    def test_only_exact_patch_bytes_are_allowed(self):
        for address, data in [(0, b'\0'), (0x4000, b'x'), (0x8000, b'x'),
                              (0x7666, b'\x89'), (0x100, b'\1')]:
            with self.assertRaises(ValueError):
                self.plan.write_frame(address, data)
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)

    def test_real_interrupted_session_proof_is_required(self):
        m.recovery_proof()
        dev, _, runner = self.make()
        with patch.object(m, 'recovery_proof', side_effect=ValueError('missing proof')):
            with self.assertRaises(ValueError):
                runner.run()
            with self.assertRaises(ValueError):
                m.runtime_view().load_plan()
        self.assertEqual(dev.calls, [])

    def observer(self, fail=False):
        reader = object.__new__(m.RecoveryHID)
        calls = []
        def native(*args):
            calls.append(args[2])
            if fail:
                raise OSError('native call did not complete')
            return 0
        reader.set_report = native
        reader.get_report = native
        with patch.object(AppleRawHID, '_enter', return_value=reader):
            reader._enter()
        journal = MemoryJournal()
        reader.request_journal = journal
        reader.trace_context = {'phase': 'write-readback', 'target_offset': 0x7666, 'target_bytes': 1}
        return reader, journal, calls

    def test_native_request_log_distinguishes_write_and_verification(self):
        reader, journal, calls = self.observer()
        reader.set_report(None, 2, 0x71, None, 8)
        reader.get_report(None, 2, 0x72, None, None)
        self.assertEqual(calls, [0x71, 0x72])
        self.assertEqual([event['action'] for event in journal.events],
                         ['native-request-start', 'native-request-complete'] * 2)
        self.assertEqual([event['operation'] for event in journal.events], ['SET', 'SET', 'GET', 'GET'])
        reader.trace_context = None
        reader.set_report(None, 2, 0x71, None, 8)
        self.assertEqual(len(journal.events), 4)

    def test_uncompleted_native_call_leaves_exact_unmatched_intent(self):
        reader, journal, calls = self.observer(fail=True)
        with self.assertRaises(OSError):
            reader.set_report(None, 2, 0x74, None, 9)
        self.assertEqual(calls, [0x74])
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.events[0]['action'], 'native-request-start')
        self.assertEqual(journal.events[0]['report_id'], 0x74)

    def test_verification_records_the_actual_read_address(self):
        reader, journal, _ = self.observer()
        packet = r.read_frame(0xff007666, 1)
        buffer = C.create_string_buffer(packet, len(packet))
        reader.set_report(None, 2, 0x71, buffer, len(packet))
        reader.get_report(None, 2, 0x72, None, None)
        for event in journal.events:
            self.assertEqual(event['read_address'], '0xff007666')
            self.assertEqual(event['read_bytes'], 1)

    def test_full_readback_also_has_a_trace_context(self):
        dev, _, runner = self.make()
        original = dev.read
        contexts = []
        def read(address, length):
            if address == 0xff004000 and length == len(self.plan.candidate):
                contexts.append(dict(dev.trace_context))
            return original(address, length)
        dev.read = read
        runner.run()
        self.assertEqual(contexts, [{'phase': 'verification', 'target_offset': 0x4000,
                                     'target_bytes': len(self.plan.candidate)}])


if __name__ == '__main__':
    unittest.main()
