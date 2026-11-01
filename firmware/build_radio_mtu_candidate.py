"""Offline A90: retain A89, permit its existing long device-info reply.

Only additional setting is a uint16 send/reassembly ceiling of128 instead48.
The immutable HID local receive template remains48. No device access.
"""
import json
import struct
from build_radio_candidate import ROOT, sha, records, encode
from build_radio_apple_candidate import build_apple
from build_radio_wp_trial import guarded_wp


def build_mtu():
    out = ROOT / 'private/candidates/radio-control-mtu-profile'
    m = build_apple(out=out,
                    component_path=ROOT / 'firmware/radio_keyboard_config_component.S',
                    version=0x90)
    items = records((out / 'dynamic-section.bin').read_bytes())
    if items[-2][0] != 0x0b:
        raise ValueError('Unexpected final startup callback')
    items.insert(-2, (0x0a, struct.pack('<IH', 0x2007d2, 128)))
    profile = encode(items)
    m.update(dynamic_sha256=sha(profile), dynamic_bytes=len(profile),
             control_ceiling=128, immutable_local_receive_template=48)
    (out / 'dynamic-section.bin').write_bytes(profile)
    (out / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n')
    dynamic, guard = guarded_wp(profile)
    if len(dynamic) > 0x4000:
        raise ValueError('One-boot candidate exceeds inactive bank')
    target = ROOT / 'private/candidates/radio-control-mtu-one-boot'
    target.mkdir(exist_ok=True)
    target.chmod(0o700)
    result = {'status': 'offline-control-MTU-trial', 'version': 0x90, **guard,
              'dynamic_sha256': sha(dynamic), 'dynamic_bytes': len(dynamic),
              'extension_sha256': m['extension_sha256'],
              'extension_bytes': m['extension_bytes'], 'component_base': m['component_base'],
              'component_symbols': m['component_symbols'],
              'same_recovery_guard_as_physical_neutral_trial': True,
              'control_ceiling': 128, 'immutable_local_receive_template': 48,
              'native_startup_and_volume_physically_verified': False, 'flashed': False}
    for name, data in [('dynamic-section.bin', dynamic),
                       ('manifest.json', (json.dumps(result, indent=2) + '\n').encode())]:
        path = target / name
        path.write_bytes(data)
        path.chmod(0o600)
    return result


if __name__ == '__main__':
    m = build_mtu()
    print(json.dumps({key: m[key] for key in
                      ['status', 'dynamic_bytes', 'dynamic_sha256', 'extension_bytes']}))
