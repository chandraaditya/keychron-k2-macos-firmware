# Keychron K2 (V2) on macOS: battery, F-row and fast reconnect

Firmware patches and tooling for the Bluetooth radio of an original Keychron K2 V2
(Cypress/Infineon CYW20730 radio with a 24C512 EEPROM, Sonix scanner MCU). Built and
tested on one keyboard against macOS 27.2.

> **Use at your own risk.** This rewrites keyboard firmware. A mistake, a different board
> revision or bad luck can leave the Bluetooth radio unbootable, and the only fix then is an
> external EEPROM programmer. Nothing here is supported by Keychron, Cypress/Infineon or
> Apple. You are responsible for your hardware.

Not affiliated with or endorsed by Keychron. "Keychron" and "K2" are used only to say
which keyboard this is for.

## What it does (radio build A94)

- **Battery level in macOS.** The battery shows in the Batteries widget and the Bluetooth
  menu like an Apple keyboard.
- **F-row and media keys.** macOS reads a proper function-key map, so F1–F4 and F7–F12 do
  their media actions, and Fn + F-key sends the plain F-key.
- **Fast connect.** The keyboard reconnects in about a second after power-on. Before, it
  took 10+ seconds, plus another 5–6 seconds before typing worked. macOS sends a
  connection-interval request at every connect, which the stock firmware rejected, so macOS
  kept retrying it for about 9 seconds and held up everything else.
- **Safe-boot fallback.** Every boot starts as a trial, and the original firmware stays in
  a second EEPROM slot. The new firmware marks itself bootable again only after the Mac has
  connected and read its key map. If it breaks before that, the next power-on falls back to
  the original firmware automatically.
  - Catch: a flat battery can also trigger that fallback. The radio browns out and
    reboots, and one boot dies before the Mac connects.
  - `--reactivate` restores A94 after that.
  - `--make-default` stops it for good. It points the backup boot header at A94 too, at
    the price of losing the automatic fallback.
    [Details](firmware/A94-REARM-TRIAL.md#making-a94-the-default-installed-2026-11-05).

The radio presents itself to macOS as an Apple keyboard. That is how the native battery
and key-map features get enabled.

Also included: a scanner (Sonix) patch, "CPU-idle A", that lets the scanner's CPU sleep
between scan interrupts. Its power saving is unmeasured.

## About the battery percentage

**The battery reading is an estimate, and not an accurate one.** The K2's board has no
fuel-gauge chip, so the keyboard can only guess the charge from the battery voltage. (Two
battery wires are not the limit: Apple's batteries also have two, but their boards count
the current in and out.) Battery voltage sags under load, recovers at rest, and is nearly
flat across the middle of the discharge curve. Expect the percentage to jump around, read
high or low, and drop quickly near the end. Use it as a rough indicator only.

## This is not a one-click installer

Everything here was built for one specific keyboard, and the safety checks are pinned to it:

- The installers refuse to run unless the keyboard's EEPROM, RAM and ROM match exact
  hashes from that keyboard's own backups. Those backups live in `private/`, which is not
  published because it contains Bluetooth pairing keys.
- The build scripts expect the stock firmware images in `private/`. They are not published
  because they are Keychron's and Cypress's code.
- Several emulator tests also read those private dumps.

To use this on your own K2 you would need to:

1. back up your own EEPROM over Bluetooth with the read-only tools;
2. check that your firmware matches (same build date, same ROM);
3. rebuild the candidate images against your backups;
4. re-pin the installers to your hashes.

That needs comfort with ARM Thumb assembly, Python and HID. Read
[the updater protocol notes](research/radio-updater-protocol.md) and
[the recovery review](research/physical-eeprom-and-recovery-review.md) first.

## Where things are

| Path | What |
|---|---|
| `firmware/*.S` | Radio patch components (battery, keyhole, key map, Fn, C6 ack, re-arm) and the scanner CPU-idle patch |
| `firmware/build_radio_*_candidate.py` | Build each radio version from the stock image |
| `firmware/A88…A94-*.md` | One write-up per radio build: what changed, tests, install notes, hardware results |
| `firmware/PERMANENT-BOOT-DESIGN.md` | How the trial boot and self re-arm work |
| `installers/` | Guarded Bluetooth updater for the radio, Sonix USB installer, read-only probes, tests |
| `research/` | Reverse-engineering notes, Unicorn-based emulator tests, macOS-side probes |
| `artifacts/` | Result and verification records from each step (no keys, no firmware) |
| `FIRMWARE-ANALYSIS.md` | The original firmware analysis |

The emulator tests use Python 3 with `unicorn`, `capstone` and `pyelftools`, plus Xcode command-line tools for the ARM assembler
(see `research/requirements.txt`).

## Status

- A94 is the only boot target on the author's keyboard (`--make-default`, 2026-11-05).
  Battery, F-row, media keys and Fn work, it survives power-off and flat batteries, and
  this keyboard no longer falls back to the original firmware automatically.
- Battery life: the original pain was about 3–4 days per charge. With the scanner idle patch
  it now looks like about a week, going by the estimate described above. Work toward
  multi-week battery life is next.

## License

MIT. See [LICENSE](LICENSE). It covers the code and documents in this repository. It does
not cover Keychron's, Cypress/Infineon's or Apple's firmware and software, none of which is
included.
