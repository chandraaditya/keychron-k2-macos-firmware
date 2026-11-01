# K2 V2 RGB CPU-idle candidate A

> Historical snapshot from October 2026. For the current state see [the main README](../README.md).

The owner's requested initial release now also has a separately built Bluetooth battery component. See [INITIAL-RELEASE.md](INITIAL-RELEASE.md) for current compatibility, backup, two-processor flashing and recovery status. This page describes the scanner-only A image.

Built offline against Keychron's published V2 RGB 1.13 image. **Not cleared for flashing. No keyboard firmware or settings have been changed.** Two rear height settings support the owner's identification as V2; the installed Sonix image and a board-specific recovery route remain unverified.

This first experiment keeps the radio connected under the existing disabled-auto-sleep policy and lets the Sonix CPU enter mode 4 between its existing interrupts. It leaves scan/PWM timing, SPI, GPIO, clocks, watchdog handling and the original sleep/shutdown handler intact. It does not shut down scanning or change the Bluetooth firmware. There is no new inactivity timer.

The intended benefit is reduced CPU busy-loop activity without the scan-stop/receiver-start deadline of the more aggressive prototype. Actual savings depend on time spent in foreground work and interrupts and on other board loads. No current or runtime result exists; this does not establish 20–30 days of battery life. Native macOS battery reporting and away/return reconnect speed remain separate work.

## Exact change

- Reference SHA-256: `256b602f7661c924c614a622f29add82e7acde51af93a7c0afbac17ffaf9ad54`.
- Replace the wireless main-loop call at `0x0798` with a call to the 212-byte wrapper at `0xd800`.
- Call original handler `0x0194` first with its input registers preserved and stack aligned. Keep its forced shutdown and auto-sleep policy.
- Skip new sleep unless wireless mode, auto-sleep disabled, quiet attention/queue/RX state, interrupts unmasked, ordinary sleep control, retained SPI/scan clocks and IRQs, running scan timer with MR24 interrupt, and PMU zero.
- Write PMU mode 4, execute DSB/WFI, restore saved PMU. The wrapper's only peripheral writes are those two PMU writes. Its extra stack use is 24 bytes, including while the original handler runs.
- Preserve all other image bytes, including vectors, original handler, persistent data `0x7000..0xa3ff`, and footer. Inverse patch reproduces the reference byte for byte.

The stock CT16B1 timer uses match-stop and is rearmed by its ISR; it is not a free-running timer. The guard deliberately accepts that stock configuration. The code leaves IRQs enabled and makes no claim that SysTick alone bounds sleep duration. A transfer arriving after a guard is checked can defer foreground work until the next existing interrupt; retained reception and timer operation need physical validation.

## Build and validation

From the project root, with Xcode command-line tools and the versions in `research/requirements.txt` available:

```sh
build/analysis-env/bin/python firmware/build_candidate.py
build/analysis-env/bin/python firmware/test_candidate.py
```

Outputs are under `artifacts/k2-v2-rgb-cpu-idle-a/`: raw `candidate.bin`, copied assembly source, instruction listing, hash manifest and test report. No updater, installer or flashing script is included. The build rejects any different reference image and unresolved assembler relocations.

Fourteen test methods and twenty guard subcases pass. Checks cover emitted branch targets, ABI forwarding and stack restoration, exact byte changes, repeatable output, rejecting a wrong reference, all skip guards, original enabled/disabled countdown behavior, original forced-sleep entry, PMU restoration and retained pending work after a modeled wake. Tests run the actual original handler in selected cases; isolation cases mock it. WFI is intercepted and an immediate wake is modeled. This is not an electrical interrupt, silicon, power, bootloader or complete hardware simulator.

An independent `gpt-6-astra` review found no blocking defect for offline packaging. It checked the emitted bytes, branches, literal loads, call order, stack/register handling and PMU restoration. Its traced/replayed flash-write paths end at or below `0xa3ff` in normal configuration operations; an existing zero-count USB corner case reaches `0xd7bf`, leaving 64 bytes before the stub. This is bounded code-path evidence, not a whole-program proof. The review record is `artifacts/k2-v2-rgb-cpu-idle-a/astra-review.json`; it explicitly withholds hardware/flash clearance.

## Before a hardware trial

The candidate is worth evaluating as the first power experiment once the hardware and recovery gates are resolved. It is not yet an approved image for this keyboard. Required evidence is a compatible physical board/layout identification, verification of installed scanner firmware or equivalence, a recoverable original configuration/image or established manufacturer recovery route, and confirmation of image-format/integrity requirements. Boot-ROM documentation alone is not a tested recovery method on this board. No code-protection change or old deprecated Sonix flasher is part of this package.

After an explicitly authorized flash, acceptance would require normal typing and releases, sleep/wake, Caps Lock output, low-battery behavior, USB/charging/mode switching, pairing persistence and a test beyond the original inactivity timeout. Compare idle current with the original image under matched conditions before making a runtime claim. A failed power result would direct work toward deeper scan idle and/or the Bluetooth power path; it would not establish that replacing the keyboard is necessary.
