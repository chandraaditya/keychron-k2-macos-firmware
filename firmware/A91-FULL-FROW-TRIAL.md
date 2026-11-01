# A91 full F-row trial

A90 plus a complete Magic Keyboard F-row in the Feature2 keyboard-configuration reply.
One-boot trial with the same recovery guard; A86 stays the fallback.

## Why

On A90 the Mac publishes `FnFunctionUsageMap` only for F10-F12, so F1-F9 arrive as plain
F-keys. The driver's own enum tables (decoded from the captured kernelcache, emulated in
`research/test_apple_keyboard_configuration.py::test_A91_full_frow_mapping`) give:

| Key | Pair | Action |
|---|---|---|
| F1 / F2 | 01 06 / 02 07 | brightness down / up (FF01/21, FF01/20) |
| F3 | 03 11 | Mission Control (FF01/10) |
| F4 | 04 10 | Launchpad (FF01/04) |
| F7 / F8 / F9 | 07 0A / 08 0C / 09 0B | rewind / play-pause / fast-forward |
| F10-F12 | unchanged | mute / volume down / up |

Logical reply is 25 bytes (`02 01 01 00 00` + 10 pairs); 26 with the F1 keyhole byte.

## Not in A91

Fn is still sent as K2's `01` in report 1's last byte, which Apple's descriptor reads as
Eject (confirmed by `research/fnwatch.swift` capture). Fn+F-key therefore still gives the
media action. Fn translation (`<< 1`) needs the scanner-to-HIDP send path traced first.

## Build and tests

- `firmware/build_radio_frow_candidate.py` (also `--reproduce-a90 <dir>`: reproduces the
  installed A90 byte-for-byte).
- Candidate: 16,128 bytes, SHA-256 `eba838d55855babb02209cacd1a412cdceffbc7142351d74ced0fd2bd6f7e3e6`.
- Component/HIDP/boot tests run against A91 with
  `K2_COMPONENT=firmware/radio_keyboard_frow_component.S K2_FEATURE2=02010100000106020703110410070a080c090b0a0d0b0e0c0f K2_PROFILE=private/candidates/radio-frow-profile K2_ONEBOOT=private/candidates/radio-frow-one-boot K2_VERSION=0x91`
  (57 pass; defaults still test A90, 57 pass).
- Installer `installers/radio_frow_trial.py`: baseline is the committed A90 journal backup
  with the A90 bank and invalidated SS0; writes 103 changed bytes in 49 frames, then one
  activation byte. `installers/test_radio_frow_trial.py` covers every byte cut, lost
  acknowledgements, tampered storage and readback failure.

## Install (not yet run)

1. Fully power-cycle the keyboard so A86 runs from `0x8000` (native battery display
   disappears until A91 boots).
2. `sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-frow-trial`
3. Keyboard resets itself about 10 s after the commit and boots A91.
4. Acceptance: `ioreg -r -c AppleHIDKeyboardEventDriverV2 -l | grep FnFunctionUsageMap`
   shows a K2 map containing `0x0007003a`; if not, disconnect/reconnect from the Bluetooth
   menu once. Then press F1, F3, F8. `verify_radio_mtu_trial.py` is A90-specific
   (892-byte extension) and will reject A91; that is not damage.

A preflight rejection writes nothing, saves a backup and leaves A86 running. Do not retry
an interrupted or rejected run without reviewing its journal.
