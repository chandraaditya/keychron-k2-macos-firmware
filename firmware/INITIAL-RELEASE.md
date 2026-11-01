# Initial release: connected idle and Bluetooth battery reporting

**Historical preparation/trial record. Current installed A86 status: [verified installed trial](INSTALLED-TRIAL.md). Phase0 assumptions below were corrected after the physical trial; use the A86 source paths in the current record.**

28 October 2026. **Owner-authorized main CPU-idle A installation succeeded:** 1,024 blocks, final checksum 0x941D, CS1 unchanged. Normal restart succeeded; the owner confirmed basic typing over both USB and Bluetooth, and USB reports bcdDevice0x0113. The initial A85 Bluetooth DS was subsequently programmed and checksum/readback verified. Its startup guard declined, so original battery methods remained active after both watchdog and full power-cycle boots. A separate A86 repair is prepared; see the correction below. The main write-capable build was compiled only after authorization; default tools remain write-disabled. See `artifacts/k2-initial-release/main-flash-result.json`.

## Board and reference compatibility

The owner's photos establish the front marking `Keychron K2 RGB Ver 1.2/20200515`, underside `CK8887RGB-1.2 / 20200427`, main controller `HFD2201KBA`, radio `CYW20730 A2KFBG`, adjacent `24C512A` memory and the two BOOT holes beneath the spacebar. The keyboard has two rear height settings, US/ANSI horizontal Enter, RGB lighting and soldered mechanical switches. This supports the **K2 V2 US RGB non-hot-swap** target described by [Keychron's V2 page](https://www.keychron.com/pages/firmware-for-k2-version-2). The photographed PCB revision differs from the published community example; no claim of identical PCB artwork is needed.

Owner-operated BOOT entry successfully enumerated USB `0c45:7040`. The identification-only probe confirmed SN32F24xB, revision 0, 64 KiB profile, **CS1** and whole-flash 16-bit checksum **0xBBA4**. Only commands 1/6 were sent. This establishes bootloader access and identity, not a demonstrated restore or a byte-exact installed-flash backup. Preserve CS1: lowering protection can erase the installed image. Evidence: `private/bootloader-identification-verified.json`.

Normal wired identity is `05ac:024f`, bcdDevice `0x0104`, with 89-/158-byte HID descriptors. The downloadable main image named 1.04 has a different first descriptor. The scanner candidate therefore uses the **published V2 RGB 1.13 reference**, not a dump of the installed scanner image. **Its full-image installation replaces the owner's main-controller settings with reference defaults.** Device settings have not been separately preserved.

The Bluetooth candidate instead uses the exact installed application **A05/20191025**, pinned by the captured application, ROM and RAM hashes. The native radio read-only preflight also passed after reconnection: live application/updater context and all 64 KiB outside current VS matched the reviewed capture. No update was enabled. Its custom identity becomes A85/20261027. The old guarded internal reader deliberately rejects that version.

## Two components and separate update paths

| Component | Initial change | Update route |
|---|---|---|
| Main scanner/RGB controller | CPU-idle A: retain scanning, timers, interrupts and SPI; yield CPU through guarded PMU4 between work | USB boot ROM; exact 65,536-byte image, offset zero, 1,024 blocks |
| CYW20730 radio | Fix the standard battery-report getter, increases/decreases and connection notification | Bluetooth HID updater; stage application in external EEPROM and select it through its static section |

CPU-idle A is a conservative first power experiment. It does not implement deep matrix sleep or alter Bluetooth connection policy. It has no measured current/runtime benefit yet, and does not promise 20–30 days or faster reconnection. Key scanning can continue through interrupts while the CPU yields between them.

The radio extension copies the fifteen original battery-object methods into a 68-byte allocator-owned shadow table/state block. It replaces only query, notification and connection handling. Report 3 returns the validated 0–100 estimate used by Fn+B. Changes in either direction are supported, duplicates suppressed, ordinary changed notifications limited to nominally 60 seconds, and connection notifications immediate. No extra ADC sampling or periodic polling is added. The original voltage-based estimate remains sensitive to charging and lighting load.

The 440-byte extension occupies `0x209014..0x2091CB`; the application arena begins at `0x2091CC`. Startup requires phase zero and the expected original arena/instruction, reserves the extension before the arena is initialized, and then installs the constructor hook. **Full reset boot is required; hot loading is unsupported.** Captured ROM shows watchdog reset following normal startup/DS-load-before-heap. This is code evidence, not a physical reset-domain measurement.

**Native macOS Bluetooth battery display remains an acceptance test.** Returning a correct standard HID report does not prove that macOS publishes it in the Bluetooth panel or Batteries display. Test the query, unsolicited notifications, native UI and low-battery warning separately. No host helper is installed.

## Backups, memory and recovery

Private captures contain the full documented 320 KiB radio ROM and 64 KiB EEPROM window. They include identity/pairing data and must remain private. Active DS is `0x03C0..0x39F2`; VS/pairings is `0x01C0..0x03BF`; unknown metadata around `0xF000` is retained.

The photographed `24C512A` marking plus the non-aliased full capture support a physical 64 KiB EEPROM. The probable Fremont manufacturer reference specifies 128-byte pages and maximum 5 ms programming; the manufacturer/logo identification remains qualified. Actual board writes are untested. The installed ROM's existing 16-byte boundary and maximum 14 data bytes fit safely within 128-byte pages; no driver geometry change is proposed. See [physical memory review](../research/physical-eeprom-and-recovery-review.md).

Main recovery is the already-demonstrated BOOT entry, followed by an appropriate full reference-image restore; main programming under unchanged CS1 now succeeded, but an actual reference-image restore has not been attempted. Radio recovery is separate: retained original DS and SS100 provide a rollback target, but a valid SS0 selecting crashing code does **not** automatically fall back. External EEPROM recovery via its exposed leads is plausible, not yet independently demonstrated in circuit. Sonix BOOT mode cannot repair radio EEPROM.

## Guarded installers

See [installer operation and test procedure](../installers/README.md). The native scanner installer defaults to hardware programming compiled out. The radio installer has hardware updates disabled. File-only planning and read-only preflight are available; a separately named owner-authorized main executable was built and used for this trial.

The main installer pins the candidate SHA, size/footer, unique USB target, exact family/revision, CS1 and baseline checksum. It shares a nonblocking process lock with the identification probe, and requires exclusive HID ownership in its programming branch. Its protocol contains no security, separate erase or reboot command. It stops on any unexpected acknowledgment or checksum and never retries automatically. Programming under CS1 succeeded on this device during the authorized trial. Device verification is the bootloader's 16-bit checksum/footer, not a cryptographic full readback.

The Bluetooth installer pins the original capture, RAM/ROM and new candidate hashes. It checks the live updater's factory/table/dispatcher fingerprints, dynamic object pointer, IDs, zero base, EEPROM storage mode, boundary, disabled state and inactive timer. It saves a fresh complete private EEPROM backup, including current VS, before enabling updates. It preserves changed live VS rather than replacing pairings from the earlier capture.

The staged transaction is:

1. Copy and verify original SS0 into SS100, committing its valid first byte last.
2. Write and verify candidate DS at `0x4000..0x77F1`, preserving original DS and VS.
3. Invalidate SS0. Write and verify its new body selecting DS4000; verify candidate and backup SS again.
4. Commit SS0's valid first byte last, then verify selection metadata and VS.
5. Send no direct LAUNCH. Expect watchdog full-reset activation when update activity stops.

**Enable report 70 arms a nominal ten-second inactivity restart.** There is no owner prompt or long pause after enable. Writes use SET_REPORT acknowledgment plus exact readback: the firmware can return a checksummed read response after a low-level read failure. The client rejects ambiguous all-AA reads, uses conservative watchdog deadlines and bounded calls, stops on failure, and performs no blind retry/rollback. A hard native timeout exits without unwinding; an unmatched durable `before-enable` or `before-write` journal entry means an unknown outcome. Exiting after enable does not cancel the timer. See [captured updater contract](../research/radio-updater-protocol.md).

## Offline verification and physical limits

| Area | Passed | Limit |
|---|---|---|
| Scanner candidate | 14 methods plus 20 guard subcases | CPU idle/wake modeled; no actual current or silicon wake result |
| Radio battery component | 15 methods, all 101 valid percentages | Selected allocator/transport/hardware mocked |
| Radio persistent boot | 8 methods; actual ROM startup/BSS/factory/heap paths | Selected hardware and allocation mocked |
| Persistent staging model | 14,406 completed-byte cut states and 8 actual-ROM selector boundaries | No torn-byte/page-corruption or crashing-app recovery proof |
| Radio protocol | 14 methods exercising captured dispatcher/adapters | No physical HID write or watchdog timing |
| Main installer | 19 transfer/validation cases under ASan/UBSan; 8 CLI/file/lock checks | Native writes disabled; no hardware transfer |
| Radio installer | 15 methods including full staging, context rejection, ACK-loss cuts, pairing preservation, API framing and deadlines | Memory transport; physical update not attempted |

Astra (`gpt-6-astra`) independently reviewed the emitted firmware and protocol, and audited the installer. Source and sanitized reports are under `firmware/`, `installers/`, `research/` and `artifacts/k2-initial-release/`; raw captures and radio payload remain private. The release manifest records current status. Main programming is checksum-verified. Basic main USB/Bluetooth input is owner-confirmed. Full matrix/host-output/wake checks, reference restore, radio update/recovery, power/current, long idle, reconnect and native macOS display remain unverified.

## Authorized trial observations

After the main update and restart, the unchanged radio A05/20191025 returned standard report85%, matching cached85% and internal85% (sensor1862). The previous stale-zero condition is therefore not permanent. This does not establish why the earlier cache was zero or prove that the main patch itself corrected it. Charging-increase and reconnect-notification changes remain separate radio-candidate behavior. The K2 still had no native battery property in the inspected HID tree. Evidence: `artifacts/k2-initial-release/post-main-battery-baseline.json`.

The first radio apply attempt stopped before enable: exclusive keyboard access returned0xe00002c1. Apple HID source requires a privileged client for keyboard seizure. The reviewed `radio_admin_trial.py` performs a claim/read-only-check/release first, then reclaims and permanently drops root before creating the session backup or enabling updates. It uses the original owner-held lock inode and the exact source-hashed updater under the isolated system interpreter. Five additional offline control-flow tests pass.

## Radio startup correction after physical trial

The A85 transaction completed, pairings and typing survived, and its marker loaded. However the hook and arena stayed original, and the extension became EF stack watermark. Original battery methods remained active. This is a failed patch-activation test, not a successful battery fix. Both watchdog and full power-off boots reproduced it.

Our original emulator manually seeded phase0 after the earlier ROM initialization and missed that the actual scatter initializer writes phase1. The corrected regression runs real scatter initialization, the entire DS parser including both0B callbacks, and heap initialization; it reproduces A85 failure and validates the separate A86 phase1 guard. This corrects the phase0 assumption above and in historical initial artifacts; those artifacts are intentionally retained. See [boot correction](../research/radio-phase1-boot-correction.md).

A86 preserves the 312-byte battery component and all other guards. Its extension remains440 bytes, arena2091CC; the constructor wrapper moves to209052 and hook becomes02f0d3fa. SHA272c7f60a926c65dab10685375aadbb94bc1ddaff88ebfedaa00e84dcd69be3f. The repair plan uses the reviewed all-FF erased region8000..B7F1, preserving originalDS3C0, originalSS100, A85DS4000 and liveVS. Its eight transaction tests include14,363 completed-byte cuts. Full physical A86 activation remains pending; native macOS display and current/runtime remain unverified.
