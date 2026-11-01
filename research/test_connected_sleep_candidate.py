"""Offline V2-reference CPU-sleep entry and incoming-SPI experiments.

No device access. Changes exist in emulator memory only. MMIO is a minimal
register model, not a silicon/interrupt/timing or power simulator. These tests
do not constitute a deployable image or prove wake on the installed keyboard.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import (Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
                     UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
IMAGE = (PRIVATE / 'vendor/k2v2-rgb-1.13-resource-4000.bin').read_bytes()
assert hashlib.sha256(IMAGE).hexdigest() == '256b602f7661c924c614a622f29add82e7acde51af93a7c0afbac17ffaf9ad54'
assert IMAGE[0x24a:0x24c] == bytes.fromhex('0221')  # MOVS r1, #2


def word(cpu, address):
    return struct.unpack('<I', cpu.mem_read(address, 4))[0]


def put(cpu, address, value):
    cpu.mem_write(address, struct.pack('<I', value))


def machine():
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x11000)
    cpu.mem_write(0, IMAGE)
    cpu.mem_map(0x20000000, 0x2000)
    cpu.mem_map(0x40000000, 0x100000)
    cpu.mem_map(0xe000e000, 0x1000)
    return cpu


def call(cpu, address):
    cpu.reg_write(UC_ARM_REG_SP, 0x20001f00)
    cpu.reg_write(UC_ARM_REG_LR, 0x10001)
    cpu.emu_start(address | 1, 0x10000, count=20000)


def sleep_entry(light):
    cpu = machine()
    # Separate local idle from radio disconnect, as in the earlier experiment.
    cpu.mem_write(0x1c8, bytes.fromhex('0029'))
    if light:
        # Keep the high-speed oscillator/clock selection; request CPU-only sleep.
        cpu.mem_write(0x242, bytes.fromhex('00bf00bf'))  # Omit BL clock_slow.
        cpu.mem_write(0x24a, bytes.fromhex('0421'))      # MOVS r1, #4.
    cpu.mem_write(0x20000166, b'\x01')
    cpu.mem_write(0x200001ba, b'\x01')
    put(cpu, 0x200001ac, 1)
    put(cpu, 0x4005e000, (1 << 12) | (1 << 7))  # SPI0 and scan timer clocks.
    put(cpu, 0xe000e100, 1 << 6)                # SPI0 IRQ already enabled.
    reached = []
    irq_enable = [1 << 6]

    def nvic_write(uc, access, address, size, value, data):
        # NVIC ISER/ICER are write-one-set/clear, not ordinary RAM assignment.
        if address == 0xe000e100:
            irq_enable[0] |= value
        elif address == 0xe000e180:
            irq_enable[0] &= ~value

    def observe(uc, address, size, data):
        put(uc, 0xe000e100, irq_enable[0])
        if address == 0x425a:
            # Initial SPI housekeeping mocked; bus is assumed quiet at entry.
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif address == 0xc92:
            # Deep-reference oscillator-ready polling: model status, not time.
            put(uc, 0x4006000c, word(uc, 0x4006000c) | 0x10)
        elif address == 0x24e:
            reached.append(True)
            uc.emu_stop()  # Never pretend to execute real sleep/wake.

    cpu.hook_add(UC_HOOK_CODE, observe)
    cpu.hook_add(UC_HOOK_MEM_WRITE, nvic_write)
    call(cpu, 0x194)
    assert reached
    result = {
        'requested_pmu_mode': word(cpu, 0x40032040),
        'spi_clock_enable_retained': bool(word(cpu, 0x4005e000) & (1 << 12)),
        'scan_timer_clock_disabled': not bool(word(cpu, 0x4005e000) & (1 << 7)),
        'spi_irq_enable_retained': bool(word(cpu, 0xe000e100) & (1 << 6)),
        'systick_disabled': word(cpu, 0xe000e010) == 0,
        'clock_configuration': hex(word(cpu, 0x4006000c)),
        'auto_sleep_disable_setting_retained': cpu.mem_read(0x20000166, 1)[0] == 1,
    }
    assert result['requested_pmu_mode'] == (4 if light else 2)
    assert all(result[k] for k in ['spi_clock_enable_retained', 'scan_timer_clock_disabled',
                                  'spi_irq_enable_retained', 'systick_disabled',
                                  'auto_sleep_disable_setting_retained']), result
    assert word(cpu, 0x4006000c) == (0 if light else 0x11)
    return result


def receive(packet, expected_address, expected_value):
    cpu = machine()
    put(cpu, 0x40044000, 2)  # Module attention A1 high during its transfer.
    put(cpu, 0x4001c014, 4)  # RX FIFO threshold interrupt status.
    current = [0]

    def fifo_read(uc, access, address, size, value, data):
        if address == 0x4001c01c:
            put(uc, address, current[0])

    def observe(uc, address, size, data):
        if address == 0x10000:
            uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, fifo_read)
    cpu.hook_add(UC_HOOK_CODE, observe)
    for byte in packet:
        current[0] = byte
        call(cpu, 0x4aea)  # Actual reference SPI IRQ handler, manually invoked.
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x10000
    assert word(cpu, 0x200001a8) == len(packet)
    assert [struct.unpack('<H', cpu.mem_read(0x20000390 + i * 2, 2))[0]
            for i in range(len(packet))] == packet
    call(cpu, 0x425a)  # Actual reference main-loop SPI parser.
    assert cpu.reg_read(UC_ARM_REG_PC) == 0x10000
    assert cpu.mem_read(expected_address, 1)[0] == expected_value
    assert word(cpu, 0x200001a8) == 0
    return {'packet': packet, 'receive_irq_executions': len(packet),
            'parser_output_address': hex(expected_address), 'parser_output': expected_value}


def main():
    cases = [
        {'case': 'Original deep-sleep entry', 'result': sleep_entry(False)},
        {'case': 'Experimental retained-clock CPU-sleep entry', 'result': sleep_entry(True)},
        {'case': 'Host LED state through existing IRQ/parser',
         'result': receive([0xb1, 2], 0x20000268, 2)},
        {'case': 'Low battery notice through existing IRQ/parser',
         'result': receive([0xb6, 0x5a, 6], 0x20000190, 1)},
    ]
    report = {
        'scope': 'Offline execution of published V2 RGB 1.13; no real device or timing model',
        'reference_sha256': hashlib.sha256(IMAGE).hexdigest(),
        'cases_passed': len(cases), 'device_access': False, 'flashed': False,
        'interrupt_arrival_simulated': False, 'hardware_wakeup_verified': False,
        'power_measured': False, 'installed_main_firmware_verified': False,
        'limits': ['Bus quiescence assumed, not implemented as a complete entry guard.',
                   'IRQ handler manually invoked; no electrical FIFO/interrupt or real WFI model.',
                   'Parser replay is separate from sleep entry; full hardware wake/resume unverified.',
                   'Retained SPI clocks do not establish a current draw or monthly runtime.',
                   'Candidate changes emulator memory only and produce no flashable image.'],
        'cases': cases,
    }
    path = PRIVATE / 'connected-sleep-candidate-emulation.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    path.chmod(0o600)
    print(json.dumps({k: report[k] for k in ['cases_passed', 'device_access', 'flashed',
                                          'hardware_wakeup_verified', 'power_measured']}))


if __name__ == '__main__':
    main()
