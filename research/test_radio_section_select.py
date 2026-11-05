"""The real ROM static-section scan (0x1CEF8) picks the boot DS from EEPROM.

Runs the captured ROM's scan, header validator (0x1CEBA) and record walker
(0x1D042) unmodified. Only the I2C read 0x2C97A is modeled, over the private
EEPROM backup taken just before --reactivate (A94 in bank 0x4000, A86 in
0x8000). It probes candidate headers at 0, 0x100, 0x200 ... 0x4000; the first
valid one wins and its own type-2 record supplies the DS address. With no valid
EEPROM header the ROM moves on to other storage, which is not modeled. No header
bytes are printed.
"""
import struct
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn import arm_const as r

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'private/update-sessions/radio-1793858974158797000.eeprom.bin'
SCAN, RETURN, READ = 0x1cef8, 0x7fff0, 0x2c97a
STATE, SELECTED = 0x205e10, 0x205e1c


def select(eeprom):
    """Run the ROM scan; return (found, selected DS, header address, header reads)."""
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for address, size in [(0, 0x80000), (0x200000, 0x10000)]:
        u.mem_map(address, size)
    u.mem_write(0, (ROOT / 'private/bt-rom-000000-050000.bin').read_bytes())
    u.mem_write(STATE, bytes(0x40))
    u.mem_write(0x20101c, b'\xa0')
    reads = []

    def hook(cpu, address, _size, _data):
        if address != READ:
            return
        at, n, buf = (cpu.reg_read(x) for x in (r.UC_ARM_REG_R0, r.UC_ARM_REG_R1, r.UC_ARM_REG_R2))
        assert cpu.reg_read(r.UC_ARM_REG_R3) == 0xa0 and at + n <= len(eeprom)
        reads.append(at)
        cpu.mem_write(buf, bytes(eeprom[at:at + n]))
        cpu.reg_write(r.UC_ARM_REG_R0, 0)
        cpu.reg_write(r.UC_ARM_REG_PC, cpu.reg_read(r.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)
    u.reg_write(r.UC_ARM_REG_SP, 0x20f000)
    u.reg_write(r.UC_ARM_REG_LR, RETURN | 1)
    u.emu_start(SCAN | 1, RETURN, count=200000)
    found = u.reg_read(r.UC_ARM_REG_R0)
    ds = struct.unpack('<I', u.mem_read(SELECTED, 4))[0]
    header = struct.unpack('<I', u.mem_read(STATE + 8, 4))[0]
    return found, ds, header, reads


class SectionSelectTests(unittest.TestCase):
    def setUp(self):
        self.eeprom = bytearray(BACKUP.read_bytes())
        self.assertEqual(len(self.eeprom), 65536)
        # The backup was taken with A86 running: SS0 invalid, SS100 -> A86.
        self.assertEqual((self.eeprom[0], self.eeprom[31], self.eeprom[0x100], self.eeprom[0x11f]),
                         (0, 0x40, 1, 0x80))

    def check(self, ds, header):
        found, selected, at, _ = select(self.eeprom)
        self.assertEqual((found, selected, at), (1, ds, header))

    def test_matches_hardware_today(self):
        self.check(0x8000, 0x100)            # Observed: invalid SS0 boots A86.
        self.eeprom[0] = 1
        self.check(0x4000, 0)                # Observed: armed SS0 boots A94.

    def test_make_default_boots_A94_from_SS100(self):
        self.eeprom[0x11f] = 0x40
        self.check(0x4000, 0x100)            # Flat-battery case: guard cleared SS0.
        self.eeprom[0] = 1
        self.check(0x4000, 0)

    def test_DS_address_comes_from_the_selected_header_only(self):
        self.eeprom[0x11f] = 0x50
        self.check(0x5000, 0x100)
        self.eeprom[0] = 1
        self.check(0x4000, 0)

    def test_byte_31_is_outside_the_checksum(self):
        for value in (0x00, 0x40, 0x80, 0xff):
            with self.subTest(value=value):
                self.eeprom[0x11f] = value
                found, _, at, _ = select(self.eeprom)
                self.assertEqual((found, at), (1, 0x100))


if __name__ == '__main__':
    unittest.main()
