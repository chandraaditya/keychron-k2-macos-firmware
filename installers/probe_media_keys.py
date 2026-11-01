"""Bounded, owner-operated A88 media-key diagnostic. No firmware writes.

Reads only cached input reports; records function-key codes and volume bits.
Ordinary key codes, modifiers, device addresses and pairing data are discarded.
"""
import ctypes as C
import json
import signal
import time

import radio_keyhole_trial as k
from apple_raw_hid import AppleRawHID


def report(io, rid):
    io._before_request()
    buf = C.create_string_buffer(bytes([rid]) + bytes(31), 32)
    length = C.c_long(32)
    signal.alarm(3)
    try:
        status = io.get_report(io.device, 0, rid, buf, C.byref(length))
    finally:
        signal.alarm(0)
    if status or not 1 <= length.value <= 32 or buf.raw[0] != rid:
        io.failed = True
        raise ValueError(f'Input report {rid} failed; stopping')
    raw = buf.raw[:length.value]
    if rid == 1:
        return {'bytes': len(raw),
                'F_keys': [f'F{code - 0x39}' for code in raw[3:9]
                           if 0x3a <= code <= 0x45],
                'extra_byte': raw[9] if len(raw) > 9 else None}
    return {'bytes': len(raw),
            'volume_bits': (int.from_bytes(raw[1:5], 'little') >> 15) & 7}


def main():
    print('Read-only A88 test. No firmware or Mac settings will change.')
    print('Only function-key codes and volume bits are recorded.')
    results = {}
    for label, action in [('released', 'leave all K2 keys released'),
                          ('F12', 'hold K2 F12 without Fn'),
                          ('Fn_F12', 'hold K2 Fn and F12 together')]:
        input(f'Press Enter, then {action} for 3 seconds: ')
        with AppleRawHID(k.Plan(), write=False) as io:
            if io.read(0x208f02, 14) != bytes.fromhex('b125880ac0023230323631303238'):
                raise ValueError('Expected A88; stopping without changes')
            observations = set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                value = {'keyboard': report(io, 1), 'consumer': report(io, 2)}
                observations.add(json.dumps(value, sort_keys=True))
                time.sleep(0.1)
        results[label] = [json.loads(value) for value in sorted(observations)]
        print('Done. Release the keys.')
    print(json.dumps({'firmware_writes': False, 'observations': results}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(str(error))
