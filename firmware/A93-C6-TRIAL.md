# A93 connection-interval (C6) trial

A92 plus one change: the radio acknowledges Apple's `SET_CONNECTION_INTERVAL_CONTROL`
feature report (C6) instead of rejecting it. One-boot trial with the same guard;
A86 stays the fallback.

## Why

After the macOS 27.2 update, the K2's F-row map (`FnFunctionUsageMap`) was missing on
every connect. Mac logs for two connects (2026-10-31 18:52:45 and 19:42:25):

1. At connect, bluetoothd queues feature `C6 01 18 01 20` (24 slots, 1 attempt,
   multiplier 32) to move the K2 to 15 ms sniff.
2. A92's root setter returns handshake 2 (ERR_INVALID_REPORT_ID). bluetoothd retries
   about every 518 ms, 18 times (about 9 s).
3. The kernel's keyboard-configuration GET (keyhole F1, report 2) is in the same
   per-device HID queue. It went out 9.3–9.4 s after connect. `AppleHIDKeyboard`
   gave up at 5 s ("Failed to get Keyboard format with error 0xE00002D6"), so no
   F-row map was published.

The C6 loop was seen before and set aside, because it also appeared on connects that
worked. Those connects most likely got the GET queued ahead of it.

## Change

`root_set_report` in `radio_keyboard_c6_component.S`: feature (type 3) report C6
returns 0 (success). Every other report keeps its existing path. The keyboard does not
change its own sniff interval in response. The Mac already sets sniff itself, so
sniff stays where it is today (11.25 ms requested by the K2, or 15 ms from the host).

## Build and tests

- `firmware/build_radio_c6_candidate.py`. A92 still rebuilds byte-for-byte (SHA
  `b2d13ebf…`).
- Candidate: 16,144 bytes, SHA-256
  `37db6e7de86a1a1bbce87b1d95c0efaea4be3f336897df7be2b8ec3d16446264`. Fn patch at
  0x206c9a is `02f054fb` → `fn_shift` at 0x209346.
- `research/test_radio_connection_interval.py` drives the full HIDP path through the
  ROM:
  - C6 now gets handshake 0, and the following F1 config GET is still sent intact;
  - other feature SETs still reach the original setter;
  - with A92's component the same test gets handshake 2, matching the Mac logs.
- Component/HIDP/boot suites pass for A93 with
  `K2_COMPONENT=firmware/radio_keyboard_c6_component.S K2_PROFILE=private/candidates/radio-c6-profile K2_ONEBOOT=private/candidates/radio-c6-one-boot K2_VERSION=0x93`
  plus A91's `K2_FEATURE2`. `research/test_radio_fn_translation.py` passes with
  `K2_FN_PROFILE=private/candidates/radio-c6-profile`.
- `research/test_apple_keyboard_configuration.py` now errors for every firmware.
  It emulates the live macOS kernel, whose addresses changed in 27.2. This is
  unrelated to A93.
- Installer `installers/radio_c6_trial.py`: baseline is the committed A92 journal
  `radio-1793184566954073000` with the A92 bank. 593 changed bytes in 114 AA-safe
  frames, then one activation byte. Tests: `installers/test_radio_c6_trial.py`.

## Install (run 2026-10-31, journal radio-1793457212404055000)

Result: identity `b125930a…` from bank 0x4000. Both C6 SETs succeeded, with no retry run. The F1 config GET went out 0.55 s after connect (it was 9.4 s on A92), no kernel timeout, and the K2 published `FnFunctionUsageMap` on the first connect. The Mac-restart check is still pending.

1. Fully power-cycle the keyboard (A86 runs).
2. `sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-c6-trial`
3. Keyboard resets into A93.
4. Acceptance:
   - identity `b125930a…`;
   - Mac log shows one C6 SET succeeding and no 518 ms retry run;
   - the F1 config GET goes out within about 1 s of connect;
   - the K2 has `FnFunctionUsageMap` on the first connect, and again after a Mac
     restart;
   - F-row media keys and Fn+F-keys work.

If the preflight rejects, `--apply-fn-trial` returns to A92 (bank already at A92 →
activation byte only).
