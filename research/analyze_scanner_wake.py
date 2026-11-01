"""Inspect published code and emulate wake-register setup, without a device.

MMIO is ordinary emulator memory. We check which register writes the code
requests, not electrical edges, interrupt delivery, clock timing or real wake.
"""
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from capstone.arm import ARM_OP_MEM, ARM_REG_PC
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from test_scanner_idle_policy import SONIX, PROFILES, PRIVATE


def requested_wake_masks(entries):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x11000)
    cpu.mem_write(0, SONIX)
    cpu.mem_map(0x20000000, 0x2000)
    cpu.mem_map(0x40000000, 0x100000)
    cpu.mem_map(0xe000e000, 0x1000)
    writes = []

    def record(uc, access, address, size, value, data):
        if address >= 0x40000000:
            writes.append({'address': hex(address), 'value': hex(value)})

    cpu.hook_add(UC_HOOK_MEM_WRITE, record)
    for entry in entries:
        cpu.reg_write(UC_ARM_REG_SP, 0x20001f00)
        cpu.reg_write(UC_ARM_REG_LR, 0x10001)
        cpu.emu_start(entry | 1, 0x10000, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x10000
        assert cpu.reg_read(UC_ARM_REG_SP) == 0x20001f00

    masks = {}
    for name, base in [('P0', 0x40044000), ('P2', 0x40048000), ('P3', 0x4004a000)]:
        masks[name] = struct.unpack('<I', cpu.mem_read(base + 0x18, 4))[0]
    return {'entry_points': [hex(e) for e in entries],
            'interrupt_enable_masks': {k: hex(v) for k, v in masks.items()},
            'requested_register_writes': writes}


def disassemble(image, start, end):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    md.detail = True
    lines = []
    for insn in md.disasm(image[start:end], start):
        annotation = ''
        if (insn.mnemonic == 'ldr' and len(insn.operands) > 1
                and insn.operands[1].type == ARM_OP_MEM
                and insn.operands[1].mem.base == ARM_REG_PC):
            at = ((insn.address + 4) & ~3) + insn.operands[1].mem.disp
            value = struct.unpack_from('<I', image, at)[0]
            annotation = f' ; literal [{at:08x}] = {value:08x}'
        lines.append(f'{insn.address:08x}: {insn.mnemonic:10s} {insn.op_str}{annotation}')
    return lines


def main():
    cases = []
    for entries, expected in [([0xab0], {'P0': '0x0', 'P2': '0x8000', 'P3': '0xf80'}),
                              ([0xaec], {'P0': '0x2', 'P2': '0x0', 'P3': '0x0'}),
                              ([0xab0, 0xaec], {'P0': '0x2', 'P2': '0x8000', 'P3': '0xf80'})]:
        result = requested_wake_masks(entries)
        assert result['interrupt_enable_masks'] == expected
        cases.append(result)
    snippets = {}
    for name, profile in PROFILES.items():
        end = 0x286 if name.startswith('V2') else 0x280
        snippets[name + ': wireless idle and sleep'] = disassemble(profile['image'], 0x194, end)
    for name, start, end in [('matrix wake setup', 0xab0, 0xaec),
                             ('alternate GPIO wake setup', 0xaec, 0xb18),
                             ('GPIO wake handlers', 0xa36, 0xab0),
                             ('auto-sleep toggle', 0x520, 0x544),
                             ('disable BT disconnect command', 0x4790, 0x47f0),
                             ('enable BT disconnect command', 0x47f0, 0x4850),
                             ('wireless main loop', 0x776, 0x7a4)]:
        snippets['V2 RGB 1.13: ' + name] = disassemble(SONIX, start, end)
    report = {
        'scope': 'Offline published-code inspection and register-write emulation only',
        'device_access': False, 'flashed': False, 'hardware_wakeup_verified': False,
        'cases_passed': len(cases), 'wake_setup_cases': cases,
        'sonix_v2_sha256': hashlib.sha256(SONIX).hexdigest(),
        'row_pin_reference': 'https://github.com/SonixQMK/qmk_firmware/blob/sn32_develop/keyboards/keychron/k2/rgb/v2/ansi/keyboard.json',
        'interpretation': 'Matrix setup enables C15 and D7-D11, matching all six '
                          'documented V2 rows. Alternate setup enables A1. Calling both '
                          'requests both masks without overwriting each other. Physical '
                          'A1 wiring, board revision, pending-edge races and SPI handshake '
                          'during connected sleep still require verification.',
        'snippets': snippets,
    }
    path = PRIVATE / 'scanner-wake-analysis.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    path.chmod(0o600)
    print(json.dumps({k: report[k] for k in ['cases_passed', 'device_access', 'flashed',
                                          'hardware_wakeup_verified']}))


if __name__ == '__main__':
    main()
