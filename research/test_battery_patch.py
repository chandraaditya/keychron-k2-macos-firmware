"""Emulate captured ROM and an offline candidate; never opens a real device."""
import io
import json
import struct
import subprocess
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR,
)

ROOT = Path(__file__).resolve().parents[1]
RAM = (ROOT / 'private/ram-200000.bin').read_bytes()
ROM = (ROOT / 'private/rom-002000.bin').read_bytes()
assert len(RAM) == 65536 and len(ROM) == 4096
assert ROM[0x90A:0x90E] == bytes.fromhex('10b50129')

objfile = ROOT / 'build/battery-get-report-candidate.o'
subprocess.run([
    'xcrun', 'clang', '-target', 'armv7m-none-eabi', '-mcpu=cortex-m3',
    '-mthumb', '-c', str(ROOT / 'research/battery_get_report_candidate.S'),
    '-o', str(objfile),
], check=True)
candidate = ELFFile(io.BytesIO(objfile.read_bytes())).get_section_by_name('.text').data()
OBJECT, OUT_SIZE, STACK, PATCH, RETURN = 0x20C9D4, 0x20E000, 0x20EC00, 0x20F000, 0x20EF00
KEEP = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]


def call(patched, measured, cached, kind=1, report_id=3):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x10000)
    cpu.mem_map(0x200000, 0x10000)
    cpu.mem_write(0x2000, ROM)
    cpu.mem_write(0x200000, RAM)
    cpu.mem_write(PATCH, candidate)
    cpu.mem_write(OBJECT + 5, bytes([cached]))
    cpu.mem_write(OBJECT + 0x14, bytes([measured]))
    cpu.mem_write(OUT_SIZE, bytes.fromhex('a5a5a5a5'))
    cpu.reg_write(UC_ARM_REG_R0, OBJECT)
    cpu.reg_write(UC_ARM_REG_R1, kind)
    cpu.reg_write(UC_ARM_REG_R2, report_id)
    cpu.reg_write(UC_ARM_REG_R3, OUT_SIZE)
    for index, reg in enumerate(KEEP):
        cpu.reg_write(reg, 0x10101010 + index)
    cpu.reg_write(UC_ARM_REG_SP, STACK)
    cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
    cpu.emu_start((PATCH if patched else 0x290A) | 1, RETURN, count=100)
    for index, reg in enumerate(KEEP):
        assert cpu.reg_read(reg) == 0x10101010 + index, 'Callee-saved register changed'
    assert cpu.reg_read(UC_ARM_REG_SP) == STACK, 'Stack pointer changed'
    result = cpu.reg_read(UC_ARM_REG_R0)
    payload = list(cpu.mem_read(result, 2)) if result else None
    out_size = cpu.mem_read(OUT_SIZE, 1)[0]
    assert bytes(cpu.mem_read(OUT_SIZE + 1, 3)) == b'\xa5' * 3, 'Length output overwrote adjacent memory'
    cache = cpu.mem_read(OBJECT + 5, 1)[0]
    return payload, out_size, cache


assert call(False, 58, 0)[:2] == ([3, 0], 8)
assert call(True, 58, 0)[:2] == ([3, 58], 8)
cases = 2
for measured, cached in [(0, 58), (1, 0), (20, 58), (58, 0), (58, 58), (90, 58), (100, 0)]:
    payload, bits, cache = call(True, measured, cached)
    assert payload == [3, measured] and bits == 8 and cache == measured
    cases += 1
for kind, report_id in [(3, 3), (1, 7), (2, 3)]:
    payload, _, cache = call(True, 58, 0, kind, report_id)
    assert payload is None and cache == 0
    cases += 1
payload, _, cache = call(True, 101, 0)
assert payload is None and cache == 0
cases += 1


def notification(changed_comparison, measured, cached):
    """Exercise the actual ROM notification routine, with a fake transport only."""
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x10000)
    cpu.mem_map(0x200000, 0x10000)
    cpu.mem_write(0x2000, ROM)
    cpu.mem_write(0x200000, RAM)
    assert bytes(cpu.mem_read(0x28EC, 2)) == b'\x0c\xd2'  # BHS: skip >= cached
    if changed_comparison:
        # Emulator memory only. Physical ROM is immutable; deployment would need a hook.
        cpu.mem_write(0x28EC, b'\x0c\xd0')  # BEQ: skip only unchanged
    transport, table, callback = 0x20D800, 0x20D900, 0x6000
    cpu.mem_write(transport, struct.pack('<I', table))
    cpu.mem_write(table + 0x2C, struct.pack('<I', callback | 1))
    cpu.mem_write(callback, bytes.fromhex('00207047'))  # return zero
    cpu.mem_write(OBJECT + 5, bytes([cached]))
    cpu.mem_write(OBJECT + 0x14, bytes([measured]))
    cpu.reg_write(UC_ARM_REG_R0, OBJECT)
    cpu.reg_write(UC_ARM_REG_R1, transport)
    cpu.reg_write(UC_ARM_REG_SP, STACK)
    cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
    emitted = []

    def observe(uc, address, size, context):
        if address == callback:
            assert uc.reg_read(UC_ARM_REG_R0) == transport
            assert uc.reg_read(UC_ARM_REG_R2) == 8
            emitted.append(list(uc.mem_read(uc.reg_read(UC_ARM_REG_R1), 2)))

    cpu.hook_add(UC_HOOK_CODE, observe)
    cpu.emu_start(0x28E3, RETURN, count=100)
    assert cpu.reg_read(UC_ARM_REG_SP) == STACK
    return emitted


assert notification(False, 58, 0) == []
assert notification(False, 90, 58) == []
assert notification(False, 20, 58) == [[3, 20]]
cases += 3
for measured, cached in [(58, 0), (90, 58), (20, 58), (0, 58), (100, 0)]:
    assert notification(True, measured, cached) == [[3, measured]]
    cases += 1
assert notification(True, 58, 58) == []
cases += 1

report = {
    'scope': 'Offline ARM emulation only; no hardware or macOS Bluetooth UI test',
    'cases_passed': cases,
    'original_report_with_measured_58_cached_0': [3, 0],
    'candidate_report_with_measured_58_cached_0': [3, 58],
    'candidate_code_and_literal_bytes': len(candidate),
    'notification_experiment': 'Original skips upward changes; equality-only comparison emits both directions and skips unchanged values',
    'flashed': False,
}
output = ROOT / 'private/battery-candidate-emulation.json'
output.write_text(json.dumps(report, indent=2) + '\n')
output.chmod(0o600)
print(json.dumps(report, indent=2))
