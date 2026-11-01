"""Offline ARM64 execution of bluetoothd report bridge blocks; no device APIs.

PAC instructions are removed only in the emulator copy, and authenticated indirect
branches become ordinary indirect branches. Transport calls are observed, not run.
"""
import json
import struct
import unittest
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *

ROOT = Path(__file__).resolve().parents[1]
helpers = (ROOT / 'research/inspect_macos_battery.py').read_text().split('targets = {}')[0]
namespace = {}
exec(compile(helpers, 'static_macho_helpers', 'exec'), namespace)
read_address = namespace['read_address']
MD = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
STACK, DATA, TARGET, STOP = 0x20000000, 0x21000000, 0x22000000, 0x22001000
REGS = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
        UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5]


def machine(start, length):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    base = start & ~0xfff
    uc.mem_map(base, ((start + length - base + 4095) // 4096) * 4096)
    code = bytearray(read_address(start, length))
    for ins in MD.disasm(bytes(code), start):
        replacement = None
        if ins.mnemonic in ('pacibsp', 'autibsp', 'autda'):
            replacement = 0xd503201f
        elif ins.mnemonic == 'retab':
            replacement = 0xd65f03c0
        elif ins.mnemonic in ('blraa', 'braa'):
            reg = int(ins.op_str.split(',')[0].strip()[1:])
            replacement = (0xd63f0000 if ins.mnemonic == 'blraa' else 0xd61f0000) | reg << 5
        if replacement is not None:
            struct.pack_into('<I', code, ins.address-start, replacement)
    uc.mem_write(start, bytes(code))
    for addr in (STACK, DATA, TARGET):
        uc.mem_map(addr, 0x10000)
    uc.reg_write(UC_ARM64_REG_SP, STACK+0x8000)
    uc.reg_write(UC_ARM64_REG_X30, STOP)
    return uc


def qput(uc, address, *values):
    uc.mem_write(address, struct.pack('<'+'Q'*len(values), *values))


class KeyholeBridgeTests(unittest.TestCase):
    def test_selector_set_is_feature_ff_two_bytes_for_every_selector(self):
        for selector in range(256):
            uc = machine(0x10059ca28, 0x60)
            block, obj, transport, vtable = DATA, DATA+0x100, DATA+0x200, DATA+0x300
            qput(uc, block+0x20, obj)
            uc.mem_write(block+0x28, struct.pack('<I', selector))
            qput(uc, obj+8, transport)
            qput(uc, transport, vtable)
            qput(uc, vtable+8, TARGET)
            seen = []
            def hook(u, address, size, unused):
                if address == TARGET:
                    args = [u.reg_read(r) for r in REGS]
                    seen.append((args[2], args[3], bytes(u.mem_read(args[4], args[5]))))
                    u.emu_stop()
            uc.hook_add(UC_HOOK_CODE, hook)
            uc.reg_write(UC_ARM64_REG_X0, block)
            uc.emu_start(0x10059ca28, STOP, count=100)
            self.assertEqual(seen, [(3, 0xff, bytes([0xff, selector]))])

    def test_keyhole_get_uses_requested_type_plus_one_and_f0(self):
        for iokit_type in (0, 1, 2):
            uc = machine(0x10059ca88, 0x38)
            block, obj, transport, vtable = DATA, DATA+0x100, DATA+0x200, DATA+0x300
            qput(uc, block+0x20, obj)
            uc.mem_write(block+0x28, bytes([iokit_type, 0, 0, 0, 0xf0]))
            qput(uc, obj+8, transport)
            qput(uc, transport, vtable)
            qput(uc, vtable, TARGET)
            seen = []
            def hook(u, address, size, unused):
                if address == TARGET:
                    seen.append(tuple(u.reg_read(r) for r in REGS[:4]))
                    u.emu_stop()
            uc.hook_add(UC_HOOK_CODE, hook)
            uc.reg_write(UC_ARM64_REG_X0, block)
            uc.emu_start(0x10059ca88, STOP, count=100)
            self.assertEqual(seen, [(transport, obj, iokit_type+1, 0xf0)])

    def test_raw_get_callback_preserves_diagnostic_report_id(self):
        for report in (0x34, 0x70, 0x71, 0x72, 0x90, 0xb2):
            uc = machine(0x1002bebb0, 0x40)
            block, obj, transport, vtable = DATA, DATA+0x100, DATA+0x200, DATA+0x300
            qput(uc, block+0x20, obj, DATA+0x400, DATA+0x500)
            uc.mem_write(block+0x38, struct.pack('<II', 2, report))
            qput(uc, obj+8, transport)
            qput(uc, transport, vtable)
            qput(uc, vtable, TARGET)
            seen = []
            def hook(u, address, size, unused):
                if address == TARGET:
                    seen.append(tuple(u.reg_read(r) for r in REGS[:4]))
                    u.emu_stop()
            uc.hook_add(UC_HOOK_CODE, hook)
            uc.reg_write(UC_ARM64_REG_X0, block)
            uc.emu_start(0x1002bebb0, STOP, count=100)
            self.assertEqual(seen, [(transport, obj, 3, report)])
            self.assertEqual(bytes(uc.mem_read(obj+0x18,16)), struct.pack('<QQ',DATA+0x400,DATA+0x500))

    def test_host_strips_exactly_one_byte_for_input90_and_feature34(self):
        for report in [bytes([0x90,0,87]), bytes([0x34,3,0,0])+bytes(range(6))+bytes(67)]:
            uc = machine(0x10059c974, 0x48)
            obj, buffer, result, result_len = DATA, DATA+0x100, DATA+0x200, DATA+0x300
            packet = b'\xf0' + report
            uc.mem_write(buffer, packet)
            qput(uc, obj+0x18, buffer)
            qput(uc, STACK+0x8000+0x38, len(packet))
            uc.reg_write(UC_ARM64_REG_X19,obj)
            uc.reg_write(UC_ARM64_REG_X22,result_len)
            uc.reg_write(UC_ARM64_REG_X23,result)
            uc.reg_write(UC_ARM64_REG_X26,len(packet))
            uc.mem_map(0x1008c8000,0x1000) # memcpy is explicitly modeled.
            def hook(u,address,size,unused):
                if address==0x1008c87a8:
                    dst,src,n=[u.reg_read(r) for r in REGS[:3]]
                    u.mem_write(dst,bytes(u.mem_read(src,n)))
                    u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
                elif address==0x10059c9bc:
                    u.emu_stop()
            uc.hook_add(UC_HOOK_CODE,hook)
            uc.emu_start(0x10059c974,STOP,count=100)
            self.assertEqual(bytes(uc.mem_read(result,len(report))),report)
            self.assertEqual(struct.unpack('<Q',uc.mem_read(result_len,8))[0],len(report))


if __name__ == '__main__':
    unittest.main()
