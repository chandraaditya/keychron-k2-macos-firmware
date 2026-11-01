"""Offline A91: A90 plus a full Magic Keyboard F-row in the Feature2 reply.

Only the component's keyboard_configuration bytes and two reply lengths differ
from A90. Control ceiling, SDP, battery keyhole and WP recovery guard are A90's.
No device access.
"""
import json
import struct
import sys
from pathlib import Path
from build_radio_candidate import ROOT, sha, records, encode
from build_radio_apple_candidate import build_apple
from build_radio_wp_trial import guarded_wp


def build(component_path, version, profile_dir, target_dir, transform=None):
    m = build_apple(out=profile_dir, component_path=component_path, version=version)
    items = records((profile_dir / 'dynamic-section.bin').read_bytes())
    if transform:
        items = transform(items, m)
    if items[-2][0] != 0x0b:
        raise ValueError('Unexpected final startup callback')
    items.insert(-2, (0x0a, struct.pack('<IH', 0x2007d2, 128)))
    profile = encode(items)
    m.update(dynamic_sha256=sha(profile), dynamic_bytes=len(profile),
             control_ceiling=128, immutable_local_receive_template=48)
    (profile_dir / 'dynamic-section.bin').write_bytes(profile)
    (profile_dir / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n')
    dynamic, guard = guarded_wp(profile)
    if len(dynamic) > 0x4000:
        raise ValueError('One-boot candidate exceeds inactive bank')
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o700)
    result = {'status': 'offline-full-frow-trial', 'version': version, **guard,
              'dynamic_sha256': sha(dynamic), 'dynamic_bytes': len(dynamic),
              'extension_sha256': m['extension_sha256'],
              'extension_bytes': m['extension_bytes'], 'component_base': m['component_base'],
              'component_symbols': m['component_symbols'],
              'control_ceiling': 128, 'immutable_local_receive_template': 48,
              'function_map': ['F1:brightness-down', 'F2:brightness-up', 'F3:mission-control',
                               'F4:launchpad', 'F7:rewind', 'F8:play-pause', 'F9:fast-forward',
                               'F10:mute', 'F11:volume-down', 'F12:volume-up'],
              'fn_eject_translation': False, 'flashed': False}
    for name, data in [('dynamic-section.bin', dynamic),
                       ('manifest.json', (json.dumps(result, indent=2) + '\n').encode())]:
        path = target_dir / name
        path.write_bytes(data)
        path.chmod(0o600)
    return result


def build_frow():
    return build(ROOT / 'firmware/radio_keyboard_frow_component.S', 0x91,
                 ROOT / 'private/candidates/radio-frow-profile',
                 ROOT / 'private/candidates/radio-frow-one-boot')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--reproduce-a90']:
        scratch = Path(sys.argv[2])
        m = build(ROOT / 'firmware/radio_keyboard_config_component.S', 0x90,
                  scratch / 'profile', scratch / 'one-boot')
    else:
        m = build_frow()
    print(json.dumps({key: m[key] for key in
                      ['status', 'version', 'dynamic_bytes', 'dynamic_sha256',
                       'extension_bytes', 'extension_sha256']}))
