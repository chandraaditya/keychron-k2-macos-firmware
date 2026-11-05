# A94: A93 that survives power-off (re-arm when healthy)

2026-10-31: offline build and tests done. 2026-11-01: installed and accepted (see Hardware results). Design: option D in
`PERMANENT-BOOT-DESIGN.md`.

## What changes

A93 plus one function, `rearm_once`, called once per boot when the host reads the
F1 keyboard configuration. Every boot still starts as a one-boot trial: the WP guard
clears SS0 byte 0 during DS parse, unchanged. If the Mac then reads F1, A94 sets
byte 0 back to 1, so the next power-on boots A94 again. If A94 crashes or never
gets the F1 read, byte 0 stays 0 and the next power-on boots A86 from SS100.

`rearm_once` (`firmware/radio_keyboard_rearm_component.S`):
- runs only if the selected DS is 0x4000;
- reads SS0 and SS100 with ROM 0x2C97A;
- requires SS0 byte 0 = 0, SS100 byte 0 = 1, and SS0 equal to SS100 except the DS
  address (0x4000 vs 0x8000). This is exactly what the installer wrote, so no
  header bytes are embedded in the image;
- writes one byte with ROM 0x2C9B2, which brackets the write-protect pin through
  `[0x200A18]`;
- reads byte 0 back. The writer's return value misses some failures, so only the
  readback counts.

One attempt per boot. The outcome is kept in shadow-table byte 151: 1 = declined,
2 = re-armed, 3 = readback differs. The updater can read it over HID.

Image: 16,364 bytes (20 spare in the 0x4000 bank), SHA
`3dd71d8deaecb23927423c9121a67ff5c5322de105c5f0a969519e53dbfd17c2`, identity
`b125940a…`. A92 and A93 still rebuild byte-identical.

## Tests (offline)

`research/test_radio_rearm.py` drives the full HIDP path. The real ROM EEPROM
reader/writer, ACK poll and WP callback run; only the I2C transfer is modeled, over
the real pre-A92 EEPROM backup.
- The first F1 read changes exactly EEPROM byte 0 (0→1). The WP bracket is
  observed as [0, 1] with the pin low during the write. A second F1 read does no
  I2C at all, and the reply bytes are unchanged.
- Battery, C6, the direct Feature2 report and the wrong selector never touch the
  EEPROM.
- No write when running from 0x8000, when SS0 is already 1, when SS100 is invalid,
  when any header byte differs, or when either DS address is wrong.
- A read failure means no write. A failed or protected write reports 3 and is
  not retried.
- The model hooks the transfer at 0x2C846's entry, so the ROM's 16-byte chunking
  of the 40-byte reads is not emulated. On hardware the app's own 38-byte host-slot
  reads take the same 0x2C97A path at every boot.
- With the A93 component, the 12 re-arm cases fail, so the tests do detect the
  change.

The component/HIDP/boot/C6/Fn suites pass for A94 (75 tests) with
`K2_COMPONENT=firmware/radio_keyboard_rearm_component.S K2_PROFILE=private/candidates/radio-rearm-profile K2_ONEBOOT=private/candidates/radio-rearm-one-boot K2_VERSION=0x94 K2_FN_PROFILE=private/candidates/radio-rearm-profile`
plus A91's `K2_FEATURE2`.

## Installer modes (`installers/radio_rearm_trial.py`, via `radio_admin_trial.py`)

| Flag | Needs running | Writes | Next boot |
|---|---|---|---|
| `--apply-rearm-trial` | A86 from 0x8000 (A93 bank) | 598 bytes / 125 frames + activation | A94 |
| `--rearm-a93` | A93 from 0x4000 | SS0 byte 0 = 1 | A93 (proves in-band writes under A9x) |
| `--rearm` | A94 from 0x4000, byte 0 = 0 | SS0 byte 0 = 1 | A94 |
| `--unarm` | A94 from 0x4000, byte 0 = 1 | SS0 byte 0 = 0 | A86 |

Every mode goes through updater 70→74, so the updater's 10 s inactivity reset
restarts the radio afterwards. `--unarm` therefore reboots straight into A86; the
design doc's "no reset" was wrong. Tests: `installers/test_radio_rearm_trial.py`
(16) and the admin pin test.

## Recovery

- No-write fallback: switch the K2 on while the Mac's Bluetooth is off. The guard
  clears byte 0 and no F1 read re-arms it. Switch off and on again → A86.
- In-band: `--unarm` while A94 is connected.
- Residual risk: A94 re-arms, then later both the keys and Bluetooth stop working.
  Only an external EEPROM programmer helps then.
- Future installers need A86 running. Use `--unarm` first, or the Bluetooth-off
  double power-cycle.

## Hardware plan (each flash confirmed by the owner)

1. `--rearm-a93` on the live A93. Expect a reset, A93 again, and SS0 byte 0 = 0.
2. Power-cycle → A86. Then `--apply-rearm-trial` → A94.
3. Mac reconnects. Probe: identity `b125940a…`, SS0 byte 0 = 1, flag 2.
4. Power-cycle. Probe: still A94; keys work. This is acceptance.

## Hardware results (2026-11-01)

The owner skipped step 1 (`--rearm-a93`), so the in-band `--unarm` path is still untested.
- 13:18:40 UTC: `--apply-rearm-trial` from A86 committed and verified (journal
  `radio-1793538810910416000`).
- After the reset: identity `b125940a…`, DS 0x4000, SS0 byte 0 = 1 with the header
  unchanged, SS100 intact, flag 2. A94 re-armed itself on its first F1 read.
- After a power-cycle: still A94, byte 0 = 1, flag 2. The owner confirmed the keys
  work. Accepted.
- Reconnect after power-on is ~0.8 s from ACL disconnect to ACL connect (bluetoothd
  log). The owner noticed it is much faster than before.

## Flat battery fallback (2026-11-05)

When the battery ran completely flat, the radio browned out and rebooted. One boot cleared
SS0 byte 0 and died before the Mac read F1, so the next power-on booted A86. A94 was still
intact in bank 0x4000. New mode `--reactivate`: A86 running from 0x8000, bank holding A94,
byte 0 = 0. It writes only byte 0 = 1 (journal `radio-1793858974158797000`). After the
reset: A94, byte 0 = 1, flag 2. Read-only state check: `python3 installers/probe_boot_state.py`.

## Making A94 the default (installed 2026-11-05)

A flat battery will trigger the A86 fallback again. Owner's choice: make A94 the
only boot target instead of adding a boot counter.

- **ROM evidence** (`research/test_radio_section_select.py`, 4 tests): runs the
  captured ROM's own scan 0x1CEF8. It tries headers at 0, 0x100, 0x200 … 0x4000; the
  first valid one wins. Validity is type 1 plus a checksum over bytes 3–10 only. The
  DS address comes from that header's own type-2 record (offset 30). Both observed
  hardware boots are reproduced. With SS100 byte 31 = 0x40, an invalid SS0 boots
  0x4000 from SS100.
- **Installer** `installers/radio_make_default.py` (`--make-default`, 7 tests):
  precondition A94 from 0x4000 with SS0 armed and SS100 = the A86 header. It writes
  only 0x11F = 0x40, so SS100 becomes identical to the A94 header. A86 stays at
  0x8000, but nothing selects it.
  - `--repair-default`: for a cut-off write, sets 0x40 whatever byte 31 holds now.
  - `--undo-default`: writes 0x80 back; the next boot is A86, then `--reactivate`.
- **Expected probe afterwards:** A94, DS 0x4000, SS0 byte 0 = 0 after the first
  reboot, SS100 = the A94 header, re-arm flag 1. A94 declines to re-arm a layout it
  did not install, and that is fine.
- **Residual risk:** no automatic fallback. If A94 ever stops booting, recovery needs
  an external EEPROM programmer.

Installed 2026-11-05 07:03 UTC (journal `radio-1793861910959936000`): write and
readback of 0x11F verified. After the reset: A94, SS0 byte 0 = 0, SS100 = the A94
header, flag 1. The owner then power-cycled. With SS0 invalid, that boot could only
come from SS100: the probe showed A94 from 0x4000, and the owner confirmed the keys.
