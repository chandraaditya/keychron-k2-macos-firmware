"""Offline A94: A93 plus a once-per-boot SS0 re-arm on the host's F1 read.

Every boot still starts as a one-boot trial (the WP guard clears SS0 byte 0).
When the host first reads the F1 keyboard configuration, A94 sets byte 0 back
to 1 if the EEPROM holds exactly the installed layout, so the next power-on
boots A94 again. Everything else, including the Fn patch, is A93. No device access.
"""
import json
from build_radio_candidate import ROOT
from build_radio_frow_candidate import build
from build_radio_fn_candidate import patch_fn


def build_rearm():
    m = build(ROOT / 'firmware/radio_keyboard_rearm_component.S', 0x94,
              ROOT / 'private/candidates/radio-rearm-profile',
              ROOT / 'private/candidates/radio-rearm-one-boot', transform=patch_fn)
    m['fn_eject_translation'] = True
    m['connection_interval_c6_acknowledged'] = True
    m['rearm_on_keyboard_configuration_read'] = True
    path = ROOT / 'private/candidates/radio-rearm-one-boot/manifest.json'
    path.write_text(json.dumps(m, indent=2) + '\n')
    return m


if __name__ == '__main__':
    m = build_rearm()
    print(json.dumps({key: m[key] for key in
                      ['status', 'version', 'dynamic_bytes', 'dynamic_sha256',
                       'extension_bytes', 'extension_sha256']}))
