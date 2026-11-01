"""Offline component tests. No device access, firmware-image or boot integration.

Model address 0x20e000 is deliberately NOT approved for the physical keyboard.
The existing allocator and HID transport are mocked; actual captured ROM
get-report and 28-bit elapsed-clock helpers execute in Unicorn.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as reg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'firmware/radio_battery_component.S'
MODEL_BASE, OBJECT, SHADOW = 0x20e000, 0x20c9d4, 0x20d800
TRANSPORT, TRANSPORT_TABLE, CALLBACK, RETURN = 0x20d900, 0x20da00, 0x70000, 0x71000
OUT_SIZE, STACK = 0x20db00, 0x20ed00
KEEP = [reg.UC_ARM_REG_R4, reg.UC_ARM_REG_R5, reg.UC_ARM_REG_R6, reg.UC_ARM_REG_R7,
        reg.UC_ARM_REG_R8, reg.UC_ARM_REG_R9, reg.UC_ARM_REG_R10, reg.UC_ARM_REG_R11]


def put(cpu, addr, n):
    cpu.mem_write(addr, struct.pack('<I', n))


def word(cpu, addr):
    return struct.unpack('<I', cpu.mem_read(addr, 4))[0]


def compile_component():
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / 'battery.o'
        subprocess.run(['xcrun', 'clang', '--target=armv7m-none-eabi', '-mcpu=cortex-m3',
                        '-mthumb', '-c', str(SOURCE), '-o', str(obj)], check=True)
        with obj.open('rb') as stream:
            elf = ELFFile(stream)
            assert not any(s.num_relocations() for s in elf.iter_sections()
                           if hasattr(s, 'num_relocations'))
            code = bytearray(elf.get_section_by_name('.text').data())
            names = ['battery_install', 'get_report', 'notify', 'connected', 'code_end',
                     'address_getter', 'address_notify', 'address_connect']
            symbols = {s.name: s['st_value'] & ~1 for s in
                       elf.get_section_by_name('.symtab').iter_symbols() if s.name in names}
    for slot, target in [('address_getter', 'get_report'), ('address_notify', 'notify'),
                         ('address_connect', 'connected')]:
        struct.pack_into('<I', code, symbols[slot], (MODEL_BASE + symbols[target]) | 1)
    return code, symbols


class RadioComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.symbols = compile_component()
        cls.rom_table = (ROOT / 'private/rom-04b000.bin').read_bytes()[0x12f4:0x12f4+60]
        assert len(cls.rom_table) == 60
        assert struct.unpack_from('<III', cls.rom_table, 8) == (0x28e3, 0x290b, 0x2925)
        cls.clock_rom = (ROOT / 'private/rom-010000-bulk.bin').read_bytes()
        assert len(cls.clock_rom) == 65536
        cls.clock_address = struct.unpack_from('<I', cls.clock_rom, 0x71a0)[0]
        assert cls.clock_address == 0x318088  # Captured native-clock register.

    def setUp(self):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.mem_map(0, 0x80000)
        self.cpu.mem_map(0x200000, 0x10000)
        self.cpu.mem_map(0x318000, 0x1000)  # Modeled clock register only.
        self.cpu.mem_write(0x2000, (ROOT / 'private/rom-002000.bin').read_bytes())
        self.cpu.mem_write(0x10000, self.clock_rom)
        self.cpu.mem_write(0x4c2f4, self.rom_table)
        self.cpu.mem_write(0x200000, (ROOT / 'private/ram-200000.bin').read_bytes())
        self.cpu.mem_write(MODEL_BASE, bytes(self.code))
        self.cpu.mem_write(CALLBACK, bytes.fromhex('00207047'))
        put(self.cpu, TRANSPORT, TRANSPORT_TABLE)
        put(self.cpu, TRANSPORT_TABLE + 0x2c, CALLBACK | 1)
        put(self.cpu, OBJECT, 0x4c2f4)
        self.cpu.mem_write(OBJECT+4, b'\x03\x00')
        self.cpu.mem_write(OBJECT+0x14, b'\x3a')
        self.cpu.mem_write(0x2005c8+0x11, b'\x03\x08\x00')
        self.allocation_result, self.allocations, self.emitted, self.writes = SHADOW, [], [], []
        self.clock(1000)

        def observe(cpu, address, size, data):
            if address == 0x1676e:
                self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_SP) % 8, 0)
                self.allocations.append(cpu.reg_read(reg.UC_ARM_REG_R0))
                cpu.reg_write(reg.UC_ARM_REG_R0, self.allocation_result)
                cpu.reg_write(reg.UC_ARM_REG_PC, cpu.reg_read(reg.UC_ARM_REG_LR))
            elif address == CALLBACK:
                self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_SP) % 8, 0)
                self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_R0), TRANSPORT)
                self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_R2), 8)
                self.assertEqual(cpu.reg_read(reg.UC_ARM_REG_R3), 1)
                self.assertEqual(word(cpu, cpu.reg_read(reg.UC_ARM_REG_SP)), 1)
                self.assertEqual(word(cpu, cpu.reg_read(reg.UC_ARM_REG_SP)+4), 0)
                payload = list(cpu.mem_read(cpu.reg_read(reg.UC_ARM_REG_R1), 2))
                self.emitted.append(payload)

        def written(cpu, access, address, size, value, data):
            self.writes.append((address, size, value))

        self.cpu.hook_add(UC_HOOK_CODE, observe)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, written)

    def clock(self, value):
        put(self.cpu, self.clock_address, value & 0xfffffff)

    def call(self, entry, r0=OBJECT, r1=0, r2=0, r3=0):
        for register, value in zip([reg.UC_ARM_REG_R0, reg.UC_ARM_REG_R1,
                                    reg.UC_ARM_REG_R2, reg.UC_ARM_REG_R3], [r0, r1, r2, r3]):
            self.cpu.reg_write(register, value)
        for i, register in enumerate(KEEP):
            self.cpu.reg_write(register, 0x12340000+i)
        self.cpu.reg_write(reg.UC_ARM_REG_SP, STACK)
        self.cpu.reg_write(reg.UC_ARM_REG_LR, RETURN | 1)
        self.cpu.emu_start(entry | 1, RETURN, count=1000)
        self.assertEqual(self.cpu.reg_read(reg.UC_ARM_REG_PC), RETURN)
        self.assertEqual(self.cpu.reg_read(reg.UC_ARM_REG_SP), STACK)
        self.assertEqual([self.cpu.reg_read(r) for r in KEEP], [0x12340000+i for i in range(8)])
        return self.cpu.reg_read(reg.UC_ARM_REG_R0)

    def install(self):
        self.assertEqual(self.call(MODEL_BASE + self.symbols['battery_install']), 1)

    def method(self, offset, **args):
        return self.call(word(self.cpu, word(self.cpu, OBJECT)+offset), **args)

    def test_copies_all_methods_and_publishes_pointer_last(self):
        self.install()
        self.assertEqual(self.allocations, [68])
        expected = bytearray(self.rom_table)
        for offset, target in [(8, 'notify'), (12, 'get_report'), (16, 'connected')]:
            struct.pack_into('<I', expected, offset, (MODEL_BASE+self.symbols[target]) | 1)
        self.assertEqual(self.cpu.mem_read(SHADOW, 60), bytes(expected))
        table_writes = [i for i, (a, _, _) in enumerate(self.writes) if SHADOW <= a < SHADOW+68]
        object_writes = [i for i, (a, _, _) in enumerate(self.writes) if a == OBJECT]
        self.assertEqual(len(object_writes), 1)
        self.assertGreater(object_writes[0], max(table_writes))

    def test_idempotence(self):
        self.install()
        self.assertEqual(self.call(MODEL_BASE), 0)
        self.assertEqual(self.allocations, [68])
        self.assertEqual(word(self.cpu, OBJECT), SHADOW)

    def test_allocation_failure_preserves_original(self):
        self.allocation_result = 0
        self.assertEqual(self.call(MODEL_BASE), 0)
        self.assertEqual(word(self.cpu, OBJECT), 0x4c2f4)
        self.assertEqual(self.writes[-1][0], STACK-4)  # Only stack frame writes.
        self.assertFalse(any(OBJECT <= a < OBJECT+0x74 for a, _, _ in self.writes))

    def test_invalid_objects_are_not_dereferenced_or_allocated(self):
        for obj in (0, 1, 0x1000, 0x200001, 0x20fffc, 0x40000000):
            self.assertEqual(self.call(MODEL_BASE, r0=obj), 0)
        self.assertEqual(self.allocations, [])

    def test_other_object_type_preserved(self):
        put(self.cpu, OBJECT, 0x4c300)
        self.assertEqual(self.call(MODEL_BASE), 0)
        self.assertEqual(word(self.cpu, OBJECT), 0x4c300)
        self.assertEqual(self.allocations, [])

    def test_bad_allocator_pointer_not_published(self):
        for pointer in (1, 0x70000, 0x20fffc, 0x40000000):
            self.allocation_result = pointer
            self.assertEqual(self.call(MODEL_BASE), 0)
            self.assertEqual(word(self.cpu, OBJECT), 0x4c2f4)

    def test_known_heap_exhaustion_skips_allocator(self):
        for cursor in (0, 0x20eeb9, 0x20eeba, 0x20eebb, 0x20eebc, 0x20eec0, 0x20ef00, 0xffffffff):
            put(self.cpu, 0x200e90, cursor)
            self.assertEqual(self.call(MODEL_BASE), 0)
            self.assertEqual(word(self.cpu, OBJECT), 0x4c2f4)
        self.assertEqual(self.allocations, [])

    def test_getter_matches_full_range_and_preserves_length_neighbors(self):
        self.install()
        for measured in range(101):
            self.cpu.mem_write(OBJECT+0x14, bytes([measured]))
            self.cpu.mem_write(OUT_SIZE, b'\xa5'*4)
            pointer = self.method(12, r1=1, r2=3, r3=OUT_SIZE)
            self.assertEqual(list(self.cpu.mem_read(pointer, 2)), [3, measured])
            self.assertEqual(self.cpu.mem_read(OUT_SIZE, 4), b'\x08\xa5\xa5\xa5')

    def test_invalid_measurement_and_other_reports(self):
        self.install()
        for measured, kind, rid in [(101, 1, 3), (255, 1, 3), (58, 3, 3), (58, 1, 7), (58, 2, 3)]:
            self.cpu.mem_write(OBJECT+0x14, bytes([measured]))
            self.cpu.mem_write(OBJECT+5, b'\x00')
            self.assertEqual(self.method(12, r1=kind, r2=rid, r3=OUT_SIZE), 0)
            self.assertEqual(self.cpu.mem_read(OBJECT+5, 1), b'\x00')

    def test_initial_zero_cache_and_both_notification_directions(self):
        self.install()
        for i, measured in enumerate((58, 90, 20, 0, 100)):
            self.clock(1000+i*192000)
            self.cpu.mem_write(OBJECT+0x14, bytes([measured]))
            self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, n] for n in (58, 90, 20, 0, 100)])

    def test_duplicate_suppression(self):
        self.install()
        self.method(8, r1=TRANSPORT)
        self.clock(400000)
        self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, 58]])

    def test_rate_limit_retains_pending_estimate(self):
        self.install()
        self.method(8, r1=TRANSPORT)
        self.cpu.mem_write(OBJECT+0x14, b'\x39')
        self.clock(1000+191999)
        self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, 58]])
        self.assertEqual(self.cpu.mem_read(OBJECT+5, 1), b'\x3a')
        self.clock(1000+192000)
        self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, 58], [3, 57]])

    def test_clock_wrap_uses_actual_rom_elapsed_helper(self):
        self.install()
        self.clock(0x10000000-1000)
        self.method(8, r1=TRANSPORT)
        self.cpu.mem_write(OBJECT+0x14, b'\x39')
        self.clock(190999)
        self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, 58]])
        self.clock(191000)
        self.method(8, r1=TRANSPORT)
        self.assertEqual(self.emitted[-1], [3, 57])

    def test_connection_reports_immediately_with_stock_flag_disabled(self):
        self.install()
        self.method(16, r1=TRANSPORT)
        self.method(16, r1=TRANSPORT)
        self.assertEqual(self.emitted, [[3, 58], [3, 58]])
        self.assertEqual(self.cpu.mem_read(0x2005c8+0x13, 1), b'\x00')

    def test_null_transport_and_invalid_measurement_do_not_publish(self):
        self.install()
        self.method(8, r1=0)
        for measured in (101, 255):
            self.cpu.mem_write(OBJECT+0x14, bytes([measured]))
            self.method(8, r1=TRANSPORT)
            self.method(16, r1=TRANSPORT)
        self.assertEqual(self.emitted, [])
        self.assertEqual(self.cpu.mem_read(OBJECT+5, 1), b'\x00')


if __name__ == '__main__':
    results = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RadioComponentTests))
    report = {'scope': 'Isolated Bluetooth battery component, emulator only; no physical placement, boot hook or persistent update image',
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'test_methods': results.testsRun, 'all_percentage_values_tested': 101,
              'passed': results.wasSuccessful(), 'code_and_literals_bytes': len(RadioComponentTests.code),
              'allocated_shadow_table_state_bytes': 68, 'model_base_not_physical_allocation': hex(MODEL_BASE),
              'real_rom_getter_and_elapsed_helper_executed': True,
              'allocator_and_transport_mocked': True, 'macos_ui_verified': False,
              'firmware_image_produced': False, 'device_access': False, 'flashed': False}
    path = ROOT / 'artifacts/k2-v2-rgb-cpu-idle-a/battery-component-tests.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if results.wasSuccessful() else 1)
