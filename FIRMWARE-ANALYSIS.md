# Firmware references and battery/power analysis

Inspected on 27 October 2026. No updater was executed. No firmware, settings, pairing or device RAM was written. Diagnostic SETUP_READ requests select a read cursor; they do not modify firmware or configuration.

**Current scope:** investigate custom firmware modifications on the existing K2 electronics first. Installing a stock update is not the owner's goal; official images are analysis references. The owner rejected the Magic Keyboard donor-controller proposal and reports that runtime remains close to historical behavior, with no noticeable capacity deterioration. Treat the present battery as adequate for this firmware investigation. Hardware-replacement alternatives below are historical research, not an active recommendation. No flashing or live device configuration changes are authorized.

## Latest initial-release status: board compatibility, recovery and battery component

The owner confirms US/ANSI horizontal Enter, RGB lighting, two rear height settings and a non-hot-swappable model. This fits the published K2 V2 US RGB target at product-variant level; physical PCB marking/recovery pads and the installed scanner image remain unverified. Passive USB identifies bcdDevice0104 but its descriptor differs from the downloaded image named1.04, so it is not an installed-image fingerprint.

Read-only captures now include the full documented320KiB Bluetooth ROM region and all64KiB of its virtual EEPROM address window, including SS/DS/VS saved privately. This supersedes the earlier limited-capture inventory below. Logical-window coverage does not establish physical EEPROM geometry. No Sonix flash backup or device firmware/settings write has occurred.

The initial release now includes an **experimental Bluetooth DS candidate based on the exact installed application**, in addition to scanner A. A440-byte extension reserves normal-cold-boot memory, installs an allocator-owned shadow battery vtable and repairs ordinary report3 queries, up/down notifications and connection reporting. Fifteen component tests (including all101percentages) and eight persistent-boot tests pass. Actual original ROM startup, BSS clearing, factory registration and heap initialization execute in selected tests. Astra independently reviewed emitted bytes and tested the relocated component. Native macOS display, physical activation, EEPROM write geometry and recovery remain unverified; no updater/flash script was executed or supplied as approved.

The complete current handoff is [firmware/INITIAL-RELEASE.md](firmware/INITIAL-RELEASE.md). It distinguishes USB scanner boot-ROM recovery from radio EEPROM rollback, the current flasher's protection-downgrade hazard, the proposed retained-SS/DS staging transaction, and the physical evidence still needed. Neither component is cleared for flashing.

## Earlier build: conservative CPU-idle candidate A

The owner confirms **two fold-out rear height settings**, supporting the K2 V2 hypothesis. The published V2 RGB 1.13 reference is now used to build a reproducible **CPU-idle candidate A**, with source, raw image, disassembly, manifest and offline results. See [firmware/README.md](firmware/README.md) and `artifacts/k2-v2-rgb-cpu-idle-a/`. This is a reference-based experimental image, not a captured installed firmware or a hardware-cleared update.

A replaces one main-loop call with a 212-byte wrapper that executes the original wireless sleep handler first, then requests PMU mode 4 only when read-only mode, bus, interrupt, clock and timer guards permit it. Scanning/PWM, SysTick, SPI reception, GPIO, clocks and watchdog handling remain as stock. This deliberately precedes the more aggressive scanner-stop experiment below. The only additional peripheral writes are PMU selection and restoration. Vectors, original handler, persistent region `0x7000..0xa3ff`, and footer are unchanged. Fourteen offline test methods plus twenty skip-guard subcases pass; WFI/wake is modeled, not physically executed.

This build does not add native macOS battery reporting or alter reconnect behavior. No power reduction, monthly runtime, silicon wake, installed-image compatibility or board-specific recovery route has been verified. It is marked **not cleared for flashing**, with no updater or flash script bundled. No live firmware, settings, pairing or device RAM writes occurred.

Independent `gpt-6-astra` review found no blocking defect for offline packaging of the emitted image (SHA-256 `0d5da2541dcc54be0909b6ce9fde79da46a20a45c38aafb3b26e35c7c97e4293`). It checked both branches, all fourteen literal loads, call order, stack/register preservation and PMU restoration. Traced normal persistent writes end at `0xa3ff`; an existing zero-count USB write corner case reaches `0xd7bf`, still below the stub. Review evidence and limits are recorded in `artifacts/k2-v2-rgb-cpu-idle-a/astra-review.json`. No hardware clearance follows from that review.

## Earlier feasibility result: retained-SPI scanner sleep and approximately 500 ms wake

The owner's acceptance condition is a genuine wake key followed by useful typing when the Mac wakes, approximately half a second in the described setup. The keyboard must transmit the physical key event if it is to wake the Mac; consuming it in macOS is different from discarding it inside the keyboard. Local scanner wake, delivery over an existing radio link, Mac display wake and reconnect after leaving range are separate timings.

An additional Astra investigation and parent code experiments now support a **concrete firmware-only candidate using Sonix PMU mode 4**, keeping the SPI clock/receiver and its interrupt active while idling the CPU and stopping scan/PWM activity. The manual explicitly permits retained peripheral clocks in mode 4 and no oscillator-restart delay when that clock remains running. The existing reference sleep entry disables the scan-timer clock, but not SPI's clock-enable bit. This makes a radio firmware patch conditional, rather than mandatory for any connected scanner idle. The deeper mode-2 timing concern below remains relevant if more aggressive power saving is needed.

`research/test_connected_sleep_candidate.py` passes **four offline cases** using the hash-verified V2 RGB 1.13 reference. Emulator-only changes remove the local disable-sleep gate, omit the slow-clock switch and select mode 4. The entry test reaches WFI with SPI clock/IRQ retained, scan clock and SysTick stopped, and the stored auto-sleep setting intact. Separate byte-by-byte executions of the actual SPI ISR and parser correctly apply host LED and low-battery messages. NVIC write-one-set/clear semantics are modeled. Results: `private/connected-sleep-candidate-emulation.json`. There is no physical FIFO, interrupt-arrival, WFI exit, timing or power model. Entry assumes a quiet bus; a complete race-safe guard and full resume/output behavior remain to be implemented. No flashable image was produced, and the installed scanner variant is still unknown.

Five small guarded ROM reads on the connected keyboard captured **1,792 bytes** around the Bluetooth delay helper and its dependencies, verifying the existing 20191025 identity and every block checksum. These reads did not execute the helper or modify firmware/configuration. The helper uses a CPU-frequency table and calibrated cycle loops, strongly supporting a microsecond-scale pre-transfer delay rather than a millisecond allowance. Actual electrical timing remains unmeasured. Capture provenance and disassembly: `private/wake-feasibility-rom-capture.json`. This extends selected ROM evidence, not a full firmware/recovery backup.

The fresh host-side cache comparison in `private/cached-hid-wake-feasibility.json` confirms both the Trackpad and K2 connected and advertising remote wake. The normally-connectable difference persists. Full current System Profiler output exposes Classic HID ACL and firmware identifiers but no sniff interval; no current interval was inferred from it. No active SDP query, link-policy setting or reconnection was performed.

The full [Apple comparison and feasibility report](research/apple-wake-feasibility.md) separates public teardown observations, a firsthand historical Magic Trackpad 2 sniff-mode report, manufacturer capabilities and unknown Apple firmware internals. Approximately 500 ms local readiness is credible; physical wake/report latency and **20–30-day runtime remain unverified**. Retaining the oscillator may consume too much for the required roughly 80–90% reduction from the reported 3–4-day runtime. A first key used only for wake does not remove the requirement to receive unsolicited Bluetooth messages correctly.

## Current independent Astra investigation

The owner subsequently requested **Astra** as advisor, replacing reliance on the earlier same-model Sol review. A fresh `gpt-6-astra` investigation with high reasoning examined manufacturer source, FCC photographs, SDK support statements and the original captures. Its detailed report is [research/astra-firmware-findings.md](research/astra-firmware-findings.md). This new evidence and more specific hypothesis take precedence over the earlier generic integration explanation below; the earlier Sol review remains a historical record.

The leading concrete issue is the **incoming transfer's wake-to-receiver-ready deadline**. The original radio is SPI master while Sonix deep sleep stops peripheral clocks. Captured sender `0x208498` asserts attention and calls a fixed delay helper before transfer, with no visible receiver-ready polling in that function. Delay units, caller safeguards and actual timing are unknown. Independent sleep may therefore require a revised ready/acknowledgment or buffering/retry contract, not merely changing the idle gate.

Two primary comparisons materially support investigating this constraint:

- Official Keychron Pro source at commit `618127a725a1773e85f13455602cf6f72ab4de17` implements scanner STOP1 independently of the radio's two-hour idle timeout. Its low-power code explicitly explains approximately 200 us from module wake assertion to UART data, versus approximately 2 ms with normal clock initialization, and implements restoration under 100 us. These are Pro implementation timings, not measurements of this K2. [Manufacturer wake implementation](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/lpm_stm32l432.c).
- K8 Pro FCC photographs visibly identify a CYW20730 A2KFBG radio, establishing one later Pro board with the same radio family and improved surrounding architecture. This is not a physical identification of the user's K2 or every Pro revision. [FCC photographs](https://fccid.io/2ASF4-K8PRO/Internal-Photos/Internal-photos-6826572.pdf).

The downloaded main 1.13 accepts wake notice `B6 5A 0B` and emits `A6 51 60`; the captured installed 20191025 Bluetooth dispatcher does not implement that acknowledgment command. This demonstrates a version-specific protocol boundary, not proof of mismatched installed firmware. The suspicious GPIO P1.8 clear is traced to low-battery blinking, weakening a radio-power-switch explanation. Original-code evidence and hashes are in `private/original-spi-wake-analysis.json`.

Astra assigns medium confidence to the original SPI timing constraint as the actual obstacle, and high confidence that it must be resolved before treating the gate experiment as a viable fix. No hard hardware impossibility, manufacturer motive, monthly runtime, complete reconnect repair or native macOS battery solution has been established. No live device actions occurred in this investigation.

## Latest firmware-only finding: scanner sleep and Bluetooth disconnect are coupled

**There is now a concrete modification candidate on the existing electronics.** In both published RGB main-controller references examined here, disabling auto-sleep also prevents the key-scanning processor's local inactivity countdown from advancing when it otherwise could. Separately, the installed Bluetooth application disables its 600-second connection-sleep timer. This links two policies that the requested behavior needs to separate: local processor sleep and Bluetooth connection retention.

This is a demonstrated code path in downloaded Sonix images plus the captured Bluetooth application, not proof that either downloaded Sonix image is installed in this unit. It is a plausible contributor to the reported runtime change, not a measured allocation of board power or a guarantee of monthly runtime. The firmware's existing behavior can be a design limitation without assuming that Keychron intended a feature and implemented it incorrectly.

### Exact code and the offline experiment

| Reference | Local idle policy | Emulator-only candidate |
|---|---|---|
| V2 RGB 1.13 | Handler `0x194`; idle countdown `0x200001ac`; pending/activity byte `0x20000191` OR auto-sleep-disable byte `0x20000166` blocks decrement | At `0x1c8`, replace `ORRS r1,r2` (`11 43`) with `CMP r1,#0` (`00 29`), keeping the pending/activity guard |
| V1 RGB 1.62 | Handler `0x194`; idle countdown `0x20000198`; pending/activity byte `0x20000180` OR auto-sleep-disable byte `0x20000155` blocks decrement except on forced sleep | At `0x1d4`, replace `ORRS r2,r3` (`1a 43`) with `CMP r2,#0` (`00 2a`), keeping the pending/activity guard and forced-sleep path |
| Captured installed Bluetooth build 20191025 | Root application object `0x20c808`, method `0x207132`, flag `+0x12c`; `0xaa` stops its timer, `0x55` permits countdown toward a connection-sleep request | Keep the disconnect-disable policy; no Bluetooth code modification is needed merely to retain that flag |

In V2 1.13, the auto-sleep shortcut both changes the local policy byte and sends a command over **SPI0**. Command sender `0x4790` prepares `A6 51 65`; sender `0x47f0` prepares `A6 51 68`. The captured Bluetooth parser handles those through `0x206d76` / `0x206d90`, setting the disable/enable flag respectively. The chips use SPI0 plus GPIO handshake in these paths; calling that bus UART would be incorrect. Shared command structure does not establish an exact main-image match.

`research/test_scanner_idle_policy.py` executes the actual compiled instructions under Unicorn with peripheral housekeeping and timer/connection callbacks mocked. **20 cases passed:** eight each for V1 1.62 and V2 1.13, plus four for the installed Bluetooth timer. They cover disabled/enabled policy, countdown expiry, pending activity, missing tick and forced sleep. The candidate allows local countdown while retaining the stored disconnect-disable setting; the installed Bluetooth disabled branch continues to stop its timer and does not request connection sleep. The scanner tests stop at sleep-entry code, before hardware operations.

Only emulator memory is changed. No patched Sonix binary, updater or deployable firmware package was produced. The offsets are hash-specific, not instructions to patch an unidentified keyboard. Evidence: `private/scanner-idle-policy-emulation.json`.

### Wake handling and why the two-byte experiment is not a complete fix

V2 1.13 sleep entry `0x1de` disables scan/PWM timer CT16B1, stops SysTick/watchdog, configures GPIO and changes clock source before `PMU_CTRL=2; WFI` at `0x24e`. The return path restores clocks, tick/watchdog, timer and matrix state. The [Sonix manual](https://www.sonix.com.tw/webapi/fl219873/SN32F248B_V2.4_EN.pdf) defines mode 2 as deep sleep with GPIO wake. The image also contains mode 4 CPU sleep in its USB-suspend path at `0xd04`, but that is not an already implemented wireless connected-idle policy.

The wireless sleep path chooses one of two wake setups:

- `0xab0`: enables GPIO2 bit 15 and GPIO3 bits 7-11, with IRQ29/IRQ28 handlers at `0xa5e`/`0xa36`. These match **C15 and D7-D11**, all six rows in the [community K2 V2 pin map](https://github.com/SonixQMK/qmk_firmware/blob/sn32_develop/keyboards/keychron/k2/rgb/v2/ansi/keyboard.json).
- `0xaec`: enables GPIO0 bit 1, with IRQ31 handler `0xa86`. The same pin is read in the SPI transfer handler, supporting a bus/handshake relationship, but its physical net and full wake contract have not been established for this unit.

`research/analyze_scanner_wake.py` executes the two existing setup routines separately and consecutively in emulated MMIO memory. **Three cases passed**, confirming their requested interrupt-enable masks and that requesting both does not overwrite the other's port masks. This does not model physical edges, interrupt arrival, retained peripheral state, pending-key races or a working keyboard wake. The firmware currently selects between them; a connected-idle modification must deliberately handle key wake, Bluetooth-side attention, cleanup of wake interrupts, clock/SPI restoration and any GPIO side effects. The electrical role of all pins altered at sleep entry is still unverified: scanner sleep must not cut radio power or violate a required handshake. Evidence and annotated disassembly: `private/scanner-wake-analysis.json`.

The main loop at `0x776..0x7a4` repeatedly services work and dispatches to the wireless/USB handlers; there is no direct WFI in that loop. Existing deep-sleep branches provide an implementation starting point. Their presence does not show how much power the installed board currently uses or that the radio will tolerate a sleeping scanner without further changes.

### Battery, reconnect and upgrade feasibility

The battery-query repair remains the more isolated code change: refresh the stale standard-report cache from the already measured estimate and permit bounded updates in both directions. Its **22 previously recorded offline cases passed**. ROM routines cannot be edited in place; a persistent implementation needs a boot-loaded RAM override or equivalent supported hook. Startup integration and persistent-image packaging have not been implemented. Correct HID reports still need validation against macOS's native battery publication; a valid percentage alone does not prove the native Bluetooth UI will display it.

Return reconnection is a separate problem from staying connected during desk idle. Captured connection-state overrides at `0x207994`, `0x2079fe` and `0x207a66` delegate into ROM state transitions and schedule notifications/timers, but no fixed 8-10-second delay has been causally identified. The previously found 10,000-valued timeout is guarded by a disabled byte in the saved configuration. Page-scan parameters and sniff support were located, but neither proves the bottleneck. There is no demonstrated faster-reconnect patch yet.

Official updates establish separate main-controller and Bluetooth update routes, not a known ready-made fix for these goals. V1 RGB 1.62 and V2 RGB 1.13 are different hardware reference streams. Installing either merely because its number is newer would be unjustified. We have published reference images, captured Bluetooth RAM and selected ROM sections; **we do not have this unit's complete installed firmware/recovery copy**, nor confirmed V1/V2 PCB identity or a validated custom-image installation/recovery procedure.

The firmware-only recommendation is to develop the scanner-idle/wake change and battery-report hook against the confirmed board/image, then validate on hardware only after a separate decision. Existing evidence supports continuing that work on the original controllers. It does not establish the requested 20-30 days, subsecond connected wake, 1-2-second return reconnection or native battery display yet. Battery replacement and donor-controller work are outside the current investigation.

## Explanation review: why available hardware capability was not sufficient

Follow-up research on 27 October 2026 examined the historical HID standard, host behavior and an independently implemented related keyboard. Exactly one advisor consultation followed evidence gathering. It challenged the working theory without device access or modifications. The conclusion below is a ranked technical inference, not a recovered account of Keychron's internal decisions.

**Best-supported theory:** the original integration provides coordinated deep sleep and continuous operation, while an independently supported connected-idle state for the external scanner is missing when auto-sleep is disabled. The demonstrated coupling is high-confidence in the named references. Its historical origin—vendor policy, product scope, reliability tradeoff or an unresolved defect—is not established. Cross-platform interoperability raises the coordination and validation burden but has not been shown to require this policy.

1. **Two-controller integration is the strongest lead.** A Bluetooth link's connected low-power state does not manage the external scanner's clocks, PWM, GPIO or SPI. The relevant compiled scanner gate and Bluetooth timer branch do not make their decision based on a Mac-versus-Windows selector. Stopping the disconnect timer is not proof of disabling radio sniff. A competent product team could ship a default deep-sleep policy that meets its normal battery goal while leaving independent connected standby unsupported. That is a plausible explanation of the product boundary, not evidence of development budgets, incompetence, vendor ownership or intent.
2. **The missing communication contract is a concrete technical complication.** A complete connected-idle state must handle held keys, in-flight transfers, Bluetooth state changes, host LED output, low-battery notifications, both wake directions and clock/peripheral restoration. These are requirements for correctness, not hypothetical reasons to refuse firmware work. A hardware wake demonstration alone does not verify the whole state.
3. **Host compatibility affects parameters and reconnect responsibility.** It is a credible contributor to conservative implementation and validation, but not an established fundamental barrier. The radio may already use connected power saving; observe its existing behavior before changing it.
4. **A specific K2 board constraint is still an alternative.** Unknown GPIO net functions, clock/peripheral retention and installed main image prevent ruling it out. Related-board evidence makes a blanket claim that the chip cannot do it less plausible.

### Standards and host evidence

The [Bluetooth SIG HID 1.1.1 specification](https://www.bluetooth.org/docman/handlers/downloaddoc.ashx?doc_id=309012), sections 5.1.8 and 5.1.8.5, specifies connected power-saving interoperability, negotiation and subrating. Host defaults can reduce the benefit; support does not establish the parameters in use. Section 5.3.4.14 separately defines disconnected connectability. These rules concern the radio link, not an external scanner's sleep implementation. The official PDF and extracted text are saved under `private/references/bluetooth-hid-1.1.1.*`.

- **Apple:** its [Accessory Design Guidelines](https://developer.apple.com/accessories/Accessory-Design-Guidelines.pdf), section 57.3, call for Classic sniff/subrating support. Apple-platform compatibility does not require an always-running scanner.
- **Windows:** Microsoft's [Modern Standby Bluetooth guidance](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/bluetooth-power-management-for-modern-standby-platforms) documents idle connected sniff and wake from paired HID devices. Its D2 current/latency figures describe the PC's radio, not this keyboard.
- **Linux:** [BlueZ 5.55 input code](https://github.com/bluez/bluez/blob/5.55/profiles/input/device.c) distinguishes host/device reconnect modes using the declared HID properties. Its host auto-reconnect path applies to host/any modes. The K2's captured declarations map to device-initiated reconnect. This establishes a real policy distinction, not macOS's measured delay.
- **Android:** the [Android 10 interoperability header](https://android.googlesource.com/platform/system/bt/+/android-10.0.0_r1/device/include/interop.h) includes a device-specific HID sniff-interval workaround. This is evidence of real interoperability variation, not a Keychron-specific diagnosis.
- **Historical product counterexample:** Logitech's [K810 guide](https://www.logitech.com/assets/46511/bluetooth-illuminated-keyboard-k810.pdf) documents Windows, iOS and Android compatibility and long backlight-off usage. It supports coexistence of multi-platform support and efficient keyboard operation. It does not establish the same chip, continuous connection, precise wake timing or a runtime prediction for this K2.

### New related implementation: original K8 connected scanner sleep

The [goyamamoto K8 project](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/keyboards/keychron/k8/readme.md) publishes custom firmware for the original RGB K8 using SN32F248B and an ITON Bluetooth interface. Its control protocol matches the inspected K2 command family. The author reports a cable-unplugged Mac test where scanner sleep and key wake retained the connection, with the timeout shortened to 20 seconds. Battery life and the release ten-minute timeout are explicitly untested; the author also documents a possible missed Caps Lock update during sleep.

The reviewed [`sleep.c`](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/keyboards/keychron/k8/rgb/sleep.c) stops the scan/PWM timer, sets LED/matrix GPIO, switches to ILRC and sleeps with key-row interrupts, while masking Bluetooth-side wake. It blocks entry during transfers, held keys or USB use. This is architectural feasibility evidence, with incomplete incoming-event handling; it is not a ready K2 image or a measured power result. Crucially, the reviewed `rgb.c` and `iton_bt.c` contain no invocation of the header's sleep-disable command. A 20-second experiment therefore does not establish retention beyond a separate module disconnect timeout; persisted module policy is unknown.

Primary source snapshots, hashes and limitations are recorded in `private/design-hypothesis-evidence.json`, with source files in `private/references/k8-custom-*` and `bluez-5.55-input-device.c`.

### Separate explanations and consequences for a rewrite

The K2's `NormallyConnectable=false` declaration is consistent with allowing radio shutdown when disconnected, while taking responsibility for reconnection. The Trackpad declares a different policy. The eight-to-ten-second return delay also occurs with auto-sleep disabled, making scanner wake alone an insufficient explanation. Changing an SDP Boolean without implementing its promised behavior is not a reconnect fix.

The battery code already contains standard-report machinery but leaves the observed cache stale and connection reporting disabled. An unused or incomplete reporting path is better supported than intentional suppression to hide an inaccurate estimate. The advisor identified a possible initialization-order failure: a zero initial sample could seed the decrease-only cache at zero, with no later upward correction. This is a testable hypothesis, not a demonstrated startup trace. Native macOS publication is a separate requirement.

The rewrite should define an explicit connected-idle state and its bidirectional wake/communication contract, retain appropriate radio power negotiation, and validate beyond all existing inactivity timeouts. Before selecting radio changes, establish actual sniff/subrating behavior; quantify scanner and whole-board idle saving; trace reconnect stages and battery initialization separately. These are future discriminators, not measurements or hardware modifications performed in this review. No Keychron engineering explanation was located, and none of the inferred motives should be presented as confirmed history.

## Latest scope and comparison with Magic Keyboard

The owner's clarified target is **Magic Keyboard behavior with the existing K2's mechanical feel**, excluding Touch ID:

| Requirement | Target |
|---|---|
| Charge interval | About 30 calendar days in the owner's light use, with backlight off; 20 days is an acceptable fallback |
| Wake from ordinary idle/Mac sleep | Wake key may be consumed; ready for subsequent typing when displays wake, roughly 0.5-1 second in the owner's setup |
| Reconnect after returning with the laptop | Roughly 1-2 seconds after a keypress, instead of the reported 8-10 seconds |
| Charge visibility | Prefer native macOS Bluetooth battery display; useful low-charge indication need not be laboratory-accurate |
| Mechanical parts | Preserve case, plate, switches, keycaps and typing feel as closely as possible |

The physical wake-key requirement supersedes earlier suggestions to preserve the initial wake keystroke. Swipe filtering is irrelevant to this keyboard. Mac display wake time, keyboard wake time and Bluetooth reconnection time are different quantities and need separate acceptance tests.

The owner supplied an underside serial whose model component is **K2-C1**, with production prefix **2009**; full identifiers are stored only in `private/keyboard-label.json`. Published listings associate K2-C1 with RGB/aluminum/red-switch K2 variants, including V2. Community interpretation of the four-digit prefix suggests September 2020, but no manufacturer decoding rule was verified. This makes V2 a plausible working hypothesis, not sufficient proof for selecting a flash image. Physical revision/PCB identification remains outstanding.

### Firmware recency: correction and date limits

- The [official V1 page](https://www.keychron.com/pages/firmware-v2-3-for-k2-keyboards) still lists **1.62**, with no verified calendar release date. A [July 2020 owner post](https://www.reddit.com/r/MechanicalKeyboards/comments/hrztrl/) mentions that version; it is historical community evidence, not an official release announcement.
- The [official V2 page](https://www.keychron.com/pages/firmware-for-k2-version-2) also offers **RGB 1.13**, with **20220516** in its filename, and white-backlight 1.11 with **20210918** in its filename. The RGB package is a newer V2 reference than the previously inspected 1.04. The page's July 2020 release dates refer to older downloads; they must not be assigned to the newer files. CDN query timestamps may reflect rehosting, not release dates.
- The V2 RGB 1.13 updater was downloaded without execution. Its firmware is in PE resource type 10 / ID 4000 / language 0, rather than the embedded ZIP's file list. A 65,536-byte raw payload was extracted offline and hashed; provenance is in `private/vendor/k2v2-rgb-1.13-extraction.json`. It is a published reference, not the installed main-controller image or a backup of this unit.
- The installed **Bluetooth** build remains **20191025**. The separately downloaded non-backlit Bluetooth 1.09 reference contains **20211217**. Neither proves the main-controller version; neither establishes RGB/V1/V2 compatibility. Main and Bluetooth version numbers are separate streams, and numerically higher main versions across hardware revisions do not imply compatibility.
- The downloaded Windows updaters share a September 2017 PE timestamp; old HEX ZIP entries have invalid/default dates. Those container timestamps cannot date the firmware release.

### What Apple demonstrates, and what remains inferred

Apple's [Lightning Magic Keyboard specification](https://support.apple.com/en-ae/112443) rates it for about a month or more. The [2015 Magic Keyboard teardown](https://www.ifixit.com/Teardown/Magic+Keyboard+Teardown/50995) identifies a **2.98 Wh** battery, Broadcom **BCM20733**, and an STM32 controller. The [Magic Trackpad 2 teardown](https://www.ifixit.com/Teardown/Magic+Trackpad+2+Teardown/51032) identifies **2,024 mAh / 7.65 Wh**, BCM20733 and multiple processing components. These are teardown specimens, not measured capacities or confirmed exact internal revisions of the owner's devices. They support the owner's point that surface area, processing complexity and chip count alone do not dictate average power.

The [CYW20733 datasheet](https://www.infineon.com/assets/row/public/documents/30/57/infineon-cyw20733-single-chip-bluetooth-transceiver-wireless-input-devices-datasheet-additionaltechnicalinformation-en.pdf) documents activity-driven power modes, low-power oscillation during sniff and hardware wake support. Apple can therefore maintain a logical connection while much circuitry sleeps between scheduled radio events, and wake local processing on user input. This is an architectural explanation supported by the components' capabilities, **not a trace of Apple's exact running firmware or negotiated timing**. We have not captured Apple's firmware, measured its current or established its gesture-filtering implementation. Apple's end-to-end control of its accessory firmware and macOS integration is relevant, but the exact reason Keychron did not deliver equivalent behavior is unknown.

These mechanisms predate current LLM tools. LLM assistance can reduce reverse-engineering and implementation effort; it does not establish that a power fix is trivial or remove the need to measure the hardware and validate firmware. No manufacturer motive, engineering incompetence or intentional battery-report suppression has been established.

### Current Apple guidance and passive device comparison

The current [Accessory Design Guidelines for Apple Devices](https://developer.apple.com/accessories/Accessory-Design-Guidelines.pdf), release **R31, 21 September 2026**, were downloaded and text-extracted offline. Sections **57.3** (pages 338-339) and **57.13** (page 349) recommend sniff/subrating for Classic Bluetooth accessories, a 15 ms base sniff interval, and HID SDP subrating parameters of 450 ms maximum host latency and 45 ms minimum timeout. The document permits usage-specific parameters. This is more appropriate starting guidance than blindly forcing the earlier suggested 60-100 ms candidate intervals. Actual accepted parameters and their current/latency tradeoff must be observed on this Mac; 450 ms is not a promised key-to-screen latency.

`research/compare_cached_hid_services.m` reads only previously cached SDP records using IOBluetooth's cached-service getter. It has no active SDP query, connection, disconnection, setter or HCI submission. Its current output is stored in `private/cached-hid-comparison.json`:

| Cached HID attribute | Trackpad | K2 |
|---|---|---|
| Remote wake | true | true |
| Device initiates reconnect | true | true |
| Normally connectable | true | false |
| Optional host max subrating latency | absent | absent |
| Optional host minimum subrating timeout | absent | absent |

The reconnect declaration difference is a candidate for understanding host/device connection responsibility; it is not proof of a delay or power defect. Adding subrating attributes alone cannot be called the fix, since the Trackpad performs well without those optional entries too. Cached SDP values do not reveal the actual negotiated link mode, sniff interval or current consumption. A passive Bluetooth log search did not establish device-specific current sniff parameters.

Additional read-only ROM captures locate the **Sniff Mode** command builder at `0xf788` (HCI opcode `0x0803`), **Exit Sniff Mode** at `0xf7e4` (`0x0804`), and **Sniff Subrating** at `0xff0c` (`0x0811`). These prove code support, not active use. No builder was executed on hardware. The inactive-transition path `0x14ec8 -> 0xad08 -> 0xfcae` programs **page-scan activity**, opcode `0x0c1c`, with an 80 ms window / 1,280 ms interval in the captured configuration. Page scan is not connected sniff mode and those values do not identify the measured reconnect bottleneck.

A 10,000-value configuration field at `0x200974+0x4b` is passed to method `0x1473e` by wrapper `0x147a6`, but the method checks enable byte `+0x49`, which is **zero in the snapshot**, before using it. An 8,000-value field also exists at `+0x3c`; its role is not established. It would be unjustified to lower either number and claim the reported 8-10 second reconnection is fixed. Disassembly, hashes and limits are in `private/power-path-analysis.json`.

### Changes worth pursuing versus unsupported shortcuts

| Change | Expected benefit and present evidence | Necessary validation |
|---|---|---|
| Existing-board connected standby | Keep the link alive; sleep the scanner/CPU between real events; accept/coordinate sniff and subrating; stop unnecessary timers/housekeeping | Measure whole-board battery-side idle draw and actual link mode; verify rapid wake and held-key behavior. This remains a proposed power fix. |
| Directed reconnect to the paired, selected Mac | Investigate wake/boot, paging, retries and HID channel setup separately, avoiding unnecessary discovery/profile cycling | Time each stage during departure/return. Existing 8,000/10,000 constants are not established bottlenecks. |
| Battery reporting/cache repair | Use the already identified estimate, seed/refresh the stale report cache, send bounded changes in both directions | Existing query-handler emulation passes; physical notifications and native macOS publication remain untested. Avoid polling that defeats low-power states. |
| Stable backlight-off battery estimate | Calibrate against a measured discharge curve; account for charging/settling; use conservative alerts | Need battery/charging-state identification and capacity/voltage measurements. A fuel-gauge IC is optional if better accuracy is later required; it does not fix power draw. |
| Battery replacement | Restore runtime if the existing cell has lost usable capacity | Capacity/health and physical fit; no evidence yet that a new cell alone reaches one month. |
| Lower scan speed / lower radio output alone | Could reduce a verified contributor | Not a substitute for idle sleep; aggressive changes can harm response, reliability or reconnection. |
| Longer auto-disconnect timeout | Changes when the existing disconnect occurs | Does not reduce connected current or implement prompt connected wake. |

A healthy hypothetical 4,000 mAh usable cell lasting 3-4 full days implies roughly 42-56 mA average draw. This is a conditional calculation from the owner's approximate runtime, not measured current. A degraded cell or an incomplete charge invalidates that inference. A 30-day goal allows only about 5.6 mA before reserve/losses. The decisive missing evidence is still battery-side current during connected idle/typing/deep sleep and usable cell capacity. The installed Sonix scanning-controller image has not been captured; its power behavior cannot be proven from downloaded reference images alone.

### Historical rejected route: genuine Magic Keyboard controller

The creator's [Hephaestus Mod repository](https://github.com/limentic/the-hephaestus-mod) publishes a mechanical-switch PCB connected to a genuine Magic Keyboard motherboard, with KiCad files, a mapped AZERTY matrix, development-board files and motherboard/battery mechanical models. The [creator's build log](https://geekhack.org/index.php?topic=120964.0) reports development matrix testing. The current repository README explicitly marks the production PCB **untested** and notes development-board errors for 9, Tab and right Option. It is an engineering reference, not a completed K2 conversion kit or proof of monthly runtime after modification.

This route could retain Apple's original wireless/battery integration while replacing the physical switch assembly with the owner's mechanical switches, plate and case. It requires a K2-shaped custom switch PCB or extensive rewiring to the donor's expected matrix, donor-specific connector work, a compatible battery/charging arrangement and verified mechanical/antenna clearances. A compact donor may lack directly mapped K2 navigation keys; donor selection and all key mappings remain open. A voltage/capacity-incompatible K2 cell must not simply be attached to an Apple charger. Reuse a matched donor power system or design an appropriate interface. Touch ID is excluded from this task.

The owner rejected this route. It is retained only as a historical reference and is not a recommendation or prerequisite for the firmware-only work above.

## Follow-up: estimator, Trackpad comparison and long-runtime options

Additional read-only ROM segments were captured at `0x14000`, `0x15000` and `0x1b000`, 4,096 bytes each. These extend the selected ROM evidence; they do not constitute a full firmware/recovery backup. Hashes are included in `private/battery-estimator-analysis.json`.

The installed battery object's sensor pointer at `+0x64` leads to a sensor method table at `0x4bd28`. Its conversion method is ROM `0x1b3ac`. This method reads the configuration at `0x2005c8`: upper raw threshold 1920, lower threshold 1520 and full-scale 100. The exact mapping is:

```text
percent = clamp(floor((raw_sensor_average - 1520) / 4), 0, 100)
```

ROM `0x2a2e` maintains an eight-sample rolling average; `0x2aae` passes this average into the conversion and stores the result at battery object `+0x14`. The final percentage conversion has no charging-state, current or temperature argument. This is a simple sensor-to-percentage estimate, not evidence of coulomb counting. The upstream ADC calibration and electrical measurement point have not been fully characterized, so raw units must not be labeled as volts.

`research/analyze_battery_estimator.py` executes the actual captured conversion routine offline under Unicorn. All 4,096 tested raw inputs match the formula, including all 12 recorded sensor/percentage pairs from this investigation. No device access occurs in that analysis. It reproduces 1745 -> 56%, 1785 -> 66%, 1857 -> 84% and 1784 -> 66% exactly.

The controlled observations support charging bias in the estimate. The initial large jump also involved turning the backlight off, so it cannot isolate the charger and lighting effects. Later plug/unplug observations held the backlight state unchanged, but settling time still varied. These observations do not measure battery capacity, load current or remaining runtime. Fn+B and the reader share the same estimate; their agreement is not independent calibration. Initial continuous discharge/charging sessions were stopped at the owner's request. Later readings were single requested samples, with no background polling restarted. Corrections to lighting conditions and the individual readings are recorded in `private/discharge-tests/manual-observations.jsonl`.

The connected Apple device was inspected through read-only macOS Bluetooth/IORegistry properties. It identifies as **Magic Trackpad 2**, vendor `0x004c`, product `0x0265`, firmware **3.1.8**, with **73%** reported through `AppleDeviceManagementHIDEventService`. Its service summary is **HID ACL**, as is the K2's: this is evidence of Bluetooth Classic HID on the current connection, not BLE. The identity does not establish its purchase/manufacture date or exact cosmetic revision. Its working Apple battery-service publication illustrates a native macOS integration that the K2 currently lacks; it does not authorize copying Apple's identity/protocol.

Apple's [Lightning Trackpad specifications](https://support.apple.com/en-za/111884) rate battery life at about a month or more. Three months may be an individual usage outcome but is not the published baseline. A low-power connected keyboard is feasible in principle without BLE: the existing CYW20730 supports connected sniff/subrating. Neither a Bluetooth version label nor a change to BLE alone guarantees long runtime.

The newly captured inactivity call chain resolves `0x20716e -> application method +0x18 -> 0x14716 -> method +0x140 -> 0x152fa`. The latter enters a connection state transition and invokes lower-layer methods/timers. This extends the trace; it is not a measurement of radio state or board current. The disabled-auto-sleep branch bypasses this path, but has not been shown to disable all lower-level sniff power saving.

The published **V1 RGB 1.62** main-controller image was also checked offline. It writes mode 2 to PMU register `0x40032040` before WFI at `0x25a` and `0xb78`. This confirms that the newer reference contains deep-sleep mechanisms too. It does not establish the installed Sonix version, whether those branches run while connected or how to preserve the first key across a wake handshake.

Runtime budgets, using an explicitly hypothetical healthy 4,000 mAh usable capacity, are:

| Calendar runtime | Maximum whole-device average current |
|---|---:|
| 20 days | 8.33 mA |
| 30 days | 5.56 mA |
| 60 days | 2.78 mA |
| 90 days | 1.85 mA |

Actual usable capacity and conversion losses reduce those allowances. At the same capacity, moving from 3-4 days to 20-30 days requires roughly a 5-10x reduction in average draw. A battery-only change would require a comparable capacity multiplier unless the existing cell has lost substantial capacity. Neither current nor usable capacity has been measured. Keychron's [K2 specifications](https://www.keychron.com/products/keychron-k2-wireless-mechanical-keyboard-nordic-layout?page=7) list 4,000 mAh and up to 240 hours of typing with lights off; this is not a 240-hour guarantee of this original unit's present always-awake operation.

Historical option list, superseded by the firmware-only scope and findings above:

1. Preserve the case, plate, switches and keycaps. Identify exact PCB and cell dimensions/health, then measure battery-side average current during typing, connected idle and the existing disconnected sleep state. A USB charging-input meter cannot by itself establish battery discharge current. Read-only captures cannot replace these measurements.
2. If the existing board is recoverable and its idle current is fixable, develop a policy that retains the Bluetooth connection, negotiates appropriate sniff/subrating and sleeps the scanning controller between events. The owner permits consuming the initial wake key; subsequent input must work promptly. A longer disconnect timeout does not implement this. The current binary-only firmware and incomplete main-controller capture make effort and outcome uncertain.
3. If that route is poor, use an nRF52840-class BLE module with ZMK on a custom adapter or replacement PCB designed around the original mechanical geometry. [ZMK's idle state](https://zmk.dev/docs/features/low-power-states) expressly retains Bluetooth and immediate key response; its deep-sleep state disconnects and would not be the ordinary idle policy. Support standard battery reporting, and validate native display and Mac sleep/wake on this Mac. ZMK documents a [macOS battery-notification wake issue](https://zmk.dev/docs/config/battery), so a low-rate/no-redundant-event policy needs testing too.
4. Reusing the switch matrix requires electrically isolating old controllers and avoiding board leakage. The [SonixQMK K2 V2 ANSI reference](https://github.com/SonixQMK/qmk_firmware/blob/sn32_develop/keyboards/keychron/k2/rgb/v2/ansi/keyboard.json) maps six rows and sixteen columns, implying 22 matrix signals before extra functions. This is a V2 reference, not a verified pin map for this unit. A small controller module is not automatically compatible. A replacement PCB must match switch/stabilizer positions, plate clearances, mount heights, USB/switch cutouts and antenna clearance. No donor K2 Pro/Max board or commercial PCB has been established as a drop-in replacement. The [SonixQMK FAQ](https://sonixqmk.github.io/SonixDocs/faq/) currently says Bluetooth support is unavailable/WIP; merely flashing that port is not the desired upgrade.
5. Keep hidden wireless charging as a fallback. A Qi receiver would feed the properly designed 5 V charging/power input with source isolation, not the battery directly. Existing charger limits determine actual cell charge rate; fast charging is unnecessary to offset keyboard power. The [example Adafruit transmitter](https://www.adafruit.com/product/2162) specifies 2-8 mm coil separation, so the residual tabletop, case, feet and internal clearance all count. Alignment, metal clearance, ferrite backing and heat need a physical layout. Published [K2 construction](https://www.keychron.com/products/keychron-k2-wireless-mechanical-keyboard?variant=40290116730969) lists an ABS bottom with optional aluminum frame; a metal bottom must not be assumed for this unit. A coil receiver modification may not require replacing the whole bottom. Perpetual powered operation also requires checking the charging/load-sharing implementation, rather than assuming continuous high-rate cell charging is appropriate.

The preferred engineering target is 20-30 calendar days with immediate response, first checking whether the existing electronics can meet it. A custom low-power replacement controller is a credible fallback for preserving the keyboard's physical character. No month-scale result, complete flashable fix, exact fitting PCB or native macOS publication has yet been demonstrated.

## Revised conclusion after checking official support and community reports

The observed zero-versus-58 mismatch is a firmware-level reporting inconsistency in this installed 20191025 build. It is not proof that missing native macOS display is caused by that inconsistency, that Keychron considers the behavior a supported feature's defect, or that newer compatible firmware retains it. The emulator demonstrates one candidate repair of the query buffer; it does not establish that a custom firmware is necessary.

The user requested checking existing work before modifying anything. The source review found:

- [Keychron's own Mac battery support article](https://help-center.keychron.com/en-us/article/12144971522071-can-mac-detect-the-battery-percentage-of-the-keyboard-if-not-is-there-) says Mac cannot detect the keyboard percentage and directs users to Fn+B, noting its inaccuracy. The article is generic; it must not be generalized to every newer Keychron family.
- [A K2 owner asks for the same macOS percentage feature](https://www.reddit.com/r/Keychron/comments/14oi40c/is_it_possible_to_display_battery_percentage/), explicitly comparing absent keyboard reporting with working AirPods/mouse reporting.
- [Another thread includes K2, K7 and K12 owners requesting OS battery reporting](https://www.reddit.com/r/Keychron/comments/1b1zv2q/battery_reporting/). Replies include speculation; they are user reports, not proof of a technical root cause.
- [A community original-K2 app](https://github.com/wretchedworm/keychron-k2-battery-sleep) documents battery percentage and warnings without replacement firmware, verified on one non-backlit K2-M1 with Bluetooth firmware 1.08 (20210820). That is evidence for revision-dependent working software access, not native Bluetooth UI support or compatibility with this RGB unit.
- [Another battery utility](https://github.com/rxrdev/keychron-battery-level) explicitly requires a battery value that macOS already has. A menu-bar utility's existence does not establish that it can recover this unit's missing value or publish it natively.

An additional official V1 US firmware page was discovered: [K2 V1 firmware history](https://www.keychron.com/pages/firmware-v2-3-for-k2-keyboards). It lists **1.62**, so the previously downloaded **1.27 must not be described as the latest V1 firmware**. The 1.62 notes concern updater success messages, function/media keys and backlight locking; the history also documents Fn+B indication and a charging-indicator fix. The inspected notes do not claim native macOS battery-percentage support. Main-controller and Bluetooth firmware are separate version streams.

The V1 RGB 1.62 package has now been downloaded and its embedded HEX extracted for offline comparison, without executing it. Its compatibility with the user's physical revision and its effect on this battery report remain unverified. The earlier Sonix power-path analysis below applies to the explicitly named **1.27 reference**, not automatically to 1.62 or the installed main-controller image.

This earlier stock-update recommendation is superseded: the owner's goal is custom firmware modification on the existing electronics. Hardware identity and published images remain necessary analysis inputs, not a goal to install a stock update. No update is authorized or applied.

## What is available locally

The device captures are not a complete firmware or recovery backup:

- Bluetooth RAM: `0x200000..0x210000`, 65,536 bytes. This contains executing custom code and runtime state. It is a sequential snapshot, not an atomic image.
- Selected Bluetooth ROM: `0x1000..0x3000`, 8,192 bytes; additional method tables at `0x4b000..0x4d000`, 8,192 bytes.
- No complete persistent EEPROM/flash image, complete built-in ROM image, or installed Sonix keyboard-controller image has been captured.

Official downloads are stored under `private/vendor/`. Their original URLs and SHA-256 hashes are recorded in `downloads.json`. Raw files remain private and ignored by version control. Only archive parsing and disassembly were performed; no downloaded executable was launched.

| Official reference | Retrieved and extracted | Compatibility status |
|---|---|---|
| Original K2 V1 RGB US 1.62 | Windows updater and embedded Sonix HEX, downloaded after finding the fuller official firmware history | Newer published V1 reference; physical-revision and installed-image match remain unverified |
| Original K2 RGB 1.27 | Windows updater, with embedded Sonix Intel HEX payload: 55,572 bytes at address zero plus a four-byte marker at `0xfffc` | Original RGB reference; exact match to this keyboard's installed main-controller firmware remains unverified |
| K2 V2 RGB ANSI 1.04 | Windows updater archive and embedded Sonix Intel HEX payload: 58,608 bytes at address zero plus marker | V2 reference only; hardware revision has not been established |
| K2 Bluetooth 1.09 | Standalone Intel HEX file; parsed 51 configuration records and reconstructed 17,913 bytes of RAM initialization/patch records | Official link specifically labels this file for the non-backlit ANSI model; not verified for the user's RGB keyboard |
| Official OTA tool archive | Archived updater, settings and vendor sample data | Reference only; sample data is not a backup of this keyboard |

The Bluetooth 1.09 application includes build date `20211217`. The installed Bluetooth build identifies as `20191025`, with version byte `0x05`. Published latest firmware is therefore a different reference, not a byte-exact backup of what is running now. These packages contain compiled firmware, not source code; they also do not supply all built-in chip ROM.

## Standard battery report versus measured battery state

The saved RAM snapshot contains a battery-monitor object at `0x20c9d4` with method table `0x4c2f4`. Its relevant fields are:

| Offset | Meaning established by disassembly | Snapshot value |
|---|---|---|
| `+0x04` | Standard battery report ID | 3 |
| `+0x05` | Cached percentage returned in that report | 0 |
| `+0x14` | Measured percentage used by Fn+B | 58 |

Selected built-in ROM establishes the paths:

- `0x290a`: checks input-report type 1 and the configured report ID, then returns the report buffer at object `+4`. Its second byte is the cached value at `+5`.
- `0x2aae`: calls the sensor/conversion method and stores the resulting percentage at `+0x14`.
- `0x28e2`: compares measured `+0x14` against cached `+5`; it updates the cache and sends a report only when the measured value is lower. A cache starting at zero will not be corrected upward by this path.
- `0x28a8`: an initialization path samples and converts the battery and seeds the cached value from the measured value. Why the active application did not leave the two fields synchronized has not yet been established.
- `0x2924`: sends a report on connection only when a configuration flag is enabled. That flag is zero in the saved snapshot.
- Installed custom function `0x2082c2` reads `+0x14` and compares it with 70 and 30 for Fn+B's indicator.

This explains the observed mismatch at the buffer level: the standard reply exposes a different, stale field. A firmware change could potentially synchronize that buffer after measurement or refresh it when handling a battery query. Neither change has been applied or tested. Whether macOS would accept the corrected report for native Bluetooth UI remains unverified.

An attempted additional live recheck after the offline analysis was denied by macOS (`0xe00002e2`) during the identification request, before a new snapshot was created. The field comparison above is from the earlier successful capture, supported by the earlier live standard-report 0% and guarded internal-state 58% reads. It must not be described as a new live measurement.

## Candidate battery fix and offline validation

An offline, firmware-specific query-handler candidate is in `research/battery_get_report_candidate.S`. It is 48 bytes including literals. It is an isolated function, not a complete firmware image. The experiment loads it into an emulated ARM Cortex-M3 alongside the captured ROM and RAM; it never opens a device or changes macOS state.

The candidate refreshes the cached report value from the measured `+0x14` field when the request is for the configured battery input report. It validates 0-100 and delegates the existing report formatting to the original ROM routine. It leaves unrelated report requests untouched. A real integration would need a firmware-loaded RAM method-table override; the original function is in immutable chip ROM. The emulation address is not an approved physical memory allocation for deployment.

`research/test_battery_patch.py` passed 22 offline cases:

- Actual captured getter with measured=58, cached=0 returns `[3,0]`.
- Candidate getter with the same inputs returns `[3,58]`, preserving the original eight-bit payload size.
- Zero, 1%, 20%, 58%, 90% and 100%, charging increases, depletion, invalid values and unrelated report types/IDs behave as expected.
- Register/stack preservation and adjacent output-length memory are checked.
- Emulation of the actual notification routine reproduces the second bug: it suppresses an upward change such as 58 to 90. An emulator-only change from skip-if-greater-or-equal to skip-if-equal sends upward and downward changes and suppresses duplicates. This ROM comparison cannot be changed in place on the physical chip; a real implementation needs an equivalent RAM override and validity checks.

A complete firmware fix should therefore:

1. Refresh the cache for battery queries.
2. Seed the cache after the first valid sample and publish one correct report when a connection becomes ready, instead of depending on a pre-existing cache or the currently disabled connect-report flag.
3. Notify on percentage changes in either direction, with a bounded rate and no repeated unchanged reports. Reuse the existing sensor sampling; do not force extra high-frequency ADC reads or host polling.

The query behavior is demonstrated in emulation. Boot integration, notifications on actual hardware, charging behavior, reconnects and battery accuracy over a discharge cycle are not yet verified. No patch has been installed in RAM, flashed, or packaged as a deployable image.

## Native macOS battery display: separate compatibility question

The host currently runs macOS 27.0 (26A428). Its connected K2 is a Bluetooth Classic HID device with the generic `IOHIDUserDevice` registry class. The currently observed registry entry has neither a `BD_ADDR` property nor a `BatteryPercent` property. Device identifiers were omitted from saved host findings.

Static inspection of the installed `/usr/sbin/bluetoothd` found a real HID battery-reading path, so it would be inaccurate to claim that macOS can only display BLE batteries. In this build:

- The caller at `0x10052373c` enumerates `IOAppleBluetoothHIDDriver`, `AppleDeviceManagementHIDEventService`, and `IOBluetoothHIDDriver`.
- The reader at `0x100524734` matches `BD_ADDR`, obtains `BatteryPercent` using `IORegistryEntryCreateCFProperty`, and returns that number.
- The fallback at `0x100524ab0` calls `IOHIDEventSystemClientCreate` and `IOHIDEventSystemClientCopyServices`, then `IOHIDServiceClientCopyProperty`. It matches `SerialNumber` after normalizing hyphens to colons and reads `BatteryCapacity`. This is a HID event-service path, distinct from the preceding `BatteryPercent` registry path. It is not a full audit of every Bluetooth battery path.
- That fallback is conditional: the caller invokes a device/feature gate at `0x100520f50`. Its strings refer to `GameControllerBlockListRemoval`, `HID/EnableGamepads`, and MFi gamepad authentication, and it checks device capability bits. A read-only query of the installed feature configuration returned false for `BluetoothFeatures.GameControllerBlockListRemoval`. This does not establish the complete gate result for the K2: its internal daemon capability bits were not read. The path cannot be assumed to apply to arbitrary keyboards just because its property can be identified.
- The separately inspected `IOHIDPowerSource` matching rule is for Apple power-pack usage `0xff00/0x58`, not the K2's existing generic battery report. It must not be repurposed by blindly changing the K2 descriptor.

Apple's public generic HID event-driver source does not provide an evident battery-strength translation path for this descriptor. This source observation and the local driver inspection do not prove that all macOS versions lack a compatible route.

Consequences:

- The existing Mac reader already works via diagnostic reads on the previously authorized host; a corrected standard report would let software query the same estimate through normal HID.
- Native Bluetooth UI is not established by the successful ARM emulation. A firmware-only correction may still leave macOS without the HID-service property publication it expects.
- A native solution needs either a verified descriptor/protocol that binds to a compatible macOS driver, or a separately validated host integration that publishes the right battery information. Merely setting `BatteryPercent` on a generic HID entry is not shown to satisfy the inspected class/address matching. The HID-service fallback offers a more specific route through `BatteryCapacity`. No property injection, daemon patch, system extension or security-setting change was attempted.
- The current Bluetooth Classic chip cannot gain a BLE Battery Service solely by replacing its firmware. A BLE controller conversion remains a cleaner alternative if native battery display proves a hard requirement that cannot be met by the existing hardware's supported protocols.

Reproduction tools: `research/inspect_macos_battery.py` performs static inspection only. Findings and disassembly are under `private/apple/`. Research dependency versions are pinned in `research/requirements.txt`. Current-build binary offsets are evidence for this OS build, not portable API addresses.

### A concrete Mac-side bridge to test first

A read-only live probe using the same HID event-service APIs found exactly one matching K2 service: it has a serial identifier and lacks `BatteryCapacity`. Its registry event driver is `AppleHIDKeyboardEventDriver`. This is positive evidence that an appropriate HID service exists, although the daemon's gamepad-related gate means the fallback is not yet established as eligible for this keyboard. The probe is `research/probe_native_battery.c`; it has no property setters or device-report functions.

Apple's HID service-client interface exposes a property setter, implemented via `IOHIDServiceClientSetProperty`. A small Mac helper is therefore a concrete native-display experiment to consider before flashing; it is not an established solution. Its steps and acceptance gates would be:

1. Match only this keyboard's live HID service and validated identity.
2. Read its measured percentage using the existing guarded diagnostic reader.
3. Attempt to publish that valid reading as `BatteryCapacity` on the matching HID event service, using the operating system's service-property interface.
4. Read it back through the same service API and verify whether native Bluetooth UI obtains and refreshes the reading. Establish that the daemon actually enables its fallback for this keyboard; a gamepad-only path would make the approach insufficient. Exercise reconnects and stale-value behavior explicitly. A successful setter alone is not success.
5. Remove or restore the property when the helper exits where supported, and never publish stale data as a fresh measurement. Bound sampling and remain quiet while the keyboard is disconnected/asleep so the bridge does not defeat standby power saving.

This is a proposed reversible host-side experiment. It has not been executed. The service may reject the write, require extra permission, ignore the key for publication, or the daemon may not enable/refresh its fallback for this device. This OS-build-dependent mechanism is not a promised stable cross-version API. No kernel or daemon patch, alternate device identity, feature-flag modification, SIP change or hardware change is part of the proposed test. If the gate excludes the K2, publishing that property alone does not solve native display and should not be represented as such. Native percentage and automatic low-battery notifications must be verified separately; helper notifications remain an optional fallback.

## Power-management findings and open work

The installed custom code implements a 600-second inactivity countdown:

- `0x206c16` reloads the countdown to 600 and starts a 1,000 ms timer.
- `0x207132` checks the auto-sleep flag at application object `+0x12c`, decrements the countdown and takes the sleep path when it expires. A disabled flag (`0xaa`) stops this timer path.
- The shortcut handlers at `0x206d76` and `0x206d90` save disabled/enabled values through the existing configuration mechanism. They have only been inspected, not invoked.

This is consistent with the owner's reported change from long battery life with auto-sleep to several days with it disabled. It does not identify the current consumed by the radio, scanning controller, regulator or battery leakage. The backlight has been off since purchase, according to the owner.

The later firmware-only section at the top now demonstrates the scanner idle-policy separation offline. No hardware power saving or faster-reconnection fix has been demonstrated. Physical current measurements would eventually quantify the saving; they are not a prerequisite to continuing the authorized offline firmware analysis. The owner reports adequate battery health and requests retaining the current electronics for this stage.

## Standby changes: what is supported and what needs proof

The disabled-auto-sleep branch stops the 600-second timer; it does not directly rewrite the radio's sniff-mode settings. Therefore we have not established that disabling auto-sleep also disables the chip's lower-level connected power saving. A patch that only enables sniff mode could be redundant.

The CYW20730 manufacturer datasheet explicitly supports Bluetooth Classic connected sniff mode, plus idle, sleep and HIDOFF. Its chip-level typical current table gives 750 microamps at a 60 ms sniff interval, 500 microamps at 100 ms, and 125 microamps at 495 ms. These are chip conditions, not measured keyboard currents, and must not be used as a whole-keyboard runtime prediction. Longer intervals also trade response latency for power. The Mac's installed Bluetooth daemon contains sniff-mode support; actual accepted link parameters remain unobserved.

The downloaded original K2 RGB 1.27 Sonix image also contains existing deep-sleep code:

- `0x25a` and `0xc0c` contain WFI instructions.
- Immediately before those instructions, it writes mode 2 to `PMU_CTRL` at `0x40032040`.
- The Sonix manufacturer documentation defines mode 2 as deep sleep, with GPIO wake capability. Thus replacing the controller is not justified merely by an assumption that it lacks sleep support.
- These are observations from the published image, not proof of which image is installed or which branches are reached in current wireless standby.

The intended power change would be a staged policy, implemented only after its existing transitions are mapped and currents measured:

1. Retain the Bluetooth connection during ordinary idle, using accepted sniff/subrating parameters. The earlier 60-100 ms candidates are superseded by reviewing Apple's current 15 ms base-interval/subrating guidance above and observing actual negotiation; no interval is a validated setting for this unit yet.
2. Keep the key-scanning controller asleep between necessary events, with matrix/GPIO wake and proper handling of held keys. The initial wake key may be consumed under the owner's clarified requirement; subsequent typing must work promptly. Preserve wake/handshake compatibility between the Sonix and Bluetooth processors. Avoid periodic polling that defeats that state.
3. Separate that connected-idle policy from deep disconnect/HIDOFF. Optionally reserve deep disconnect for long unattended periods; simply changing ten minutes to a longer timeout does not reduce connected current or fix reconnection latency.
4. Rate-limit battery and housekeeping traffic so battery reporting does not undo the power savings.

Connected sniff is a standard Bluetooth Classic mechanism and is plausible with this Mac. The resulting keyboard current, negotiated timing, first-key reliability and total runtime have not been demonstrated. If the radio is already efficient but the scanning controller remains active, a Bluetooth-only patch will not solve the dominant drain; the main-controller firmware would also need changes. If both are already sleeping efficiently, battery capacity and board-level leakage become the next measurements.

## Decision before any hardware change

| Change | Present evidence | Remaining acceptance gate |
|---|---|---|
| Battery query cache refresh | Demonstrated using captured ROM in ARM emulation | Firmware-matched integration and a live standard-report read |
| Correct notifications, including charging and reconnect | Bidirectional comparison behavior demonstrated offline; connection/report policy specified | Live event delivery, rate limiting and reconnect/charging tests |
| Native macOS Bluetooth percentage | Native `BatteryCapacity` fallback identified; live read-only probe finds matching K2 service with the property absent | Test a Mac helper's property publication and actual native UI refresh before flashing anything |
| Lower-power standby without routine disconnect | Both processors have relevant low-power capabilities; existing timer traced | Measure current/link mode and verify first-key behavior before and after |

Before constructing a flashable candidate, obtain a complete compatible persistent image/recovery route and confirm the physical hardware revision. The downloaded non-backlit 1.09 image is not a safe substitute for the installed RGB firmware. Hardware replacement is not presently required by the evidence.

## Official sources

- [Original K2 firmware and RGB 1.27 link](https://www.keychron.com/pages/firmware-for-k2-keyboards)
- [K2 V2 firmware and compatibility instructions](https://www.keychron.com/pages/firmware-for-k2-version-2)
- [K2 Bluetooth firmware landing page](https://www.keychron.com/pages/k2-bluetooth-firmware)
- [Bluetooth downloads and non-backlit HEX label](https://www.keychron.com/pages/bluetooth-firmware-for-k2-windows-version-ansi-us-layout)
- [Infineon AN214821: SETUP_READ/READ protocol](https://www.infineon.com/assets/row/public/documents/30/42/infineon-an214821-upgrading-human-interface-device-firmware-example-protocol-commands-and-scripts-applicationnotes-en.pdf)
- [CYW20730 manufacturer datasheet, power management and current table](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/752/CYW20730_RevJ_4-25-17.pdf)
- [Sonix SN32F240B manufacturer documentation](https://www.sonix.com.tw/webapi/fl219873/SN32F248B_V2.4_EN.pdf)
- [Apple generic HID event-driver source](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDFamily/IOHIDEventDriver.cpp)
- [Apple HID service-client property interface](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/HID/Headers/HIDServiceClient.h)
- [Bluetooth Core: Link Manager Protocol, including sniff negotiation](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/br-edr-controller/link-manager-protocol-specification.html)
