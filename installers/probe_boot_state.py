"""Read-only: which radio build runs, which section booted, and the A94 boot byte.

Prints no header bytes or keys, only comparisons. Needs the K2 connected over
Bluetooth; no sudo, no writes.
"""
import struct
import radio_installer as r
import radio_fn_trial as fn
import radio_mtu_recovery as prev
import radio_rearm_trial as rearm

NAMES = {bytes.fromhex('b125860ac0023230323631303238'): 'A86 (original app)'}
NAMES.update({v: f'A{k:x}' for k, v in rearm.IDENTITY.items()})

plan = fn.Plan()
a94 = (r.ROOT / 'private/candidates/radio-rearm-one-boot/dynamic-section.bin').read_bytes()
with prev.RecoveryHID(plan) as io:
    identity = io.read(0x208f02, 14)
    print('identity', identity.hex(), NAMES.get(identity, 'unknown'))
    print('selected DS', hex(struct.unpack('<I', io.read(0x205e1c, 4))[0]))
    ss0 = io.read(0xff000000, 40)
    print('SS0 byte0', ss0[0], 'rest==A9x header', ss0[1:] == plan.new_ss[1:])
    ss100 = io.read(0xff000100, 40)
    print('SS100 intact A86 header', ss100 == plan.backup_ss,
          '| SS100 is the A94 header (A94 is default)', ss100 == plan.new_ss)
    print('bank 4000 holds A94', io.read(0xff004000, len(a94)) == a94)
    obj = struct.unpack('<I', io.read(0x208ea8, 4))[0]
    table = struct.unpack('<I', io.read(obj, 4))[0]
    if 0x209000 <= table < 0x20ef00:
        print('rearm flag (1 declined, 2 rearmed, 3 readback differs)', io.read(table + 151, 1)[0])
