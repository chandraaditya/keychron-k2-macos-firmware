"""Offline analysis of captured K2 code. Does not open or modify any device."""
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'


def main():
    ram = (PRIVATE / 'ram-200000.bin').read_bytes()
    rom = (PRIVATE / 'rom-01b000.bin').read_bytes()
    monitor_rom = (PRIVATE / 'rom-002000.bin').read_bytes()
    tables = (PRIVATE / 'rom-04b000.bin').read_bytes()

    def word(address):
        if 0x200000 <= address <= 0x210000 - 4:
            return struct.unpack_from('<I', ram, address - 0x200000)[0]
        if 0x4b000 <= address <= 0x4d000 - 4:
            return struct.unpack_from('<I', tables, address - 0x4b000)[0]
        raise ValueError(f'Address outside captured data: {address:#x}')

    battery = word(0x208ea8)
    sensor = word(battery + 0x64)
    sensor_table = word(sensor)
    conversion = word(sensor_table + 4) & ~1
    assert conversion == 0x1b3ac, 'Unexpected captured conversion method'
    config = 0x2005c8
    upper = struct.unpack_from('<H', ram, config - 0x200000 + 10)[0]
    lower = struct.unpack_from('<H', ram, config - 0x200000 + 12)[0]
    scale = ram[config - 0x200000 + 16]
    window = ram[config - 0x200000 + 9]
    assert (lower, upper, scale, window) == (1520, 1920, 100, 8)

    # Execute the actual captured conversion routine, without any ADC/hardware call.
    emu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    emu.mem_map(0x1b000, 0x1000)
    emu.mem_write(0x1b000, rom)
    emu.mem_map(0x200000, 0x10000)
    emu.mem_write(0x200000, ram)
    stop = 0x70000
    emu.mem_map(stop, 0x1000)

    def captured_percent(raw):
        emu.reg_write(UC_ARM_REG_R0, sensor)
        emu.reg_write(UC_ARM_REG_R1, raw)
        emu.reg_write(UC_ARM_REG_LR, stop | 1)
        emu.emu_start(conversion | 1, stop, count=100)
        return emu.reg_read(UC_ARM_REG_R0)

    for raw in range(4096):
        expected = min(scale, max(0, (raw - lower) * scale // (upper - lower)))
        actual = captured_percent(raw)
        assert actual == expected, (raw, actual, expected)

    # All points below were previously read from the keyboard, not generated data.
    observations = [(1753, 58), (1733, 53), (1731, 52), (1816, 74),
                    (1858, 84), (1859, 84), (1855, 83), (1814, 73),
                    (1745, 56), (1785, 66), (1857, 84), (1784, 66)]
    verified = []
    for raw, measured in observations:
        actual = captured_percent(raw)
        assert actual == measured, (raw, actual, measured)
        verified.append({'raw_sensor_average': raw, 'observed_percent': measured,
                         'captured_routine_percent': actual})

    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    snippets = {}
    for name, data, base, start, end in [
        ('sensor_to_percentage', rom, 0x1b000, conversion, 0x1b3d0),
        ('rolling_average', monitor_rom, 0x2000, 0x2a2e, 0x2aae),
        ('percentage_store', monitor_rom, 0x2000, 0x2aae, 0x2ac0),
    ]:
        snippets[name] = [f'{i.address:08x}: {i.mnemonic} {i.op_str}'
                          for i in disassembler.disasm(data[start-base:end-base], start)]

    provenance = []
    for name in ['ram-200000.bin', 'rom-01b000.bin', 'rom-014000.bin',
                 'rom-015000.bin', 'rom-002000.bin', 'rom-04b000.bin']:
        data = (PRIVATE / name).read_bytes()
        provenance.append({'file': name, 'bytes': len(data),
                           'sha256': hashlib.sha256(data).hexdigest()})

    report = {'firmware_build': '20191025', 'device_access': False,
              'conversion_address': hex(conversion), 'config_address': hex(config),
              'lower_raw': lower, 'upper_raw': upper, 'full_scale_percent': scale,
              'rolling_average_samples': window,
              'formula': 'clamp(floor((raw_average - 1520) / 4), 0, 100)',
              'exhaustive_raw_inputs_verified': 4096,
              'observed_points_verified': verified, 'disassembly': snippets,
              'provenance': provenance,
              'limits': ['Raw units have not been independently calibrated to volts.',
                         'Conversion has no charging/current/temperature argument; upstream '
                         'sensor calibration and board circuitry are not fully characterized.',
                         'Does not measure capacity, standby current or battery health.']}
    out = PRIVATE / 'battery-estimator-analysis.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    out.chmod(0o600)
    print(json.dumps({k: report[k] for k in ['firmware_build', 'formula',
          'rolling_average_samples', 'exhaustive_raw_inputs_verified']}))
    print(f'All {len(observations)} recorded sensor/percentage pairs match captured code.')


if __name__ == '__main__':
    main()
