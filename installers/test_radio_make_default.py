"""SS100 -> A94 (make-default) and back (undo-default). No hardware."""
import struct
import unittest
import radio_make_default as m
import radio_rearm_trial as rearm
from test_radio_frow_trial import ChunkedDevice
from test_radio_installer import MemoryJournal, selected


class Tests(unittest.TestCase):
    def make(self, mode, *, ss0_byte=1, identity=0x94, ds=0x4000, eeprom=None):
        view = m.runtime_view(mode)
        plan = view.load_plan()
        dev = ChunkedDevice(plan)
        state = bytearray(plan.baseline)
        state[0x4000:0x4000 + len(plan.candidate)] = plan.candidate
        state[0] = ss0_byte
        state[0x100:0x128] = plan.ss100(0x13 if plan.before is None else plan.before)
        dev.eeprom = bytearray(eeprom if eeprom is not None else state)
        dev.ram[0x8f02:0x8f10] = rearm.IDENTITY[identity]
        dev.ram[0x5e1c:0x5e20] = struct.pack('<I', ds)
        journal = MemoryJournal()
        return dev, journal, view.Runner(dev, plan, journal), plan

    def test_make_default_writes_one_byte_and_every_boot_selects_A94(self):
        dev, journal, runner, plan = self.make('make-default')
        original = bytes(dev.eeprom)
        runner.run()
        writes = [frame for frame in dev.calls if frame[0] == 0x74]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][1:7], struct.pack('<IH', 0xff00011f, 1))
        self.assertEqual(writes[0][7:-1], b'\x40')
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, dev.eeprom)) if a != b], [0x11f])
        self.assertEqual(bytes(dev.eeprom[0x100:0x128]), plan.new_ss)
        self.assertEqual(bytes(dev.eeprom[0x8000:0x8000 + len(plan.active)]), plan.active)
        # Armed, and after the guard clears SS0 (flat battery, no host): both boot A94.
        self.assertEqual(selected(dev.eeprom), 0x4000)
        dev.eeprom[0] = 0
        self.assertEqual(selected(dev.eeprom), 0x4000)
        self.assertIn({'action': 'committed-and-verified',
                       'activation': 'watchdog-reset-then-A94-with-SS100-to-A94'}, journal.events)

    def test_undo_restores_the_A86_fallback(self):
        dev, _, runner, plan = self.make('undo-default', ss0_byte=0)
        runner.run()
        self.assertEqual(bytes(dev.eeprom[0x100:0x128]), plan.backup_ss)
        self.assertEqual(selected(dev.eeprom), 0x8000)

    def test_repair_sets_A94_from_any_byte_31(self):
        for value in (0x00, 0x13, 0x80, 0xff):
            with self.subTest(value=value):
                dev, _, runner, plan = self.make('repair-default')
                dev.eeprom[0x11f] = value
                original = bytes(dev.eeprom)
                runner.run()
                self.assertEqual([i for i, (a, b) in enumerate(zip(original, dev.eeprom)) if a != b],
                                 [] if value == 0x40 else [0x11f])
                self.assertEqual(bytes(dev.eeprom[0x100:0x128]), plan.new_ss)
                dev.eeprom[0] = 0
                self.assertEqual(selected(dev.eeprom), 0x4000)

    def test_wrong_runtime_or_storage_rejects_before_enable(self):
        for mode in ['make-default', 'undo-default', 'repair-default']:
            cases = [dict(identity=0x93), dict(ds=0x8000)]
            if mode == 'make-default':
                cases.append(dict(ss0_byte=0))
            for case in cases:
                with self.subTest(mode=mode, case=case):
                    dev, _, runner, _ = self.make(mode, **case)
                    with self.assertRaises(ValueError):
                        runner.run()
                    self.assertEqual(dev.calls, [])
            addresses = [1, 0x100, 0x4000, 0x4000 + 0x3f00, 0x8000, 0xf030]
            if mode != 'repair-default':
                addresses.append(0x11f)
            for address in addresses:
                with self.subTest(mode=mode, address=address):
                    dev, _, runner, _ = self.make(mode)
                    dev.eeprom[address] ^= 0x40 if address != 0x11f else 0xc0
                    with self.assertRaises(ValueError):
                        runner.run()
                    self.assertEqual(dev.calls, [])

    def test_already_default_is_rejected(self):
        dev, _, runner, _ = self.make('make-default')
        dev.eeprom[0x11f] = 0x40
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(dev.calls, [])

    def test_only_the_SS100_byte_can_be_framed(self):
        _, _, _, plan = self.make('make-default')
        for offset, data in [(0x11f, b'\x80'), (0, b'\1'), (0x11e, b'\x40'), (0x11f, b'\x40\x00')]:
            with self.assertRaises(ValueError):
                plan.write_frame(offset, data)

    def test_loss_never_retries_and_SS0_still_boots_A94(self):
        for number in (1, 2):
            for after in (False, True):
                dev, _, runner, _ = self.make('make-default')
                dev.after_write = after
                dev.fail = lambda frame, device: len(device.calls) == number
                with self.assertRaises(OSError):
                    runner.run()
                self.assertEqual(len(dev.calls), number)
                self.assertEqual(dev.eeprom[0], 1)
                self.assertEqual(selected(dev.eeprom), 0x4000)


if __name__ == '__main__':
    unittest.main()
