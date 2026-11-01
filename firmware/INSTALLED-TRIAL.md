# Installed K2 trial: 28 October 2026

> Historical snapshot from October 2026. For the current state see [the main README](../README.md).

Current radio: **A86 fallback is active from8000**, following an interrupted A90 staging attempt. Its exact runtime and methods are verified, SS0 remains invalid, SS100 matches the retained A86 header, and the owner confirms normal Bluetooth typing including Shift/Backspace. A90 never committed or activated. The final14-byte attempted write was read back and matches the saved backup; all attempted prefix payloads were identical to the preceding A89 image. No retry has been performed. The current A90 installer requires A89 and will refuse this A86 state. macOS still caches the Apple interface profile from the previous pairing; native-widget/volume behavior remains unresolved. See [interruption evidence](A90-CONTROL-MTU-TRIAL.md). The A86 sections below describe the retained fallback and earlier investigation.

Recovery is physically accepted: the earlier corrected neutral trial invalidated SS0 and ran A86 from4000; after the owner unplugged USB and powered fully OFF for10seconds, A86 ran from8000 with working typing. [Recovery evidence](RECOVERY-WP-TRIAL.md) supersedes the earlier boot-selection state below.

Both firmware components are installed and running. Basic USB and Bluetooth typing are owner-confirmed. The radio patch remains active after a complete power-off and a fresh Mac pairing. Native macOS Bluetooth-menu battery display remains unresolved. Battery-life improvement has not yet been measured.

## Installed components

| Component | Current image and evidence |
|---|---|
| Main scanner/RGB controller | CPU-idle A based on Keychron V2 RGB1.13; SHA256 `0d5da2541dcc54be0909b6ce9fde79da46a20a45c38aafb3b26e35c7c97e4293`. All1,024 blocks programmed and bootloader checksum0x941D verified, with CS1 unchanged. Normal USB bcdDevice0x0113 and typing over both transports confirmed. |
| Bluetooth radio | A86/20261028; DS at0x8000,14,322 bytes; SHA256 `272c7f60a926c65dab10685375aadbb94bc1ddaff88ebfedaa00e84dcd69be3f`. Every staged write read back; complete DS verified before SS0 activation. Runtime extension, constructor hook and all15 battery methods verified after restart and fresh pairing. |

The main patch yields the CPU between interrupts while retaining scanning, timers and communication. It is not a measured promise of20–30-day runtime or faster reconnection. The image replaced main settings with reference defaults. The owner subsequently used Fn+S+O; radio sleep readback is0xAA, disabled. Backlight-off operation is the intended trial condition.

The radio patch makes standard report3 queries refresh from the existing Fn+B estimate, handles increases and decreases, suppresses duplicate notifications, limits ordinary changes to nominal60seconds, and reports on connection. Actual queries tracked86→87% and matched the internal estimate. This remains the original voltage-based estimator, sensitive to charging/load; it is not a calibrated fuel gauge.

## Read the current estimate

The ordinary reader now supports both original A05/20191025 and installed A86/20261028:

```sh
sh read-battery.sh
```

A86 interpretation requires the exact440-byte extension hash, constructor hook, complete shadow method table, original accessor/indicator fingerprints, valid object pointers and stable pointer/percentage checks. It does not require private captures to run. It sends read requests only, registers no keyboard-input callback and installs no background process.

Detailed post-install verification:

```sh
python3 installers/verify_radio.py --phase1
```

## Native macOS display result

The standard report works, but the Mac's generic K2 HID service does not publish a battery value automatically. The owner saw no percentage in the native Bluetooth UI.

A temporary Mac-side test published the freshly validated87% as `BatteryCapacity`. A second independent service client read87%, yet the UI still displayed no percentage. Forgetting/re-pairing and a complete keyboard power cycle also did not produce a native percentage. Both temporary service properties were then confirmed absent; no bridge or background helper remains installed.

This does not prove native UI impossible. It establishes that correct report3 data and simple service-property publication are insufficient in the tested configuration. Further work needs driver eligibility and its required report protocol, rather than another sensor/cache fix. See [native compatibility research](../research/native-battery-next-route.md). A Mac restart has not been tested and is not a demonstrated fix.

## First radio trial and correction

The initial A85 trial programmed successfully but did not activate its battery hook. Its phase0 guard declined because an earlier ROM scatter initializer sets phase1 before loading the DS. The original emulator manually seeded phase0 and missed that earlier step. The guard left original methods active; typing remained functional.

The corrected regression executes actual ROM scatter initialization, the complete DS parser including both callbacks, and heap initialization. It reproduces the A85 failure and validates A86's exact phase1 guard. Eight regression methods pass, retaining phase/arena/original-instruction checks. The unchanged312-byte battery component still occupies the same addresses; the constructor wrapper moves to0x209052 and the runtime call becomes02f0d3fa. See [correction analysis](../research/radio-phase1-boot-correction.md).

Active source/build:

- `research/radio_boot_phase1.S` and `firmware/build_radio_phase1_candidate.py`.
- `firmware/radio_battery_component.S` remains unchanged.
- `installers/radio_phase1_installer.py` and the explicit `--apply-phase1` admin-helper mode performed the repair.

Historical `radio_boot_hook.S`, the default initial builder and A85 artifacts remain preserved. They are not the active A86 build. The trial installers require their exact expected predecessor and should not be rerun on A86.

## Backup and recovery state

Original DS3C0 and original SS100 remain intact; the inactive A85 DS4000 is retained. Current SS0 selects A86 DS8000. Pairing/VS and unknown upper metadata were excluded from planned writes. Private captures include the original full64KiB EEPROM, pre-update captures and the installed-state capture with new pairing information. Raw files contain private identity/pairing data.

Main BOOT access and actual programming under CS1 were demonstrated. A byte-exact original main-image backup was not available. A reference-image restore and independent in-circuit radio restore have not been exercised. Retained SS100 is an original-firmware target, not automatic recovery from a valid header selecting crashing code.

The radio helper used owner-authenticated root access only to claim the keyboard, then permanently dropped groups/GID/UID before backing up or enabling updates. Ghostty required Input Monitoring and a full app restart. No OS security bypass was used.

## Verification and remaining measurements

The repair updater passes8 offline methods and14,363 completed-byte interruption states, alongside15 base-updater and5 privilege-helper tests. The main protocol passes19 simulated transfer cases and8 CLI/file/lock checks. Reader response/address checks and A86 method-table rejection checks pass. These complement actual EEPROM write/readback and runtime verification; they do not simulate electrically torn pages or every radio/scheduler interaction.

Remaining acceptance work: measured idle current or a usage-matched full discharge interval, long idle and wake/host-output coverage, and native macOS battery publication. Faster return reconnection remains separate work. No monthly-runtime claim is made.

Current evidence is recorded in `artifacts/k2-initial-release/manifest.json`, `main-flash-result.json`, `radio-phase1-flash-result.json`, `radio-phase1-live-verification.json` and `native-battery-property-trial.json`.
