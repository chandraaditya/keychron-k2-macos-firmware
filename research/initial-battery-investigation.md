# Keychron K2 battery investigation

Current trial: [installed firmware and verified results](../firmware/INSTALLED-TRIAL.md). Main CPU-idle A and radio A86 are installed and runtime-verified; USB/Bluetooth typing works. The standard battery report matches the internal estimate. Native macOS menu display remains unresolved, and power/runtime improvement is unmeasured. [Historical preparation](../firmware/INITIAL-RELEASE.md).

In progress: [Apple battery-profile prototype and one-boot recovery trial](../firmware/APPLE-BATTERY-TRIAL.md). The new profile is offline; physical rollback verification is pending.

**Result: the installed firmware's battery estimate is readable without flashing. Fresh reads returned 58%, matching the blue Fn+B indicator.**

Observed on the connected keyboard on 27 October 2026:

- Bluetooth name: `Keychron K2`; vendor/product IDs: `05ac:024f`.
- macOS reports `1.1.11`. This is the HID device version, not a verified keyboard-controller firmware version.
- The diagnostic version query returned prefix `b1 25 05 0a c0 02` and build date `20191025`.
- These observations are consistent with the original K2 family. They do not establish the exact PCB revision or a compatible firmware image.
- Bluetooth input report 3 declares battery strength from 0 to 100 and successfully returns `03 00`.
- The owner observed blue with Fn+B, while unplugged. Keychron documents blue as 30-70% for the RGB K2. Therefore the raw Bluetooth 0% is not a trustworthy battery estimate on this unit.
- No firmware, saved settings, or pairing was changed. The version query requested identification only.

## Read the working battery estimate

Requires macOS and Xcode command-line tools. macOS may require Input Monitoring permission for the host application.

From this project directory:

```sh
sh build.sh
sh read-battery.sh
```

Observed output:

```json
{"device":"Keychron K2","battery_percent":58,"source":"firmware_indicator_state","firmware_build":"20191025"}
```

This reads the firmware's existing battery estimate. It is not an independent measurement of charge capacity. Agreement with Fn+B validates the corresponding charge band, not laboratory accuracy or the full discharge curve. A charge/discharge cycle has not been tested.

## What the installed code shows

The installed Bluetooth build's RAM was read through Cypress/Infineon's SETUP_READ (`0x71`) and READ (`0x72`) commands. All returned blocks were checked for report ID, address, length and checksum. No update-mode enable, erase, memory-write or launch/reset commands were sent.

The inspected path is:

1. The keyboard shortcut handler at `0x206dc0` loads the battery object from the global structure at `0x208e80`, offset `0x28`, then calls `0x2082c2`.
2. `0x2082c2` loads a byte from that object at offset `0x14`. It compares the byte to 70 and 30 to choose the indicator behavior.
3. The small accessor at `0x2082be` independently loads that same byte.
4. The global pointer slot is therefore `0x208ea8`. In the observed session it points to `0x20c9d4`; the percentage byte was at `0x20c9e8` and contained decimal 58.
5. A separate fresh one-byte diagnostic read returned 58, followed by a successful read through the guarded reusable reader. The standard Bluetooth input report 3 still returned `03 00`.

This establishes a working route to the state used by the battery indicator. Further ROM analysis found that the standard report uses a separate cached field that contains zero. See [firmware analysis](FIRMWARE-ANALYSIS.md) for that path, the official downloaded reference images, and remaining limitations.

## Reader safeguards and scope

`inspect.c` implements the working reader. Before interpreting the battery byte it verifies:

- The observed diagnostic identity, including version byte `0x05` and build date `20191025`.
- The exact bytes of the battery accessor/indicator functions and shortcut caller.
- The global-structure literal used by the installed code.
- The object pointer's alignment and RAM bounds, its expected type table, a 0-100 percentage, and an unchanged pointer across the read.
- Every memory response's header and checksum.

The pointer is resolved on every run; the observed heap address is not hardcoded. This reader supports only the inspected firmware layout. Unexpected versions or layouts produce an error. It does not fall back to reporting the unreliable 0%.

The guarded reader now obtains identity directly from the verified record at `0x208f02`, avoiding the identification output request that later returned an access error. It uses memory-read setup and feature reads only, with no input callback. SETUP_READ selects an address for a subsequent read; despite using the HID SET_REPORT operation, it does not write firmware or saved settings. No login item, pairing change, reboot or firmware update was installed.

`battery.c` remains a separate diagnostic for the unreliable standard report. The build creates it as `build/keychron-raw-battery`; its output is explicitly unvalidated.

Raw snapshots and disassembly are stored under `private/`, excluded from version control with restricted permissions. They may contain device state and should remain private. The reader itself needs no full snapshot.

## One-hour discharge experiment

A bounded logger was started on 27 October 2026 at 19:08 IST, with white backlight confirmed at maximum brightness and auto-sleep previously disabled. Unplugged operation is assumed unchanged from the owner's earlier confirmation. The initial internal estimate was 53%, the cached and standard reports were 0%, and the raw sensor average was 1733.

`battery_logger.py` samples every five minutes for one hour, without changing keyboard settings or preventing Mac sleep. It records failed reads and sampling gaps, stops after three consecutive internal-read failures, and treats an initial internal-read failure as an immediate stop. `private/discharge-tests/active.json` points to the session's metadata, samples and summary. This is an estimate-under-load experiment; it does not measure current, usable capacity or an exact full-charge runtime. Diagnostic polling itself adds traffic. A thread follow-up is scheduled to review completion.

The owner subsequently stopped the discharge run to try charging, then stopped that run for individual plug/unplug and lighting observations. No background recorder remains running. The follow-up was paused. The owner later clarified that the backlight was off during the initial charging readings; the correction and later single samples are in `private/discharge-tests/manual-observations.jsonl`.

Further captured ROM analysis established the exact sensor conversion: `clamp(floor((raw_average - 1520) / 4), 0, 100)`, after an eight-sample rolling average. All twelve recorded sensor/percentage pairs match execution of the captured conversion routine offline. This confirms the firmware estimate, not its accuracy as a charge measurement. See the follow-up section of [firmware analysis](FIRMWARE-ANALYSIS.md) for the Trackpad comparison and runtime options.

## Verification

`build.sh` compiles with warnings treated as errors and runs offline checks for malformed responses, checksum corruption, address mismatch, truncated packets, prohibited address ranges and invalid object pointers. These tests do not access hardware.

Live verification completed on the connected K2: checksum-verified snapshot, a separate direct read of the discovered byte, guarded battery read returning 58%, and a comparison standard-report read returning 0%. The owner's blue Fn+B observation matches Keychron's documented 30-70% range.

## References

- [Keychron K2 battery-color documentation](https://www.keychron.com/pages/firmware-for-k2-keyboards)
- [Infineon AN214821: diagnostic memory-read protocol, section 7.2](https://www.infineon.com/assets/row/public/documents/30/42/infineon-an214821-upgrading-human-interface-device-firmware-example-protocol-commands-and-scripts-applicationnotes-en.pdf)
- [Community original-K2 reader and its compatibility limits](https://github.com/wretchedworm/keychron-k2-battery-sleep)
- [Community battery-reader implementation](https://github.com/wretchedworm/keychron-k2-battery-sleep/blob/main/Sources/BatteryReader.c)

The community project's firmware-specific addresses were not reused as battery addresses: its verified firmware is 1.08, dated 20210820, whereas the addresses above were derived from this keyboard's installed 20191025 build.
