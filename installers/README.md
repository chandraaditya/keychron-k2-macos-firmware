# Guarded K2 installers and first hardware trial

> Historical snapshot from October 2026. For the current state see [the main README](../README.md).

28 October trial status: the owner authorized installation. Main CPU-idle A was programmed and checksum-verified under unchanged CS1; basic USB/Bluetooth typing is owner-confirmed. Radio installation is pending a session-compatible privileged exclusive claim; no radio update has been enabled. Default tools remain write-disabled.

## Available operations

From the project directory, file-only plans:

```sh
./build/k2-sonix-installer --plan artifacts/k2-v2-rgb-cpu-idle-a/candidate.bin
python3 installers/radio_installer.py --plan
```

Read-only preflights, only when the corresponding mode is already selected:

```sh
# Main controller: owner has manually entered USB boot mode.
./build/k2-sonix-installer --check artifacts/k2-v2-rgb-cpu-idle-a/candidate.bin
# Radio: keyboard connected over Bluetooth with its original application.
python3 installers/radio_installer.py --check
```

The scanner's flash mode rejects before file/device access in the default compiled build. The radio's apply mode rejects before loading files or opening a device. A separately named authorized main executable was built and used after owner approval. The radio source's write path is exercised only through an in-memory test backend. All live device queries so far have been read-only.

The main installer pins the exact reviewed CPU-idle A image; this is not a general flasher. The radio installer pins the exact new DS, old application, full private baseline, ROM and RAM fingerprints. Editing a candidate and its adjacent manifest together will not bypass its candidate hash. Main query/program operations share a per-user lock with the read-only probe. Both future writing paths require exclusive HID access; inability to obtain it stops before programming.

## Ordered trial after explicit authorization

Install one component at a time to distinguish the effects. Have a working alternate input device. Use a reliable data cable and stable power. Record before/after state and keep raw backups private.

1. **Main trial:** recheck BOOT identity, CS1 and baseline0xBBA4; install CPU-idle A without lowering protection or using a separate erase. Require receipt/footer and post-program checksum0x941D and unchanged CS1 before owner-operated normal restart. This replaces main settings with reference defaults. There is no byte-exact backup of the currently installed main image, and the checked official reference is the available restore source.
2. Verify ordinary typing, modifiers, all keys, Fn/media, Caps Lock output, lighting controls, USB/Bluetooth switching and all used paired hosts. Record the resulting auto-sleep/backlight settings; explicitly select the intended connected operation with lighting off for runtime comparison. Stop on input or communication regressions.
3. Observe idle beyond the original ten-minute timeout, then overnight, including key wake and host-output changes. Compare measured current if possible, otherwise measure a complete usage-matched discharge interval. This candidate has no established 20–30-day runtime improvement. Reconnection delay is a separate future investigation.
4. **Radio trial:** independently approve its remaining recovery risk. The exposed EEPROM is a possible external restore route, but in-circuit recovery is untested and retained SS100 does not auto-recover a crashing selected application. The main USB bootloader cannot restore the radio.
5. Immediately before update, the tool checks the exact live original application/updater context and full EEPROM state, saving a fresh full private backup and journal. After enable70 it must proceed without owner prompts. It stages SS100 and DS4000, verifies every write, and commits SS0 last. The watchdog may reset the radio roughly ten seconds after update activity stops. This activation is part of the approved update, even though the tool sends no LAUNCH.
6. After reconnect, verify candidate identity A85/20261027, regular typing and pairings first. The old layout-specific internal reader is expected to reject the new version. Compare the standard report3 to Fn+B and controlled charge/load changes. Then test macOS Bluetooth/Batteries display and unsolicited notifications. Record UI failure separately from an accurate raw report.

## Failure handling

Neither installer retries, deprotects, guesses another target, erases a fallback bank or automatically resets on failure. A transfer error can mean data was written before acknowledgment was lost. Preserve the device state and journal; do not re-run a mutating command blindly.

The radio's native call timeout deliberately terminates the process instead of hanging forever in a blocking system call. No exception/finally guarantee exists on that path. A durable `before-enable` or `before-write` entry without matching completion means **unknown result**, and an enabled inactivity timer may still reset the radio. The last completed transaction stage and readback determine whether the old or new DS is selected. Completed-byte cut simulations do not cover electrically torn pages or the new application crashing.

The radio read-only preflight does not arm that timer. Hardware updates remain disabled in the distributed source/build pending owner approval and final review.

## Reproduce offline checks

```sh
xcrun clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined installers/test_sonix_core.c installers/sonix_core.c -o build/test-sonix-core
./build/test-sonix-core artifacts/k2-v2-rgb-cpu-idle-a/candidate.bin
python3 installers/test_sonix_cli.py
python3 installers/test_radio_installer.py
```

These tests never select the actual hardware programming branch. The CLI contention test holds the process lock and confirms preflight rejects before device access. Candidate emulation and captured-ROM protocol/transaction checks are documented in [release status](../firmware/INITIAL-RELEASE.md).

## macOS privileged radio claim

The ordinary radio attempt stopped before enable with0xe00002c1: exclusive keyboard seizure requires a privileged HID client. `radio_admin_trial.py` retains the same user-owned lock and exact source-pinned engine. Run it with the isolated system interpreter from the owner's Terminal using sudo. It first proves claim/read-only-target-check/release, then reclaims and permanently drops supplementary groups/GID/UID to the owner before journal creation, fresh full capture or update enable. No security settings or lock ownership are changed. The source hash must match its constant.

The AppleScript administrator-launcher attempt authenticated but stopped before enable with0xe00002e2: TCC attributed the request to authtrampoline in audit user0 and denied ListenEvent. Running from the logged-in owner's Terminal is the next access check; Terminal may itself need Input Monitoring. Do not bypass TCC or remove the exclusive requirement. Do not blindly rerun after a transaction error.
