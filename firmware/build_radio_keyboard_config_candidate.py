"""A89: only add Apple's keyboard Feature2 configuration to A88.

No device access. Retains exact A88 SDP, estimator, MTU and WP recovery guard.
"""
import json
from build_radio_candidate import ROOT, sha
from build_radio_apple_candidate import build_apple
from build_radio_wp_trial import guarded_wp


def build_keyboard_config():
    out = ROOT / 'private/candidates/radio-keyboard-config-profile'
    manifest = build_apple(out=out,
                           component_path=ROOT / 'firmware/radio_keyboard_config_component.S',
                           version=0x89)
    dynamic, guard = guarded_wp((out / 'dynamic-section.bin').read_bytes())
    if len(dynamic) > 0x4000:
        raise ValueError('One-boot candidate exceeds inactive bank')
    target = ROOT / 'private/candidates/radio-keyboard-config-one-boot'
    target.mkdir(exist_ok=True)
    target.chmod(0o700)
    result = {'status': 'offline-keyboard-configuration-trial', 'version': 0x89,
              **guard, 'dynamic_sha256': sha(dynamic), 'dynamic_bytes': len(dynamic),
              'extension_sha256': manifest['extension_sha256'],
              'extension_bytes': manifest['extension_bytes'],
              'component_base': manifest['component_base'],
              'component_symbols': manifest['component_symbols'],
              'same_recovery_guard_as_physical_neutral_trial': True,
              'Feature_FF_selector_02': True, 'Feature_F1_02': True,
              'volume_function_map': ['F10:mute', 'F11:volume-down', 'F12:volume-up'],
              'native_media_keys_physically_verified': False, 'flashed': False}
    for name, data in [('dynamic-section.bin', dynamic),
                       ('manifest.json', (json.dumps(result, indent=2) + '\n').encode())]:
        path = target / name
        path.write_bytes(data)
        path.chmod(0o600)
    return result


if __name__ == '__main__':
    m = build_keyboard_config()
    print(json.dumps({key: m[key] for key in
                      ['status', 'dynamic_bytes', 'dynamic_sha256', 'extension_bytes']}))
