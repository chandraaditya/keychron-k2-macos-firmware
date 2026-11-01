# Apple battery-profile experiment

Latest: first neutral recovery startup fell back safely to A86 but did not invalidate SS0. The corrected guard now includes the original write-protection setup and callback. See [corrected recovery trial](RECOVERY-WP-TRIAL.md). Native Apple-profile testing remains pending physical recovery acceptance.

Prepared 28 October 2026. The goal is the native macOS Batteries widget and its low-battery behavior. No new Apple profile has been installed or accepted. A86 remains the last physically verified radio build. There is no new battery-life result.

## Offline prototype

`radio_apple_component.S` adds complete Input90 `[90,00,percentage]` and Feature34/version3 (77 bytes including Report ID) through the existing battery-object getter. The original root GET dispatcher, keyboard/media/system reports, vendor diagnostic updater and standard battery report3 remain. Connection/change notifications send both report3 and90; the existing60-second normal-change limit remains. Status bits are zero until their charging meanings are verified.

The address in Feature34 comes from the existing battery object+6, populated by the original constructor from the connection address. No device address is embedded in source. The component allocates152 bytes through the existing allocator and publishes the shadow table last.

The ROM BF configuration record can provide an alternate SDP blob, without relocating existing app data. The initial append-only fixture was superseded by an explicit429-byte grouped descriptor: a first FF00/1A multiple-interface marker, one keyboard Application wrapper containing the exact original323bytes, and one management Application wrapper containing the exact observed83bytes. This preserves the original report fields and separates keyboard and management according to the verified kernel interface algorithm. It changes DeviceID vendor/product/source to BluetoothSIG004C/0267/1 for a temporary compatibility experiment. Actual Bluetooth host preprocessing and final driver attachment remain physical acceptance questions. The1053-byte SDP payload and its BF record parse and load correctly offline. Historical append-only fixtures remain preserved.

`build_radio_apple_candidate.py` emits a research DS only. Its manifest explicitly disallows interpreting it as a cleared installation. It is not a full EEPROM image or vendor updater file.

## Recovery trial before changing the profile

The installed working A86 DS occupies8000. The new recovery trial reuses inactive bank4000, keeps A86 at8000 and original firmware at3C0, and first changes backup SS100 to select A86. SS0 activation is last. A durable fresh full EEPROM backup precedes enabling the updater. Pairing/VS changes are preserved.

The first two trial records load and invoke a192-byte guard before the rest of the DS. It writes only SS0 validity byte0 to zero, polls for EEPROM completion, and reads the byte back. All polling uses a shared finite instruction budget; watchdog service occurs every1024 polls. The budget is not a measured time duration. Successful invalidation means the next reset selects retained A86 from SS100, regardless of what later prototype code does.

On a protocol error or readback failure, the guard arms the ROM's one-use config hook at200C80. The hook clears itself, sets selected DS base205E1C to8000, and returns8000 to the original parser before the new profile is processed. No parser ABI violation, ROM modification, EEPROM erase or direct LAUNCH is used.

Physical bus failure remains a limit: fallback parsing uses the original EEPROM reader. A permanently stuck bus or failed memory cannot be repaired by this software guard. External ESP32 recovery remains unverified. Completed-byte interruption tests do not simulate electrically torn writes.

`radio-rollback-preflight` contains this guard followed by the exact existing A86 DS. It changes no Bluetooth identity or HID descriptor. Its physical acceptance requires both:

1. First startup: A86 runs from4000, SS0 is invalidated and SS100 selects8000.
2. After owner power-cycle: A86 runs from8000, with working typing and unchanged extension/methods.

The owner-facing admin helper has a separate `--apply-rollback-preflight` mode. It pins the new installer source and candidate, uses root only to claim the HID device, and permanently drops root before backup or any update enable. The old updater modes still reject the wrong predecessor. This mode is a firmware write; it is not a read-only check.

The owner's first physical preflight attempt was rejected after the64KiB read: `EEPROM outside pairing/VS differs from reviewed backup`. Its journal contains only the claim/root-drop event; no update-enable or write event occurred. The first implementation compared before saving, so that rejected in-memory capture was lost. This ordering is corrected: future full reads are durably saved before comparison, and rejection is journaled before any enable.

The separate owner-run read-only diagnostic established26 stable outside-VS changes, all within the second38-byte saved Bluetooth slot recordF027..F04C. Its changed32-byte blocks were independently reread as16+16 and exactly matched the first capture. SS0, SS100, all firmware banks and every other byte outside VS match the historical capture. No partial-AA tail was seen. The original application writes this exact record through20823A→174FA; see `research/eeprom-drift-findings.md`.

A new reviewed snapshot is saved separately as `private/bt-eeprom-A86-preflight-reviewed-64k.bin`, SHA256 `767dd6fe973c11aa6be53c204cb52330c6b2f78be6bfcb7d31c74bac53afe840`. The historical snapshot is preserved. The installer pins both captures and checks that their transition changes only VS plus those26 bytes inside the second slot record. Its live `fresh_matches` remains strict outside VS; even a further change inside that slot is rejected. No mutable-region mask was expanded. The actual candidate firmware is unchanged.

The native transport now limits EEPROM requests to16 bytes. ROM GET72 ignores adapter failure; with32-byte requests it can return a valid first16 plus an AA-filled failed tail, with a valid HID checksum. A single16-byte request allows the existing all-AA failure guard to reject that failed transfer. ROM/RAM requests retain32-byte chunks. Sixteen base installer tests include exact native chunking and response parsing; this is a transport correction independent of the observed legitimate slot drift.

Read-only Codex queries received macOS access error e00002e2; the owner runs the hardware diagnostic from Ghostty with Input Monitoring. No permission database or OS security setting was changed. The Apple profile remains offline.

The read-only checker is `installers/verify_radio_rollback_preflight.py trial` or `fallback`, run from the permitted terminal. It writes a sanitized result under `artifacts/k2-initial-release/` only after all expected header/runtime checks pass.

## Verification completed offline

- Eight report-handler methods: all101 percentages, original keyboard/media/system routes, Feature34 lengths/address, optional unsupported queries, notification behavior and allocator failure, through actual root ROM161E→D3E.
- Four image/boot methods: actual ROM scatter, full DS parser, BF registration and loader, heap initialization and original-record preservation.
- Five one-boot guard methods: actual async I2C setup/status routines with modeled controller completion, early controller initialization, NACK/retry, seven failure modes, bounded polling/watchdog service and neutral preflight. Fallback EEPROM readability is modeled, not physically established after a bus timeout.
- Ten staging/verifier methods: exact write windows,14610 completed-byte cuts, lost-ACK stop, predecessor corruption rejection, pairing preservation, rejected-capture retention, continued slot-metadata rejection and trial/fallback distinction.
- Five admin-helper methods: source pin, claim/release, permanent privilege drop before transaction and refusal without authentication.
- Four read-only diagnostic methods: region classification, private rejected-capture retention, partial-AA-tail rereads and retention after reread failure.

These checks establish an offline prototype and a concrete recovery experiment. They do not establish native macOS driver attachment, Batteries widget display, charging status, low-battery notifications or monthly runtime.
