"""Static inspection of the local Bluetooth daemon; no process interaction."""
import bisect
import json
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

raw = Path('/usr/sbin/bluetoothd').read_bytes()
magic, count = struct.unpack_from('>II', raw)
assert magic == 0xCAFEBABE
arches = [struct.unpack_from('>IIIII', raw, 8 + 20 * i) for i in range(count)]
arch = next(a for a in arches if a[0] == 0x100000C)
image = raw[arch[2]:arch[2] + arch[3]]
assert struct.unpack_from('<I', image)[0] == 0xFEEDFACF
ncmds = struct.unpack_from('<I', image, 16)[0]
sections, functions, segments = [], [], []
pos = 32
for _ in range(ncmds):
    cmd, size = struct.unpack_from('<II', image, pos)
    if cmd == 0x19:
        segname = image[pos + 8:pos + 24].rstrip(b'\0').decode()
        vm, vmsize, off, filesize = struct.unpack_from('<QQQQ', image, pos + 24)
        segments.append((segname, vm, off, filesize))
        nsects = struct.unpack_from('<I', image, pos + 64)[0]
        for i in range(nsects):
            p = pos + 72 + i * 80
            name = image[p:p + 16].rstrip(b'\0').decode()
            addr, length, offset = struct.unpack_from('<QQI', image, p + 32)
            sections.append((name, addr, length, offset))
    elif cmd == 0x26:
        dataoff, datasize = struct.unpack_from('<II', image, pos + 8)
        encoded_functions = image[dataoff:dataoff + datasize]
    pos += size
textbase = next(vm for name, vm, _, _ in segments if name == '__TEXT')
last, val, shift = textbase, 0, 0
for byte in encoded_functions:
    val |= (byte & 127) << shift
    if byte & 128:
        shift += 7
    else:
        if not val: break
        last += val
        functions.append(last)
        val, shift = 0, 0


def address_for_offset(off):
    for _, addr, size, offset in sections:
        if offset <= off < offset + size:
            return addr + off - offset
    raise ValueError(off)


def read_address(addr, size):
    for _, vm, offset, length in segments:
        if vm <= addr and addr + size <= vm + length:
            return image[offset + addr - vm:offset + addr - vm + size]
    return b''


targets = {}
for needle in [b'HID Battery fetch battery level', b'HID Battery percentage',
               b'HID battery fetch failed', b'HID Battery Failed to fetch']:
    offset = image.find(needle)
    if offset >= 0:
        targets[address_for_offset(offset)] = needle.decode()

text = next(s for s in sections if s[0] == '__text')
_, addr, length, off = text
code = image[off:off + length]
hits = []
for index, (word,) in enumerate(struct.iter_unpack('<I', code)):
    if word & 0x9F000000 != 0x90000000: continue
    reg = word & 31
    imm = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 3)
    if imm & (1 << 20): imm -= 1 << 21
    pc = addr + index * 4
    page = (pc & ~4095) + (imm << 12)
    if not any(page == (t & ~4095) for t in targets): continue
    for delta in range(1, 7):
        p = (index + delta) * 4
        if p + 4 > len(code): break
        nxt = struct.unpack_from('<I', code, p)[0]
        if nxt & 0xFF000000 == 0x91000000 and (nxt >> 5) & 31 == reg:
            target = page + (((nxt >> 10) & 4095) << (12 if nxt & (1 << 22) else 0))
            if target in targets:
                function_index = bisect.bisect_right(functions, pc) - 1
                start = functions[function_index]
                end = functions[function_index + 1] if function_index + 1 < len(functions) else pc + 128
                hits.append({'string': targets[target], 'reference': hex(pc),
                             'function_start': hex(start), 'function_end': hex(end)})

root = Path(__file__).resolve().parents[1] / 'private/apple'
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
out = []
for start, end in sorted({(int(x['function_start'], 16), int(x['function_end'], 16)) for x in hits}):
    out.append(f'FUNCTION {start:#x}..{end:#x}')
    for i in md.disasm(read_address(start, end - start), start):
        out.append(f'{i.address:016x} {i.mnemonic:10} {i.op_str}')
(root / 'bluetooth-battery-functions.txt').write_text('\n'.join(out) + '\n')
def cfstring(addr):
    value = read_address(addr, 32)
    pointer, length = struct.unpack_from('<QQ', value, 16)
    # This slice uses chained rebases whose low 32 bits are image-relative.
    pointer = textbase + (pointer & 0xFFFFFFFF)
    return read_address(pointer, length).decode()


assessment = {
    'arm_slice_subtype': arch[1],
    'string_xrefs': hits,
    'registry_driver_classes': [cfstring(a) for a in [0x100B76B18, 0x100B76B38, 0x100B76B58]],
    'registry_address_property': cfstring(0x100B76B78),
    'registry_battery_property': cfstring(0x100B76B98),
    'hid_service_fallback': {
        'function': '0x100524ab0',
        'enumeration_api': 'IOHIDEventSystemClientCopyServices',
        'property_api': 'IOHIDServiceClientCopyProperty',
        'identity_property': cfstring(0x100B5F6F8),
        'normalize_from': cfstring(0x100B5B8D8),
        'normalize_to': cfstring(0x100B5B8B8),
        'battery_property': cfstring(0x100B76BB8),
    },
    'scope': 'Observed static path in the installed macOS binary; not proof that every battery path was analyzed',
}
(root / 'bluetooth-battery-xrefs.json').write_text(json.dumps(assessment, indent=2) + '\n')
if __name__ == '__main__':
    print(json.dumps(assessment, indent=2))
