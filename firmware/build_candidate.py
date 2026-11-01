"""Offline, exact-input build. No device, updater or flashing functionality."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'private/vendor/k2v2-rgb-1.13-resource-4000.bin'
BASE_SHA = '256b602f7661c924c614a622f29add82e7acde51af93a7c0afbac17ffaf9ad54'
SOURCE = Path(__file__).with_name('cpu_idle_a.S')
OUT = ROOT / 'artifacts/k2-v2-rgb-cpu-idle-a'
HOOK, ORIGINAL, STUB = 0x798, 0x194, 0xd800


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bl(source, target):
    displacement = target - (source + 4)
    if displacement % 2 or not -(1 << 24) <= displacement < (1 << 24):
        raise ValueError('Thumb BL target out of range/alignment')
    n = displacement & 0x1ffffff
    s, i1, i2 = (n >> 24) & 1, (n >> 23) & 1, (n >> 22) & 1
    j1, j2 = 1 ^ i1 ^ s, 1 ^ i2 ^ s
    return struct.pack('<HH', 0xf000 | (s << 10) | ((n >> 12) & 0x3ff),
                       0xd000 | (j1 << 13) | (j2 << 11) | ((n >> 1) & 0x7ff))


def build():
    base = BASE.read_bytes()
    if len(base) != 65536 or sha(base) != BASE_SHA:
        raise ValueError('Reference image does not match exact approved analysis input')
    if base[HOOK:HOOK+4] != bl(HOOK, ORIGINAL):
        raise ValueError('Original call site does not match')
    with tempfile.TemporaryDirectory(prefix='k2-offline-build-') as tmp:
        obj = Path(tmp) / 'idle.o'
        subprocess.run(['xcrun', 'clang', '--target=armv6m-none-eabi', '-mcpu=cortex-m0',
                        '-mthumb', '-c', str(SOURCE), '-o', str(obj)], check=True)
        with obj.open('rb') as handle:
            elf = ELFFile(handle)
            text_section = elf.get_section_by_name('.text')
            if any(s.header['sh_type'] in ('SHT_REL', 'SHT_RELA') and s.num_relocations()
                   for s in elf.iter_sections() if hasattr(s, 'num_relocations')):
                raise ValueError('Unexpected unresolved relocation')
            stub = bytearray(text_section.data())
            symbols = {s.name: s['st_value'] & ~1 for s in
                       elf.get_section_by_name('.symtab').iter_symbols()
                       if s.name in ('cpu_idle_a', 'original_call', 'idle_wfi',
                                     'idle_done', 'code_end')}
    call_offset = symbols['original_call']
    stub[call_offset:call_offset+4] = bl(STUB + call_offset, ORIGINAL)
    if STUB + len(stub) > 0xe000 or any(base[STUB:STUB+len(stub)]):
        raise ValueError('Code insertion region is not the expected zero padding')
    image = bytearray(base)
    image[HOOK:HOOK+4] = bl(HOOK, STUB)
    image[STUB:STUB+len(stub)] = stub
    allowed = set(range(HOOK, HOOK+4)) | set(range(STUB, STUB+len(stub)))
    changed = {i for i, (a, b) in enumerate(zip(base, image)) if a != b}
    if not changed <= allowed:
        raise ValueError('Unexpected changed bytes')
    # Include all discovered persistent settings, not merely the 0x8000 page.
    for start, end in ((0, 0x194), (ORIGINAL, 0x286), (0x7000, 0xa400), (0xfffc, 0x10000)):
        if image[start:end] != base[start:end]:
            raise ValueError('Protected region changed')
    recovered = bytearray(image)
    recovered[HOOK:HOOK+4] = base[HOOK:HOOK+4]
    recovered[STUB:STUB+len(stub)] = base[STUB:STUB+len(stub)]
    if recovered != base:
        raise ValueError('Inverse patch is not byte-exact')
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    listing = '\n'.join(f'{i.address:08x}  {i.bytes.hex():10} {i.mnemonic:8} {i.op_str}'
                        for i in disassembler.disasm(stub[:symbols['code_end']], STUB)) + '\n'
    manifest = {
        'candidate': 'k2-v2-rgb-cpu-idle-a', 'status': 'offline-experimental-not-cleared-for-flashing',
        'base_sha256': BASE_SHA, 'image_sha256': sha(image), 'source_sha256': sha(SOURCE.read_bytes()),
        'image_size': len(image), 'hook': HOOK, 'original_handler': ORIGINAL,
        'stub_start': STUB, 'stub_size': len(stub), 'changed_byte_count': len(changed),
        'symbols': {k: STUB + v for k, v in symbols.items()},
        'hook_before': base[HOOK:HOOK+4].hex(), 'hook_after': image[HOOK:HOOK+4].hex(),
        'allowed_change_ranges_end_exclusive': [[HOOK, HOOK+4], [STUB, STUB+len(stub)]],
        'persistent_region_preserved': ['0x7000', '0xa400'],
        'binary_inverse_patch_verified': True,
        'compiler': subprocess.check_output(['xcrun', 'clang', '--version'], text=True).splitlines()[0],
        'device_access': False, 'flashed': False, 'installed_image_match_verified': False,
        'hardware_wake_verified': False, 'power_savings_measured': False,
        'compatibility_evidence': 'Owner reports two rear height settings, supporting K2 V2; installed Sonix image not captured.',
        'limitations': ['Published V2 RGB 1.13 reference; not a dump of this keyboard.',
                        'No radio firmware or macOS battery reporting change.',
                        'No verified board recovery route or hardware current measurement.',
                        'Emulation does not model real sleep, timing, electrical interrupts or flash boot checks.'],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in [('candidate.bin', bytes(image)), ('cpu_idle_a.S', SOURCE.read_bytes()),
                       ('disassembly.txt', listing.encode()),
                       ('manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())]:
        (OUT / name).write_bytes(data)
    print(json.dumps({k: manifest[k] for k in ('candidate', 'image_sha256', 'stub_size',
                                              'changed_byte_count', 'status')}))
    return manifest


if __name__ == '__main__':
    build()
