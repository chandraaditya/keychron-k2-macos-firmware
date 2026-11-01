# A92 Fn translation trial

A91 (full F-row) plus Fn translation. One-boot trial with the same recovery guard; A86 stays the fallback.

## Why

The K2 scanner sends key frames `A1 mod - k1 k2 k3 k4 k5 fn` over SPI0. The original radio
handler (`0x206c2c`) copies frame byte 8 unchanged into report 1's last byte (`[obj+0x145]`).
K2 uses `01` for Fn; Apple's 182-byte descriptor reads bit0 as Eject and bits1..7 as Fn
(confirmed by `research/fnwatch.swift`: Fn arrived as Consumer/B8).

## Change

`0x206c9a: ldrb.w r0,[sp,#8]` (`9df80800`) inside the original app record (loaded at
`0x206838`) becomes `bl fn_shift`. `fn_shift` (in `radio_keyboard_fn_component.S`) does the same
load, `lsls r0,r0,#1`, `bx lr`. SP is untouched by BL; the handler restores LR from its own
stack frame, and nothing else reads `+0x145`.

## Build and tests

- `firmware/build_radio_fn_candidate.py`; A90 and A91 still rebuild byte-for-byte.
- Candidate: 16,136 bytes, SHA-256 `b2d13ebfc4358f38e71a3f9b88f9fc0c403aebe89d59454d4eea114803fe0f73`.
- `research/test_radio_fn_translation.py` boots the real A92 section and runs the original
  handler: Fn 0→0, Fn 1→2, modifiers/keys unchanged; A91 still passes 1 through.
- Component/HIDP/boot suites (57) pass for A92 with
  `K2_COMPONENT=firmware/radio_keyboard_fn_component.S K2_PROFILE=private/candidates/radio-fn-profile K2_ONEBOOT=private/candidates/radio-fn-one-boot K2_VERSION=0x92` plus A91's `K2_FEATURE2`.
- Installer `installers/radio_fn_trial.py` (baseline: committed A91 journal
  `radio-1793183520453584000` with A91 bank): 124 changed bytes in 51 AA-safe frames, then
  one activation byte. `installers/test_radio_fn_trial.py`.

## Install (not yet run)

1. Fully power-cycle the keyboard (A86 runs; battery display and F-row map disappear).
2. `sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-fn-trial`
3. Keyboard resets into A92. If the K2's `FnFunctionUsageMap` is absent, disconnect/reconnect once.
4. Acceptance: RAM `0x206c9a` reads `fn_patch.bytes` + `84f84501`; F12 = volume up,
   Fn+F12 = plain F12 (Terminal shows `ESC[24~`); holding Fn alone ejects/sleeps nothing.

If the A92 preflight rejects, `--apply-frow-trial` returns to A91: with the bank already
at A91 it plans zero data writes and only rewrites the activation byte (checked offline).

Pressing Fn alone now behaves like a Mac Fn/Globe key (System Settings › Keyboard ›
"Press 🌐 key to").
