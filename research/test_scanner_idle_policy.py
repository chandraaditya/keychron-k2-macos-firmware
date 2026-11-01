"""Offline policy experiments on captured/downloaded K2 code; no device access.

The Sonix experiment changes two bytes in emulator memory only. It does not
produce a flash image or model electrical power, interrupts or actual wakeup.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR,
                              UC_ARM_REG_PC, UC_ARM_REG_SP)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
SONIX_PATH = PRIVATE / 'vendor/k2v2-rgb-1.13-resource-4000.bin'
SONIX = SONIX_PATH.read_bytes()
SONIX_V1 = (PRIVATE / 'vendor/k2-original-rgb-1.62-Settings_FWFiles_SN32F240B_32-00000000.bin').read_bytes()
RAM = (PRIVATE / 'ram-200000.bin').read_bytes()
assert hashlib.sha256(SONIX).hexdigest() == '256b602f7661c924c614a622f29add82e7acde51af93a7c0afbac17ffaf9ad54'
assert hashlib.sha256(SONIX_V1).hexdigest() == '9b883a0de5283248acfde785432010a418219651212911aeb95da979efecc62d'
assert SONIX[0x1c8:0x1ca] == bytes.fromhex('1143')  # ORRS r1, r2
assert SONIX_V1[0x1d4:0x1d6] == bytes.fromhex('1a43')  # ORRS r2, r3

PROFILES = {
    'V2 RGB 1.13': dict(image=SONIX, policy=0x20000166, pending=0x20000191,
                       tick=0x200001ba, force=0x20000193, count=0x200001ac,
                       patch=0x1c8, replacement='0029', housekeeping=0x425a,
                       sleep=0x1de),
    'V1 RGB 1.62': dict(image=SONIX_V1, policy=0x20000155, pending=0x20000180,
                       tick=0x200001a6, force=0x20000182, count=0x20000198,
                       patch=0x1d4, replacement='002a', housekeeping=0x3d68,
                       sleep=0x1e8),
}


def scanner(patched, disabled, pending, ticks, countdown=400, forced=0,
            profile='V2 RGB 1.13'):
    config = PROFILES[profile]
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x11000)
    cpu.mem_write(0, config['image'])
    cpu.mem_map(0x20000000, 0x2000)
    if patched:
        # Ignore the auto-disconnect setting when deciding local scanner idle.
        # Keep the pending-report guard, setting storage and command sender intact.
        cpu.mem_write(config['patch'], bytes.fromhex(config['replacement']))
    cpu.mem_write(config['policy'], bytes([disabled]))
    cpu.mem_write(config['pending'], bytes([pending]))
    cpu.mem_write(config['tick'], bytes([ticks]))
    cpu.mem_write(config['force'], bytes([forced]))
    cpu.mem_write(config['count'], struct.pack('<I', countdown))
    stack, end = 0x20001f00, 0x10000
    cpu.reg_write(UC_ARM_REG_SP, stack)
    cpu.reg_write(UC_ARM_REG_LR, end | 1)
    result = {'sleep_entry_reached': False, 'returned': False}

    def observe(uc, address, size, data):
        if address == config['housekeeping']:
            # Mock only SPI housekeeping; no bus/peripheral model is present.
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif address == config['sleep']:
            result['sleep_entry_reached'] = True
            uc.emu_stop()  # Do not pretend to simulate hardware sleep/wakeup.
        elif address == end:
            result['returned'] = True
            uc.emu_stop()

    cpu.hook_add(UC_HOOK_CODE, observe)
    cpu.emu_start(0x195, end + 2, count=1000)
    assert result['sleep_entry_reached'] or result['returned'], 'Unexpected control flow'
    if result['returned']:
        assert cpu.reg_read(UC_ARM_REG_SP) == stack
    result['countdown_after'] = struct.unpack('<I', cpu.mem_read(config['count'], 4))[0]
    result['auto_sleep_setting_after'] = cpu.mem_read(config['policy'], 1)[0]
    assert result['auto_sleep_setting_after'] == disabled, 'Experiment changed persisted-policy byte'
    return result


def bluetooth(disabled, countdown):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(0, 0x20000)
    cpu.mem_map(0x200000, 0x10000)
    cpu.mem_write(0x200000, RAM)
    main = 0x20c808
    assert struct.unpack_from('<I', RAM, main - 0x200000)[0] == 0x208d04
    cpu.mem_write(main + 0x12c, bytes([0xaa if disabled else 0x55]))
    cpu.mem_write(0x208eae, struct.pack('<H', countdown))
    stack, end = 0x20ee00, 0x1ff00
    cpu.reg_write(UC_ARM_REG_R0, main)
    cpu.reg_write(UC_ARM_REG_SP, stack)
    cpu.reg_write(UC_ARM_REG_LR, end | 1)

    def word(address):
        return struct.unpack('<I', cpu.mem_read(address, 4))[0]

    child = word(main + 0x4c)
    connected_method = word(word(child) + 0x34) & ~1
    transport = word(0x208e98)
    request_method = word(word(transport) + 0x18) & ~1
    result = {'timer_starts_ms': [], 'timer_stops': 0,
              'connection_sleep_requests': 0, 'returned': False}

    def observe(uc, address, size, data):
        if address == end:
            result['returned'] = True
            uc.emu_stop()
            return
        if address == 0x168a8:
            result['timer_starts_ms'].append(uc.reg_read(UC_ARM_REG_R1))
        elif address == 0x168d0:
            result['timer_stops'] += 1
        elif address == connected_method:
            uc.reg_write(UC_ARM_REG_R0, 1)
        elif address == request_method:
            result['connection_sleep_requests'] += 1
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    cpu.hook_add(UC_HOOK_CODE, observe)
    cpu.emu_start(0x207133, end + 2, count=1000)
    assert result['returned'] and cpu.reg_read(UC_ARM_REG_SP) == stack
    result['countdown_after'] = struct.unpack('<H', cpu.mem_read(0x208eae, 2))[0]
    return result


def main():
    results = []
    cases = [
        # patched, disabled, pending-report, tick, count, force, remaining, sleep
        (False, 1, 0, 1, 400, 0, 400, False),
        (True,  1, 0, 1, 400, 0, 399, False),
        (True,  1, 0, 1,   1, 0,   0, True),
        (False, 0, 0, 1,   1, 0,   0, True),
        (True,  0, 0, 1,   1, 0,   0, True),
        (True,  1, 1, 1, 400, 0, 400, False),
        (True,  1, 0, 0,   1, 0,   1, False),
        (True,  1, 0, 1, 400, 1, 399, True),
    ]
    for profile in PROFILES:
        for patch, disabled, pending, ticks, count, forced, remaining, sleep in cases:
            # The older image forces the countdown to one before decrementing.
            if profile == 'V1 RGB 1.62' and forced:
                remaining = 0
            actual = scanner(patch, disabled, pending, ticks, count, forced, profile)
            assert actual['countdown_after'] == remaining, (profile, actual, remaining)
            assert actual['sleep_entry_reached'] == sleep
            results.append({'cpu': 'Sonix published ' + profile,
                            'patched_in_emulator': patch, 'auto_sleep_disabled': disabled,
                            'pending_report': pending, 'tick_ready': ticks,
                            'countdown_before': count, 'forced_sleep': forced, 'result': actual})
    for disabled, count, remaining, sleep in [
            (True, 600, 600, 0), (True, 0, 0, 0),
            (False, 600, 599, 0), (False, 0, 0, 1)]:
        actual = bluetooth(disabled, count)
        assert actual['countdown_after'] == remaining
        assert actual['connection_sleep_requests'] == sleep
        if disabled:
            assert actual['timer_starts_ms'] == [] and actual['timer_stops'] == 1
        results.append({'cpu': 'captured installed Bluetooth 20191025',
                        'auto_sleep_disabled': disabled, 'countdown_before': count,
                        'result': actual})
    report = {'scope': 'Offline ARM execution with mocked peripherals/timers only',
              'cases_passed': len(results), 'device_access': False, 'flashed': False,
              'standby_current_measured': False, 'hardware_wakeup_verified': False,
              'candidate': 'Ignore auto-sleep-disable byte in Sonix local-idle countdown '
                           'while retaining existing Bluetooth disconnect-disable policy.',
              'sonix_payloads': [{
                  'reference': name, 'sha256': hashlib.sha256(p['image']).hexdigest(),
                  'emulator_only_change': {'address': hex(p['patch']),
                                          'original': p['image'][p['patch']:p['patch']+2].hex(),
                                          'experiment': p['replacement']}}
                  for name, p in PROFILES.items()],
              'critical_limit': 'Sonix reference image is not confirmed installed or compatible '
                                'with this physical PCB. Do not transplant this offset or flash it.',
              'cases': results}
    output = PRIVATE / 'scanner-idle-policy-emulation.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({k: report[k] for k in ['cases_passed', 'device_access', 'flashed',
                                          'standby_current_measured', 'hardware_wakeup_verified']}))


if __name__ == '__main__':
    main()
