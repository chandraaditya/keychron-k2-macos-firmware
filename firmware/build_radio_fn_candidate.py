"""Offline A92: A91 plus Fn translation in the original scanner-frame handler.

The original app record (loaded at 0x206838) stores scanner frame byte 8 as
report1's last byte via `ldrb.w r0, [sp, #8]` at 0x206c9a. A92 replaces those
four bytes with a BL to the component's fn_shift, which returns the byte << 1
(Apple: bit0 Eject, bits1..7 Fn). Everything else is A91. No device access.
"""
import json
import struct
import sys
from build_radio_candidate import ROOT
from build_radio_frow_candidate import build

APP_BASE = 0x206838
PATCH_AT = 0x206c9a
ORIGINAL = bytes.fromhex('9df80800 84f84501')  # ldrb.w r0,[sp,#8]; strb.w r0,[r4,#0x145]


def thumb_bl(source, target):
    offset = target - (source + 4)
    if offset & 1 or not -(1 << 24) <= offset < (1 << 24):
        raise ValueError('BL target out of range')
    s = (offset >> 24) & 1
    i1 = (offset >> 23) & 1
    i2 = (offset >> 22) & 1
    imm10 = (offset >> 12) & 0x3ff
    imm11 = (offset >> 1) & 0x7ff
    j1 = (~i1 ^ s) & 1
    j2 = (~i2 ^ s) & 1
    return struct.pack('<HH', 0xf000 | (s << 10) | imm10, 0xd000 | (j1 << 13) | (j2 << 11) | imm11)


def patch_fn(items, manifest):
    target = manifest['component_base'] + manifest['component_symbols']['fn_shift']
    matches = [i for i, (t, d) in enumerate(items)
               if t == 0x0a and len(d) > 4 and struct.unpack_from('<I', d)[0] == APP_BASE]
    if len(matches) != 1:
        raise ValueError('Expected exactly one original app record')
    t, d = items[matches[0]]
    o = 4 + PATCH_AT - APP_BASE
    if d[o:o + 8] != ORIGINAL:
        raise ValueError('Original Fn store differs')
    d = bytearray(d)
    d[o:o + 4] = thumb_bl(PATCH_AT, target)
    items = list(items)
    items[matches[0]] = (t, bytes(d))
    manifest['fn_patch'] = {'address': hex(PATCH_AT), 'target': hex(target),
                            'bytes': d[o:o + 4].hex()}
    return items


def build_fn():
    m = build(ROOT / 'firmware/radio_keyboard_fn_component.S', 0x92,
              ROOT / 'private/candidates/radio-fn-profile',
              ROOT / 'private/candidates/radio-fn-one-boot', transform=patch_fn)
    m['fn_eject_translation'] = True
    path = ROOT / 'private/candidates/radio-fn-one-boot/manifest.json'
    path.write_text(json.dumps(m, indent=2) + '\n')
    return m


if __name__ == '__main__':
    m = build_fn()
    print(json.dumps({key: m[key] for key in
                      ['status', 'version', 'dynamic_bytes', 'dynamic_sha256',
                       'extension_bytes', 'extension_sha256']}))
