# Captured radio updater: request, response and reset contract

2026-10-28. Astra. Offline review of complete ROM SHA256 `07532fa29dccc635926f3e97a8333d08b9ecb0130221078699a3e98cce5bc1bf` and installed 20191025 RAM/EEPROM code. No device access, update enable, EEPROM writes or launch. This specifies a reviewable implementation; it is not permission to execute it.

## Principal findings

1. SET_FEATURE 70 with an empty payload enables writes **and starts a nominal ten-second inactivity timer whose callback forces a watchdog reboot**. Successful updates refresh it. No disarm command was found. Avoid any approval prompt, long pause or unbounded retry after enable.
2. SET_FEATURE 74 has the expected address/length/data/checksum format. Its return status follows synchronous EEPROM-driver completion. There is no separate GET_FEATURE 70/74 acknowledgment report; both are rejected by the GET handler.
3. GET_FEATURE 72 returns a well-formed, checksummed response even when its low-level EEPROM read fails. The buffer was prefilled with AA. Header/checksum verification alone is therefore insufficient; compare intended data exactly and establish current identity/context using independently meaningful content.
4. Timeout reboot invokes the same reset routine as standard LAUNCH75 with address zero. It is distinct from directly launching code or parsing DS into a live heap. The extension requires a full reset boot, not necessarily physical power removal.

## Exact framing and statuses

All integers are little-endian. The HID report type is Feature (3). The macOS buffer convention already used successfully for reads includes the report ID as byte zero; the internal handler receives the payload after that byte.

| Operation | Complete report buffer | Result |
| --- | --- | --- |
| Enable | `70` only | Successful SET_REPORT acknowledgment; timer starts. No checksum byte. |
| Set up read | `71 + address:u32 + length:u16 + checksum:u8` | Accepted without enable. Refreshes an already-active update timer; does not start one. |
| Read | GET report ID72; expected total response `length+8` | `72 + address:u32 + length:u16 + data[length] + checksum`. Read cursor advances by length. |
| Write | `74 + address:u32 + length:u16 + data[length] + checksum:u8` | Requires enable and nonzero length. Payload length excluding ID must equal `length+7`. Successful write refreshes timer. |

For 71/74, choose checksum so the sum of **all bytes including report ID and checksum** is zero modulo256. The same sum rule applies to72 responses. The EEPROM virtual address is `0xFF000000 + offset`. Reject all other address families in a dedicated EEPROM updater, even though the firmware exposes a wider interface.

The actual installed custom SET dispatcher at2066A4 delegates allowed IDs to ROM2400. Its observed numeric results are0(success),2(invalid report ID or write while disabled),4(invalid parameter/checksum/length/write failure), and15(GET allocation failure). The standard [Bluetooth HID1.1.1 specification](https://www.bluetooth.org/docman/handlers/downloaddoc.ashx?doc_id=309012) defines SET_REPORT acknowledgment as HANDSHAKE and maps those codes to successful, invalid-report-ID, invalid-parameter and fatal. GET_REPORT returns DATA on success or HANDSHAKE on error. The macOS API’s precise mapping of each error to IOReturn has not been measured for writes; retain the raw error and stop on any non-success rather than inventing error-code mappings.

There is no command-specific busy/status poll for70/74 in this implementation. The ordinary HID NOT_READY code exists in the standard, but no return1 path was found in the installed updater dispatch. EEPROM busy handling is synchronous ACK polling inside ROM2C9B2/2C94C. That polling has no visible retry bound. Do not interpret a host timeout as proof the write did not happen. A failed multi-chunk call may already have changed a prefix.

Malformed-checksum74 returns4 without clearing enable. Wrong-length/zero-length74 or low-level write failure returns4 and clears enable. Neither cancels the already-active timer. Nonempty70 also returns4, clears enable and leaves the timer active. A wrong GET72 response-size request clears enable; allocation failure returns15. Unknown report IDs are rejected by the custom dispatcher.

## EEPROM and timer paths

Write adapter272A masks off the address high byte, adds updater-object+0C, and routes according to storage-mode bits[6:4] at205E10. EEPROM mode1 uses I2C2C9B2 with a16-bit address and slave byteA0 below64KiB. Current captured factory construction passes base0 and interval10. Do not assume these properties for an unidentified object or different build.

Enable70 can perform erase operations on another configuration: object base nonzero combined with storage mode4. An explicit base0/EEPROM-mode guard excludes that branch for this keyboard. A raw70 command is not universally harmless.

Timer method2658 calls16896 with interval10. That routine multiplies by80; schedulerBE82 multiplies by40 native half-slot ticks, giving32,000 ticks, nominally ten seconds at3,200Hz. This duration is code-derived, not physically timed. Valid71 and72 refresh only if the timer is already running; enable70 and successful74 start/restart it. Timer callback26A4 enters17600→2C418, writes4 to329000 and3 to329008, then spins. No physical reset was triggered in this investigation.

The same26A4 routine is invoked by standard75 with address0. By contrast, nonzero75 can branch directly to supplied code and is excluded. Reset vector4 contains201; ROM200→280 resets VTOR/SP, disables interrupts, calls1C636→2CFEC to reset phase0, discovers SS and proceeds through the previously established DS-load-before-heap path. No watchdog-cause-dependent bypass was found in that sequence. This supports watchdog reboot as the expected normal activation route. Full hardware reset-domain behavior remains unmeasured; the distinction supported here is reset boot versus hot loading, not a blanket claim that all reset sources are electrically identical.

## Preconditions and staging contract

A dry run should use files only by default. An explicitly selected read-only preflight can verify identity without enabling updates. A write-capable build would need all checks complete before70:

- Verify the exact private original SS identity and installed build20191025, active DS hash/layout, constructor and updater code fingerprints, and selected Bluetooth HID transport. USB main-controller identity is insufficient.
- Resolve the updater dynamically through captured singleton global2067BC after fingerprinting its factory206676 and custom table206794. Validate its RAM pointer and full seven-entry table; do not hardcode the runtime object address20CABC. Expected IDs at+4..9 are70..75, base+0C=0, size+10=0, interval halfword+14=10. Storage205E10 bits[6:4] must be1. Validate the timer pointer+20, initial enable byte+1E=0 and inactive timer state. The configured write boundary byte20102C is16.
- Read and retain the latest VS before updating; never synthesize, zero or replace pairing data from a stock image. Check exact SS offsets and VS pointer/length. Abort on unexpected layout or identity, and keep private raw data out of logs.
- Allow writes only to planned SS0 bytes0..39, backup SS100 bytes100..127, and candidate DS4000..77F1. Exclude old DS3C0..39F2, VS1C0..3BF, unknown F000 metadata, erase73 and direct launch75. Revalidate candidate/source hashes and operation manifest immediately before enabling.
- Stage and verify backup SS100 before invalidating SS0. Write and verify every new DS byte before selecting it. Preserve the original DS and backup SS100. The existing transaction validator covers14,406 completed-byte prefixes and eight actual-ROM section-selection boundaries.
- Do not pause after70. Track the inactivity deadline; maintain serialized progress or an explicitly designed validated71/72 keepalive. On failure, stop new mutations and report the known boot-selectable state. Do not claim that exiting the updater leaves the device running indefinitely: the armed timer will reset it.
- Final SS0 commitment authorizes subsequent activation, including timeout reboot. Verify the full candidate DS and staged SS before the one-byte commit. Re-read the commit and selection metadata immediately afterward; if acknowledgment is lost, do not blindly rewrite. Expected disconnection after verification is a reboot indication, not proof of successful new application startup.
- Retaining SS100 does not automatically recover a valid SS0 whose DS crashes. An independently usable recovery route remains required for that case.

The [manufacturer EEPROM application note](https://www.infineon.com/assets/row/public/documents/30/42/infineon-an214820-eeprom-format-information-and-firmware-upgrading-applicationnotes-en.pdf) establishes the section model, private pairing data and staging concept, but expressly omits the detailed HID-layer protocol. The framing, error and watchdog findings above come from this captured implementation, not assumptions about its sample updater.

## Reproducible offline checks

`private/bt-persistence-research/test_update_protocol.py` executes the installed custom dispatcher, ROM checksum and read/write adapters, with modeled I2C/allocation/timer scheduling. Fourteen tests pass, including empty enable, malformed enable, disabled write, checksum and length failures, EEPROM write failure, false-success read framing, lack of GET70/74 ACK reports, timer refresh and modeled watchdog reset-register writes. Results are in `update-protocol-test-results.json`. No host HID transport, real EEPROM timing or physical watchdog is emulated.
