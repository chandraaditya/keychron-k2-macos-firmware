"""Offline A93: A92 plus an acknowledged Apple feature C6 (connection interval).

macOS 27.2 sends SET_CONNECTION_INTERVAL_CONTROL (feature C6) at connect and
retries it for ~9 s when the original setter rejects it, delaying the kernel's
keyboard-configuration GET past its 5 s timeout. A93's root setter returns
success for C6; everything else, including the Fn patch, is A92. No device access.
"""
import json
from build_radio_candidate import ROOT
from build_radio_frow_candidate import build
from build_radio_fn_candidate import patch_fn


def build_c6():
    m = build(ROOT / 'firmware/radio_keyboard_c6_component.S', 0x93,
              ROOT / 'private/candidates/radio-c6-profile',
              ROOT / 'private/candidates/radio-c6-one-boot', transform=patch_fn)
    m['fn_eject_translation'] = True
    m['connection_interval_c6_acknowledged'] = True
    path = ROOT / 'private/candidates/radio-c6-one-boot/manifest.json'
    path.write_text(json.dumps(m, indent=2) + '\n')
    return m


if __name__ == '__main__':
    m = build_c6()
    print(json.dumps({key: m[key] for key in
                      ['status', 'version', 'dynamic_bytes', 'dynamic_sha256',
                       'extension_bytes', 'extension_sha256']}))
