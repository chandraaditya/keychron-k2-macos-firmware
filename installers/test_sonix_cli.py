"""File-only CLI refusal tests; never chooses the live preflight mode."""
import fcntl
import os
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'build/k2-sonix-installer'
IMAGE=ROOT/'artifacts/k2-v2-rgb-cpu-idle-a/candidate.bin'


def invoke(*args):
    return subprocess.run([str(BIN),*map(str,args)],capture_output=True,text=True)


assert invoke('--plan',IMAGE).returncode==0
refused=invoke('--flash',IMAGE)
assert refused.returncode==2 and 'disabled' in refused.stderr and 'No device opened' in refused.stderr
with tempfile.TemporaryDirectory() as folder:
    base=Path(folder)
    wrong=base/'wrong.bin'
    data=bytearray(IMAGE.read_bytes());data[0xd810]^=1;wrong.write_bytes(data)
    result=invoke('--plan',wrong)
    assert result.returncode==1 and 'SHA256 differs' in result.stderr
    short=base/'short.bin';short.write_bytes(data[:-1])
    result=invoke('--plan',short)
    assert result.returncode==1 and '65536-byte' in result.stderr
    link=base/'link.bin';link.symlink_to(IMAGE)
    assert invoke('--plan',link).returncode==1
assert invoke('--erase',IMAGE).returncode==2
assert invoke('--unlock',IMAGE).returncode==2
# Contention must reject before the native manager opens any hardware.
lock=os.open(f'/tmp/k2-sonix-{os.getuid()}.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
try:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    refused=invoke('--check',IMAGE)
    assert refused.returncode==1 and 'No device opened' in refused.stderr and 'lock' in refused.stderr
finally:os.close(lock)
report={'file_only_cases_passed':8,'candidate_sha256':hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
        'native_binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),
        'hardware_programming_compiled_out':True,'device_access':False,'flashed':False}
p=ROOT/'artifacts/k2-initial-release/sonix-installer-file-tests.json'
p.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
