"""A92 Fn translation through the original scanner-frame handler. No hardware.

Boots the actual A92 dynamic section in the WP-guard harness, then runs the
original handler at 0x206c2c on an A1 key frame. Only the frame-ready check,
the frame read, the follow-up timer and the final tail call are modeled.
"""
import json
import os
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research import test_radio_wp_guard as wp

ROOT = Path(__file__).resolve().parents[1]
OBJ = 0x20c000


class Tests(unittest.TestCase):
    def boot(self, profile):
        self.m = json.loads((ROOT / profile / 'manifest.json').read_text())
        ds = (ROOT / profile / 'dynamic-section.bin').read_bytes()
        return wp.WPGuardTests().run_case('ok', dynamic=ds)[0]

    def frame(self, cpu, frame):
        cpu.mem_write(OBJ, bytes(0x200))
        def hook(u, address, size, data):
            if address == 0x17f16:      # frame ready
                u.reg_write(r.UC_ARM_REG_R0, 1)
            elif address == 0x208426:   # read 16-byte frame into caller buffer
                u.mem_write(u.reg_read(r.UC_ARM_REG_R1), frame.ljust(16, b'\0'))
                u.reg_write(r.UC_ARM_REG_R0, 0)
            elif address in (0x168a8, 0x174fa):
                u.reg_write(r.UC_ARM_REG_R0, 0)
            elif address == 0x17e2c:    # handler's final tail call
                u.emu_stop()
                return
            else:
                return
            u.reg_write(r.UC_ARM_REG_PC, u.reg_read(r.UC_ARM_REG_LR))
        handle = cpu.hook_add(UC_HOOK_CODE, hook)
        cpu.reg_write(r.UC_ARM_REG_R0, OBJ)
        cpu.reg_write(r.UC_ARM_REG_SP, 0x2003f0)
        cpu.reg_write(r.UC_ARM_REG_LR, 0x70001)
        try:
            cpu.emu_start(0x206c2d, 0x70000, count=5000)
        finally:
            cpu.hook_del(handle)
        self.assertEqual(cpu.reg_read(r.UC_ARM_REG_SP), 0x2003f0)  # all pushed state popped
        return bytes(cpu.mem_read(OBJ + 0x13d, 9)), cpu.mem_read(OBJ + 0xc4, 1)[0]

    def test_A92_shifts_fn_into_apple_field(self):
        cpu = self.boot(os.environ.get('K2_FN_PROFILE', 'private/candidates/radio-fn-profile'))
        base = self.m['component_base'] + self.m['component_symbols']['fn_shift']
        self.assertEqual(bytes(cpu.mem_read(0x206c9a, 8)),
                         bytes.fromhex(self.m['fn_patch']['bytes']) + bytes.fromhex('84f84501'))
        self.assertEqual(int(self.m['fn_patch']['target'], 16), base)
        # A1, modifier, -, keys1..4, key5, Fn
        f12 = bytes([0xa1, 0x00, 0, 0x45, 0, 0, 0, 0])
        self.assertEqual(self.frame(cpu, f12 + b'\x00'), (bytes([0, 0, 0x45, 0, 0, 0, 0, 0, 0]), 1))
        self.assertEqual(self.frame(cpu, f12 + b'\x01'), (bytes([0, 0, 0x45, 0, 0, 0, 0, 0, 2]), 1))
        mods = bytes([0xa1, 0x0a, 0, 0x04, 0x05, 0x06, 0x07, 0x08, 0x01])
        self.assertEqual(self.frame(cpu, mods), (bytes([0x0a, 0, 4, 5, 6, 7, 8, 0, 2]), 1))

    def test_A91_keeps_original_fn_byte(self):
        cpu = self.boot('private/candidates/radio-frow-profile')
        self.assertEqual(bytes(cpu.mem_read(0x206c9a, 8)), bytes.fromhex('9df8080084f84501'))
        f12 = bytes([0xa1, 0x00, 0, 0x45, 0, 0, 0, 0, 0x01])
        self.assertEqual(self.frame(cpu, f12)[0][-1], 1)


if __name__ == '__main__':
    unittest.main()
