# Making the trial survive power-off (design only; nothing built or flashed)

2026-10-28. Deferred by the owner until battery work is done. "A93" below meant
"the next version"; A93 is now the C6 connection-interval fix (`A93-C6-TRIAL.md`),
so a permanence build would be a later number on top of it.

2026-10-31: built as A94 (option D, trigger 1). See `A94-REARM-TRIAL.md`. Correction:
`--unarm` goes through the updater, whose inactivity reset reboots the radio, so it
switches to A86 at once rather than "no reset".

## Where we are

A92 runs from bank 0x4000 as a one-boot trial. The guard record (first in the DS prefix,
`research/radio_one_boot_guard_wp.S`) writes SS0 byte 0 = 0 during DS parse. The next boot
then fails over to SS100 → A86 at 0x8000. Byte 0 as the only validity toggle is proven in
both directions (installer activation sets it to 1, the guard clears it).

The ROM picks the first valid static section and never checks that the application started
(`research/physical-eeprom-and-recovery-review.md`). So a plain valid SS0 has no automatic
rollback.

Read-only checks on the live A92 (2026-10-28):
- identity `b125920a…`, selected DS 0x4000, SS0 byte 0 = 0 with the rest equal to the A92
  header, SS100 identical to the A86 backup;
- the factory updater is intact: singleton 0x2067BC → object with table 0x206794, IDs
  70–75, base 0, interval 10, storage mode 1, write boundary 16. So writes over Bluetooth
  should work from A9x too (reads are proven; writes not yet tried under A9x).

## Options

| | What | Automatic fallback | Verdict |
|---|---|---|---|
| A | A92 without the guard, SS0 stays 1 | none: if any boot fails, the only recovery is an external EEPROM programmer (never tested) | reject |
| B | Point SS100 at A92 | removes A86 | reject |
| C | Mac daemon re-runs the activation byte whenever A86 shows up | always | slow (each power-on boots A86, resets, reconnects); root daemon writing EEPROM | backup idea |
| **D** | **Keep the guard; A93 writes SS0 byte 0 back to 1 once it is healthy** | **yes, until A93 proves itself on each boot** | **recommended** |

## Recommended: D, the "re-arm when healthy" switch

Every boot starts as a trial (the guard is unchanged and stays first). Once that boot proves
healthy, A93 writes byte 0 back to 1, so the next power-on boots A93 again. If A93 crashes or
hangs before it proves healthy, SS0 stays invalid and the next power-cycle boots A86, exactly
as it does today.

Change from A92: one small component function plus one RAM flag. The guard, A86, SS100,
VS and pairing data are untouched.

### When does it count as healthy? (your call)

1. **When the Mac reads the keyboard config** (keyhole GET F1, already served by our
   component). This proves boot, Bluetooth link, host and our code. Strongest.
   Gotcha: turn the K2 on while the Mac is off or out of range, then off again → it comes
   back as A86 until re-armed. Re-arm = a 1-byte installer run (`--rearm`), like today's
   `--apply-frow-trial` shortcut.
2. **N seconds after boot** (timer). Covers boot and early crashes, not a broken Bluetooth
   path. The gotcha above disappears.
3. **End of DS load.** Covers parse failures only. Barely better than option A.

Recommendation: option 1. The intermittent first-connect case (missing `FnFunctionUsageMap`)
is fine: re-arm needs only one F1 fetch in the whole session, and a reconnect does one.

Sleep note: you run with auto-sleep disabled. If auto-sleep is enabled later and CYW20730
deep sleep wakes through a reset (likely, not yet traced), each wake is a new trial. With
option 1, re-arm happens again on reconnect, so this is fine while the Mac is reachable.

### Write primitive

Use ROM `0x2C9B2`, the synchronous EEPROM writer. The factory updater's 0x74 write uses it
from the same HID report-handler context our F1 reply runs in. It brackets write-protect
through `[0x200A18]` automatically.

Rules:
- write once per boot (RAM flag);
- only if SS0 bytes 1..39 still equal the A93 header (never validate a header we didn't
  install);
- read back byte 0 afterwards;
- on any failure, do nothing more.

Its ACK poll has no bound. A stuck bus means hang → watchdog → reboot. The guard's own
bounded write then fails → redirect to A86. It fails safe.

## Recovery paths after permanence

1. **A93 boots and connects:** in-band "unarm" writes SS0 byte 0 = 0 over Bluetooth, then
   power-cycle → A86. The updater is present under A92. Writes under A9x are unproven, so
   the first hardware step tests this deliberately (see below).
2. **A93 dies before healthy:** power-cycle → A86 automatically.
3. **A93 healthy at the F1 fetch but broken later** (e.g. keys stop after an hour): the
   re-arm already happened, so path 1 is needed. If Bluetooth also dies, only the external
   programmer remains. This is the one residual risk. A92 has run for hours with none of
   this, and A93 adds no code to the key path.
4. Future installers can no longer assume "A86 running from 0x8000". They must unarm first,
   or chain from A93 directly.

## Build and tests (after approval)

- `firmware/radio_keyboard_rearm_component.S`: A92 component plus `rearm_once` called from
  the F1 reply path. `build_radio_rearm_candidate.py` builds version 0x93; A90–A92 must
  still rebuild byte-identical.
- Unicorn, real A93 section, modeled EEPROM:
  - byte 0 is 0 after DS parse;
  - becomes 1 after the first F1 GET, never on a second;
  - no write if the header differs, or if the I2C call fails (byte stays 0);
  - WP bracket observed;
  - exactly one byte touched;
  - F1 reply bytes unchanged.
- The 57-test component/HIDP/boot suites, run for A93.
- Installer `radio_rearm_trial.py`: chained from the A92 journal `radio-1793184566954073000`
  with the same AA-safe sparse frames and `ChunkedDevice` tests. Plus `--rearm` (activation
  byte only) and `--unarm` (byte 0 = 0, no reset) modes.

## Hardware acceptance

1. Power-cycle → A86. Install A93 (last install that needs A86 running).
2. Reconnect. Read SS0 byte 0 (no sudo): expect 1 after the Mac's F1 fetch.
3. **Unarm test while still safe:** run `--unarm`, read byte 0 = 0, then `--rearm`. This
   proves in-band recovery works under A9x before we depend on it.
4. Power off, power on: identity `b125930a…`; battery, F-row and Fn work.
5. Optional: Mac Bluetooth off, power-cycle twice → A86 → `--rearm`. Proves the fallback.

Rollback at any point: power-cycle into A86 when byte 0 = 0, or unarm first.
