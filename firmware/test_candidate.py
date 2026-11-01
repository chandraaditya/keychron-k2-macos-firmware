"""Execute emitted ARM bytes offline. MMIO and WFI are explicitly modeled.

No claim of silicon timing, power, electrical interrupts, bootloader acceptance,
or compatibility with the owner's uncaptured installed scanner image.
"""
import contextlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import tempfile

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as reg

from build_candidate import build, BASE, BASE_SHA, OUT, HOOK, ORIGINAL, STUB, bl, sha

PMU, CLOCK, TIMER, IRQ = 0x40032040, 0x4005e000, 0x40002000, 0xe000e100
REGS = [reg.UC_ARM_REG_R0, reg.UC_ARM_REG_R1, reg.UC_ARM_REG_R2, reg.UC_ARM_REG_R3,
        reg.UC_ARM_REG_R4, reg.UC_ARM_REG_R5, reg.UC_ARM_REG_R6, reg.UC_ARM_REG_R7,
        reg.UC_ARM_REG_R8, reg.UC_ARM_REG_R9, reg.UC_ARM_REG_R10, reg.UC_ARM_REG_R11]
SENTINEL = 0x10000


def word(cpu, address):
    return struct.unpack('<I', cpu.mem_read(address, 4))[0]


def put(cpu, address, value):
    cpu.mem_write(address, struct.pack('<I', value))


def machine(image):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x11000)
    cpu.mem_write(0, image)
    cpu.mem_map(0x20000000, 0x2000)
    cpu.mem_map(0x40000000, 0x100000)
    cpu.mem_map(0xe000e000, 0x1000)
    cpu.mem_write(0x20000166, b'\x01')
    cpu.mem_write(0x200001b8, b'\x01')
    put(cpu, CLOCK, 0x1080)
    put(cpu, IRQ, 0x10040)
    put(cpu, TIMER, 1)
    put(cpu, TIMER+0x1c, 0x7000)
    return cpu


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.manifest = build()
        cls.image = (OUT / 'candidate.bin').read_bytes()
        cls.base = BASE.read_bytes()
        cls.wfi = cls.manifest['symbols']['idle_wfi']
        cls.disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)

    def execute(self, cpu=None, mock_original=True, at_wfi=None, start=STUB):
        cpu = cpu or machine(self.image)
        original_calls, sleeps, writes = [], [], []
        initial = [0x12340000 + i for i in range(len(REGS))]
        for r, value in zip(REGS, initial):
            cpu.reg_write(r, value)
        cpu.reg_write(reg.UC_ARM_REG_SP, 0x20001710)
        cpu.reg_write(reg.UC_ARM_REG_LR, SENTINEL | 1)
        expected_sp = 0x20001710

        def observe(uc, address, size, data):
            if address == ORIGINAL:
                original_calls.append([uc.reg_read(r) for r in REGS[:4]])
                self.assertEqual(uc.reg_read(reg.UC_ARM_REG_SP) % 8, 0)
                if mock_original:
                    # Model ABI-conforming original handler's caller-saved clobbers.
                    for r in REGS[:3]:
                        uc.reg_write(r, 0xabcd)
                    uc.reg_write(reg.UC_ARM_REG_PC, uc.reg_read(reg.UC_ARM_REG_LR))
            elif address == self.wfi:
                self.assertEqual(word(uc, PMU), 4)
                self.assertEqual(uc.reg_read(reg.UC_ARM_REG_PRIMASK), 0)
                sleeps.append(address)
                if at_wfi:
                    at_wfi(uc)
                # Explicit model of a wake/return, NOT execution of real WFI.
                uc.reg_write(reg.UC_ARM_REG_PC, (address + 2) | 1)
            elif address == SENTINEL or (start == HOOK and address == HOOK+4):
                uc.emu_stop()

        def record_write(uc, access, address, size, value, data):
            if 0x40000000 <= address < 0x40100000 or address >= 0xe000e000:
                writes.append((address, size, value))

        hook1 = cpu.hook_add(UC_HOOK_CODE, observe)
        hook2 = cpu.hook_add(UC_HOOK_MEM_WRITE, record_write)
        cpu.emu_start(start | 1, SENTINEL, count=50000)
        cpu.hook_del(hook1)
        cpu.hook_del(hook2)
        self.assertIn(cpu.reg_read(reg.UC_ARM_REG_PC), (SENTINEL, HOOK+4))
        self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_SP), expected_sp)
        self.assertEqual([cpu.reg_read(r) for r in REGS[3:]], initial[3:])
        self.assertEqual(original_calls, [initial[:4]])
        return cpu, sleeps, writes

    def test_exact_binary_scope_and_inverse(self):
        self.assertEqual(sha(self.base), BASE_SHA)
        self.assertEqual(sha(self.image), self.manifest['image_sha256'])
        n = self.manifest['stub_size']
        differences = {i for i, (a, b) in enumerate(zip(self.base, self.image)) if a != b}
        self.assertLessEqual(differences, set(range(HOOK, HOOK+4)) | set(range(STUB, STUB+n)))
        for start, end in ((0, 0x194), (ORIGINAL, 0x286), (0x7000, 0xa400), (0xfffc, 0x10000)):
            self.assertEqual(self.image[start:end], self.base[start:end])
        restored = bytearray(self.image)
        restored[HOOK:HOOK+4] = self.base[HOOK:HOOK+4]
        restored[STUB:STUB+n] = self.base[STUB:STUB+n]
        self.assertEqual(restored, self.base)

    def test_independent_branch_decode(self):
        for address, target in ((HOOK, STUB), (STUB+2, ORIGINAL)):
            instruction = next(self.disassembler.disasm(self.image[address:address+4], address))
            self.assertEqual(instruction.mnemonic, 'bl')
            self.assertEqual(instruction.op_str, f'#{hex(target)}')
        # The hook's stock continuation consumes neither flags nor R0-R3.
        instruction = next(self.disassembler.disasm(self.image[HOOK+4:HOOK+6], HOOK+4))
        self.assertEqual((instruction.mnemonic, instruction.op_str), ('b', '#0x776'))
        self.assertEqual(self.image[self.wfi-4:self.wfi], bytes.fromhex('bff34f8f'))  # DSB

    def test_reproducible_build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            again = build()
        self.assertEqual(again, self.manifest)
        self.assertEqual((OUT / 'candidate.bin').read_bytes(), self.image)

    def test_reject_wrong_bl_alignment(self):
        with self.assertRaises(ValueError):
            bl(HOOK, STUB+1)

    def test_reject_wrong_reference_without_changing_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / 'wrong.bin'
            wrong.write_bytes(self.base[:-1] + bytes([self.base[-1] ^ 1]))
            with patch('build_candidate.BASE', wrong):
                with self.assertRaisesRegex(ValueError, 'exact approved analysis input'):
                    build()
        self.assertEqual((OUT / 'candidate.bin').read_bytes(), self.image)

    def test_sleep_restores_pmu_and_preserves_peripherals(self):
        cpu, sleeps, writes = self.execute()
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(writes, [(PMU, 4, 4), (PMU, 4, 0)])
        self.assertEqual(word(cpu, PMU), 0)
        self.assertEqual(word(cpu, CLOCK), 0x1080)
        self.assertEqual(word(cpu, IRQ), 0x10040)
        self.assertEqual(word(cpu, TIMER), 1)

    def test_hook_executes_emitted_wrapper_and_returns(self):
        _, sleeps, writes = self.execute(start=HOOK)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(writes, [(PMU, 4, 4), (PMU, 4, 0)])

    def test_actual_stock_handler_runs_before_new_sleep(self):
        # Real stock SPI parser and 0x194 execute; tick flag zero returns normally.
        _, sleeps, writes = self.execute(mock_original=False)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(writes, [(PMU, 4, 4), (PMU, 4, 0)])

    def test_actual_stock_enabled_countdown_preserved(self):
        cpu = machine(self.image)
        cpu.mem_write(0x20000166, b'\x00')
        cpu.mem_write(0x200001ba, b'\x01')
        put(cpu, 0x200001ac, 2)
        cpu, sleeps, _ = self.execute(cpu, mock_original=False)
        self.assertEqual(word(cpu, 0x200001ac), 1)
        self.assertEqual(sleeps, [])

    def test_actual_disabled_countdown_preserved_with_new_yield(self):
        cpu = machine(self.image)
        cpu.mem_write(0x200001ba, b'\x01')
        put(cpu, 0x200001ac, 2)
        cpu, sleeps, writes = self.execute(cpu, mock_original=False)
        self.assertEqual(word(cpu, 0x200001ac), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(writes, [(PMU, 4, 4), (PMU, 4, 0)])

    def test_original_handler_keeps_forced_sleep_policy(self):
        cpu = machine(self.image)
        cpu.mem_write(0x200001ba, b'\x01')
        cpu.mem_write(0x20000193, b'\x01')
        put(cpu, 0x200001ac, 100)
        reached = []

        def observe(uc, address, size, data):
            if address == 0x1de:
                reached.append(address)
                uc.emu_stop()  # Stop before physical deep-sleep/MMIO work.

        cpu.hook_add(UC_HOOK_CODE, observe)
        cpu.reg_write(reg.UC_ARM_REG_SP, 0x20001710)
        cpu.reg_write(reg.UC_ARM_REG_LR, SENTINEL | 1)
        cpu.emu_start(STUB | 1, SENTINEL, count=20000)
        self.assertEqual(reached, [0x1de])
        self.assertEqual(word(cpu, PMU), 0)

    def test_incoming_work_after_guards_survives_modeled_wake(self):
        def arriving_work(cpu):
            cpu.mem_write(0x20000188, b'\x01')
            put(cpu, 0x4001c014, 4)
            # Model ISR caller-saved clobbers; R4/R5 must survive by ABI.
            for r in REGS[:3]:
                cpu.reg_write(r, 0x9876)

        cpu, sleeps, _ = self.execute(at_wfi=arriving_work)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(cpu.mem_read(0x20000188, 1), b'\x01')
        self.assertEqual(word(cpu, 0x4001c014), 4)
        _, sleeps, writes = self.execute(cpu)
        self.assertEqual(sleeps, [])
        self.assertEqual(writes, [])

    def test_all_read_only_skip_guards(self):
        cases = [
            ('stock auto-sleep enabled', 0x20000166, 0, 1),
            ('USB mode', 0x200001b8, 0, 1),
            ('other mode', 0x200001b8, 2, 1),
            ('forced sleep', 0x20000193, 1, 1),
            ('MCU attention', 0x40044000, 1, 4),
            ('radio attention', 0x40044000, 2, 4),
            ('outgoing queue 0', 0x20000104, 1, 1),
            ('outgoing queue 1', 0x20000105, 1, 1),
            ('outgoing queue 3', 0x20000107, 1, 1),
            ('incoming packet', 0x20000188, 1, 1),
            ('SPI raw receive status', 0x4001c014, 4, 4),
            ('sleep-on-exit', 0xe000ed10, 2, 4),
            ('sleep-deep', 0xe000ed10, 4, 4),
            ('SPI IRQ disabled', IRQ, 0x10000, 4),
            ('scan IRQ disabled', IRQ, 0x40, 4),
            ('SPI clock disabled', CLOCK, 0x80, 4),
            ('scan clock disabled', CLOCK, 0x1000, 4),
            ('timer stopped', TIMER, 0, 4),
            ('timer match interrupt disabled', TIMER+0x1c, 0x6000, 4),
            ('exceptional PMU state', PMU, 2, 4),
        ]
        for name, address, value, size in cases:
            with self.subTest(name=name):
                cpu = machine(self.image)
                cpu.mem_write(address, value.to_bytes(size, 'little'))
                _, sleeps, writes = self.execute(cpu)
                self.assertEqual(sleeps, [])
                self.assertEqual(writes, [])
                self.assertEqual(int.from_bytes(cpu.mem_read(address, size), 'little'), value)

    def test_masked_interrupts_skip_without_changing_mask(self):
        cpu = machine(self.image)
        cpu.reg_write(reg.UC_ARM_REG_PRIMASK, 1)
        cpu, sleeps, writes = self.execute(cpu)
        self.assertEqual((sleeps, writes), ([], []))
        self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_PRIMASK), 1)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'test_methods_run': result.testsRun, 'guard_subcases': 20,
              'passed': result.wasSuccessful(), 'device_access': False, 'flashed': False,
              'wfi': 'Intercepted; modeled immediate interrupt return, not physical sleep.',
              'image_sha256': sha((OUT / 'candidate.bin').read_bytes()),
              'hardware_wakeup_verified': False, 'current_draw_measured': False}
    (OUT / 'test-results.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
