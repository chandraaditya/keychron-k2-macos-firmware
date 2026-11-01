"""Read-only corrected-WP trial/fallback acceptance, separate result files."""
import json
import sys
import radio_installer as r
import radio_wp_trial as wp
from verify_radio_rollback_preflight import verify

def main():
    if sys.argv[1:]not in (['trial'],['fallback']):raise ValueError('Specify trial or fallback')
    stage=sys.argv[1];plan=wp.Plan()
    def observe(data):
        target=r.ROOT/'artifacts/k2-initial-release'/f'radio-wp-{stage}-observation.json'
        target.write_text(json.dumps(data,indent=2)+'\n')
        print(json.dumps(data,indent=2),flush=True)
    with r.NativeHID(plan)as io:result=verify(io,plan,stage,observer=observe)
    result.update(corrected_WP_trial=True,candidate_DS_sha256=wp.EXPECTED_CANDIDATE_SHA)
    target=r.ROOT/'artifacts/k2-initial-release'/f'radio-wp-{stage}-verification.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError)as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
