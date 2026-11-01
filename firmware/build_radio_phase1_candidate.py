"""Build separate A86 phase-one candidate; never replace historical A85 files."""
from pathlib import Path
from build_radio_candidate import ROOT, build

OUT = ROOT / 'private/candidates/radio-battery-phase1'

def build_phase1(*, out=OUT):
    return build(boot_path=ROOT/'research/radio_boot_phase1.S', out=out,
                 version=0x86, builddate='20261028', phase_expected=1)

if __name__ == '__main__':
    build_phase1()
