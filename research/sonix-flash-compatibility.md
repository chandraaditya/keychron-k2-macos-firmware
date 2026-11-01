# Original K2 Sonix compatibility, recovery, and flashing assessment

2026-10-27. Astra consultation. Source inspection, downloaded-file analysis and comparison with the parent's passive USB registry capture only. No USB requests, flasher installation/execution, bootloader entry, resets, protection changes, or device writes were performed by this investigation.

## Decision

A technically coherent flashing route exists for the SN32F248B family, but **this candidate is not yet cleared for this keyboard**. Three uncertainties remain concrete: exact board/application compatibility; accessible and verified hardware boot-ROM recovery; and preservation/acceptance of the installed main-controller settings. Current SonixFlasherC also needs a guard against silently lowering code protection.

The downloaded V2 RGB US 1.13 base is a published reference, not a backup of this keyboard. Its raw application image starts at flash address zero. The `resource-4000` filename means Windows executable resource ID 4000, not flash offset 0x4000. Candidate A is 65,536 bytes, SHA256 `0d5da2541dcc54be0909b6ce9fde79da46a20a45c38aafb3b26e35c7c97e4293`; its full-image 16-bit little-endian word sum is `0x941d`, final word `0xAAAA5555`, and transfer length 1,024 blocks of 64 bytes. These were calculated offline, not checked against a programmed device.

## Compatibility: what the new USB evidence establishes

28 October update: the owner reports the physical marking `RGB Ver 1.2/20200515`. This is a board revision/date code, not a firmware version or proof of product generation. It differs from the `RGB-BC Ver 1.1` recovery-board reference below. No exact published match or pad identification has been established from the text alone; a photograph of this board is still needed before transferring that recovery procedure.

The parent's passive capture records USB 05ac:024f, bcdDevice 0x0104, and report descriptors of 89 and 158 bytes. Comparison against the actual downloaded files gives:

| Published filename | Static VID:PID | Static bcdDevice | Match observed 89-byte / 158-byte descriptors |
|---|---|---|---|
| V1 RGB 1.27 | 05ac:024f | 0x0121 | both exact |
| V1 RGB 1.62 | 05ac:024f | 0x0142 | both exact |
| V2 RGB 1.04 | 0c45:8006 | 0x0104 | first absent; second exact |
| V2 RGB 1.13 | 05ac:024f | 0x0113 | both exact |

The downloadable V2 1.04 first descriptor is only 79 bytes. Its keyboard report format differs: six ordinary key slots, versus the other images' five slots plus a vendor usage byte. Runtime descriptor construction has not been exhaustively excluded, but the static mismatch is sufficient to reject “bcdDevice 1.04 proves we have the downloaded installed image.” A factory 1.04 build distinct from that download is plausible. The version mismatches in V1 filenames reinforce that filename labels are not authoritative firmware identity.

The V1 and V2 descriptor overlap also means the matching descriptors do not distinguish their PCBs. Rear-leg/case details, purchase date and the underside product code support V2 as a hypothesis; they do not determine matrix wiring, switch technology, or MCU package. The original reverse-engineer's [K2 RGB V2 board documentation](https://github.com/dexter93/keychron-k2/tree/8a020f6f0a25e0a8fa816cca5b7eb521b01c3ff1) identifies an HFD2201KBA-marked controller compatible with the SN32F24xB family, rather than requiring a literal Sonix marking.

Keychron's [V2 US page](https://www.keychron.com/pages/firmware-for-k2-version-2) scopes its files to 84-key V2 US and separates RGB from white backlight. Its [V2 ISO page](https://www.keychron.com/pages/firmware-for-keychron-k2-version-2-iso-version) explicitly warns against interchanging mechanical, optical and hot-swappable variants. Therefore, broad Bluetooth-update compatibility claims cannot be transferred to the main Sonix image. No primary source found here establishes universal compatibility of this exact US RGB 1.13 image across all hot-swappable K2 boards. An ISO/JIS, white-only, optical, Pro, Max or V3 board is outside this candidate's established scope.

## Recovery is a separate ROM, not the candidate's application

The [Sonix SN32F240B series manual v2.4](https://www.sonix.com.tw/webapi/fl219873/SN32F248B_V2.4_EN.pdf), memory map and §§14.7–14.10, places the 3 KiB USB boot ROM at 0x1FFF0000–0x1FFF0BFF, separate from user flash 0x00000000–0x0000FFFF. It documents that P2.2/BOOT held low during boot enters that loader. Ordinary application replacement should not overwrite that separate ROM.

[SonixQMK's hardware instructions](https://github.com/SonixQMK/SonixDocs/blob/develop/howto.md) describe BOOT/GND pads, commonly under Keychron spacebars, but explicitly say accessibility varies. Their older generic package-pin instruction must not be applied blindly: Sonix's own manual assigns BOOT to different physical pin numbers in different packages. A user-authored [K2 V2 installation record](https://github.com/rajumakantham/QMK-on-K2V2) identifies an RGB-BC Ver 1.1 board and its spacebar-area pads; that is evidence about that author's board, not confirmation of this one.

For this device, recovery preparation means identifying the actual board marking and BOOT/GND pads, then—only when separately authorized—demonstrating that the hardware entry route enumerates the expected Sonix bootloader without erasing anything. Entering bootloader changes device operation and is not a passive query. Keeping a known compatible factory image is useful, but the published image is not an exact personal backup. Hardware ROM availability makes application failure potentially recoverable; unverified pad access, USB transport, power, protection state and board identity prevent an “unbrickable” claim.

## Current flasher source: useful implementation, important traps

Source reviewed: [SonixFlasherC commit 73f9fab8a82c5c4f91181d276676c8f936726925](https://github.com/SonixQMK/SonixFlasherC/tree/73f9fab8a82c5c4f91181d276676c8f936726925), reporting version 3.0.0. Local source snapshot is under `private/sonix-flash-research/source`. The old Python [sonix-flasher](https://github.com/SonixQMK/sonix-flasher) is archived and warns that it is deprecated and potentially dangerous; its historical tutorials are not a recommendation to install it.

The C implementation supports the SN32F24xB family with bootloader USB ID 0c45:7040 and a 64 KiB profile. It sends 64-byte feature reports on interface 0, report ID 0. The version query identifies the bootloader/chip family and security, **not the installed application revision or exact keyboard PCB**.

The normal flash path calls `device_set_code_security(...CS0)` before programming. It skips this only if already at CS0. The Sonix manual says lowering CS1/CS2 to CS0 first mass-erases user flash. It also explicitly permits writer programming at all three security levels, so that downgrade is a tool choice, not a demonstrated requirement for this task. A future guarded implementation should refuse any security change; successful programming under the actual protection state remains to be verified. Never unlock a protected device in an attempt to obtain a backup: that destroys the contents being sought.

Other source-level limits:

- `--info`, without `--reboot`, sends chip/security and checksum queries only; no erase/program/security command. The default libusb backend may detach a kernel driver and claim interface 0, so it is not equivalent to passive registry inspection.
- No flash-readback/backup command is implemented. Hardware checksum is readable even under protection, but a 16-bit sum is neither a backup nor a collision-resistant firmware identity.
- `--reboot hfd` sends `AA 42 89 5A FF 71 62 CC` and zeros to normal firmware. This matches the downloaded Keychron 1.04 updater configuration and the 1.13 application's reboot matcher. It changes device state. The tool then queries through the same open handle after a delay instead of explicitly reopening the new bootloader identity, so a one-shot normal-mode reboot-and-flash command is not a verified route.
- Firmware preparation opens the file for modification and may pad it in place. The exact 64 KiB candidate needs no padding, but use a dedicated copy and verify its hash after preparation.
- The profile's maximum size is displayed but not enforced before programming. Our candidate independently meets the 64 KiB bound.
- The tool picks a device by VID/PID without a serial/path selection. A future flashing session must positively exclude another matching bootloader device.
- The 24xB path skips the separate erase command, sends program-enable command 05, then the data. It checks the returned final word and 16-bit checksum, followed by another whole-flash checksum. That is useful transfer verification, not byte-for-byte readback.

## Conditional future sequence, not authorization or ready-to-run clearance

1. Establish V2 US ANSI 84-key RGB board and switch variant, and identify its actual recovery pads. Resolve the installed-image discrepancy above. Ideally obtain a non-destructive exact main-flash backup through a separately validated method; none is currently established here.
2. Decide how installed settings will be preserved or deliberately replaced. Candidate A preserves the **reference image's** 0x7000–0xA3FF bytes. Flashing all 64 KiB still replaces this keyboard's settings with those reference bytes. Main-controller settings must not be confused with pairing records on the separate radio.
3. Under separate device-action authorization, enter hardware boot ROM and verify 0c45:7040 and the expected 24xB/64 KiB response. An info-only command in that already-established state is `sonixflasher -v 0c45/7040 --info`, with no `-r`. Record raw protection level/checksum; do not downgrade protection.
4. Use a reviewed guarded flasher that checks exact image hash/size, expected family, unique device, offset zero, and refuses protection changes. The unguarded upstream syntax expressing the intended transfer is `sonixflasher -v 0c45/7040 -f candidate-copy.bin -o 0`. It must **not** be executed as-is before those guards and compatibility/recovery decisions. No jumploader, 0x200 offset, or PE-resource 0x4000 offset applies to this 24xB image.
5. Verify transfer checksums/final word; reboot to application only after success. If the application fails, use the already-demonstrated physical boot-ROM route and the confirmed compatible recovery image. This restores the published application, not necessarily the former personal settings or exact factory build.

## Why no new normal-mode query is cleared yet

The exact 1.13 GET_FEATURE handler at 0x1840 → 0x17B0 returns the existing 64-byte command/reply buffer and marks a protocol event; it is not a fresh version or arbitrary flash-read service. If the prior buffer contains opcode AB, GET also changes the protocol state. Calling it alone does not identify a new firmware version.

Critically, normal-mode command F0 is **not a harmless version request**: dispatcher 0x3E92 selects 0x3F5E, which calls persistent-settings routine 0xD322. F1/F2/F3 are accepted no-op cases here, not established arbitrary memory-read commands.

There are bounded settings-read transactions using a SET_FEATURE request followed by GET_FEATURE replies: byte0=04, byte1=05/10/12/14/16, count in little-endian bytes8–9. The fixed flash bases are respectively 0x9000/0x90C0/0x9340/0x97C0/0x9080, with limits 2/10/20/48/1 blocks. They do not expose arbitrary code or the primary 0x8000 settings block. Adjacent write opcodes 11/13/15/17 immediately modify flash metadata even before bulk data. These are audited **reference-1.13 semantics**, not permission to send frames to the unmatched installed build. A pure GET-only fresh-version or full-backup query has not been established.

Reproducibility: `private/sonix-flash-research/analyze_offline.py` regenerates `offline-analysis.json` from local files and the parent's registry capture. It imports no USB/HID library, opens no device, and only calculates descriptor hashes and theoretical transfer metadata.
