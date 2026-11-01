"""A88 Apple keyhole protocol, retaining the physically verified WP guard."""
import json
from build_radio_candidate import ROOT,sha
from build_radio_apple_candidate import build_apple
from build_radio_wp_trial import guarded_wp

def build_keyhole():
    out=ROOT/'private/candidates/radio-apple-keyhole-profile'
    m=build_apple(out=out,component_path=ROOT/'firmware/radio_apple_keyhole_component.S',version=0x88)
    dynamic,guard=guarded_wp((out/'dynamic-section.bin').read_bytes())
    target=ROOT/'private/candidates/radio-apple-keyhole-one-boot'
    target.mkdir(exist_ok=True);target.chmod(0o700)
    result={'status':'offline-keyhole-protocol-trial-pending','version':0x88,**guard,
            'dynamic_sha256':sha(dynamic),'dynamic_bytes':len(dynamic),
            'extension_sha256':m['extension_sha256'],'extension_bytes':m['extension_bytes'],
            'component_base':m['component_base'],'component_symbols':m['component_symbols'],
            'same_recovery_guard_as_physical_neutral_trial':True,
            'Feature_FF_selector':True,'Input_F0_90':True,'Feature_F0_34':True,
            'native_battery_percent_verified':False,'flashed':False}
    for name,data in [('dynamic-section.bin',dynamic),('manifest.json',(json.dumps(result,indent=2)+'\n').encode())]:
        p=target/name;p.write_bytes(data);p.chmod(0o600)
    return result

if __name__=='__main__':
    m=build_keyhole();print(json.dumps({k:m[k]for k in ['status','dynamic_bytes','dynamic_sha256','extension_bytes']}))
