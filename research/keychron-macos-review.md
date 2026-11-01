# Review: bkovacev/keychron-macos and the Bluetooth-row requirement

28 October 2026. Reviewed source at commit219e5a1bc7296bcc79fb4d36f30bc001c7cf0ec3 through the GitHub connector. No repository installer, app, firmware or demo was executed. The owner explicitly requires the percentage beside the K2 in the Bluetooth device row; Control Center's separate Batteries list is insufficient.

## What the repository actually provides

The project's own [known limits](https://github.com/bkovacev/keychron-macos/blob/219e5a1bc7296bcc79fb4d36f30bc001c7cf0ec3/README.md#known-limits) state that the keyboard will not appear as a Bluetooth battery. Its [PowerSource.swift](https://github.com/bkovacev/keychron-macos/blob/219e5a1bc7296bcc79fb4d36f30bc001c7cf0ec3/macos/Sources/K10ProBattery/PowerSource.swift) resolves IOPSCreatePowerSource, IOPSSetPowerSourceDetails and IOPSReleasePowerSource, registering Type=Accessory Source for the native Control Center/Batteries surfaces. Setting Transport Type=Bluetooth in that dictionary does not make this a bluetoothd device-row update. This is separate from the previously tested HID-service BatteryCapacity publication.

The firmware is QMK for a K10 Pro STM32L432/CKBT51 system. It exposes readings through USB raw HID and a custom Consumer-usage beacon over the radio's existing report. It also has LED-element control commands. Those board targets, firmware binaries, beacon decoders and control writes do not apply to the Sonix/CYW20730 K2. The Mac publisher could be adapted to the K2's now-working report3, but would still populate the wrong requested surface.

The author's inability to alter CKBT51's descriptor from QMK is specific to that architecture/work scope. It does not establish that the K2 radio firmware cannot be changed; A86 already demonstrates that. Nor does absence of battery parsing in an open generic driver prove absence in all closed Apple drivers. We directly inspected the latter.

Reviewed blobs: README222e0d836b843a50f0bf91cea23353c391b026e5; researchb80ca0bb8e77fd5ce43eb5105bf2801a5615dbd2; publisher2bf882f102af046f46418afa0601736e7ac0ef8a.

## Concrete Bluetooth-row path recovered independently

The installed Apple management driver reads Input0x90 with payload[status,percentage], and Feature0x34 with a76-byte version3 payload containing the Bluetooth address. It publishes BatteryPercent/BD_ADDR and sends a battery-status notification. Its external personalities also match specific Apple IDs and a vendor management collection. Generic report3 is not the same contract.

A read-only query to the owner's actual Lightning Magic Trackpad2 independently confirmed both reports: complete Feature34 length77/version3/address matching its registry serial in forward order; complete Input90 length3/status0/percentage70. Identifiers were omitted. Its existing registry management descriptor is83bytes, and the native management class is attached. Evidence: private/apple/management/live-trackpad-validation.json.

The installed bluetoothd fallback was also executed OFFLINE over64 individual flag bits and20 override combinations. With no feature/preference override, it accepts flags0x2E800 (bits11,13,14,15,17). This does not prove the K2's live flags: feature/config calls were mocked and internal live daemon memory was not read. Source: research/emulate_native_battery_gate.py; result: private/apple/native-gate-emulation.json. No feature flag was changed.

## Next test and boundaries

The specific missing proof is driver attachment and association with the real K2 Bluetooth row. The safest candidate proof is a temporary battery-only host management interface serving the exact reports and associating the real K2 address, with no keyboard/mouse/touch input usages. The pure offline packet fixture has five tests covering every0–100 percentage, invalid values, address order and descriptor report sizes. No virtual device was created.

Virtual-HID creation itself requires an accepted Apple entitlement in the current kernel; sudo alone is insufficient. A legitimately entitled host publisher, if available, would allow a nonflash proof. Driver binding on Virtual transport and native UI association would still need testing separately. Do not forge entitlements or change OS protections.

A physical-radio management profile remains another possible route, but entails explicit matching/identity treatment and checking all reports the selected driver can issue, plus maintaining diagnostics and an independently usable recovery route. Adding report90 or changing a PID alone is not a validated update. The working A86 firmware remains untouched during this research.

Detailed primary implementation evidence and proposed descriptor: [management protocol](native-management-protocol.md). The repository is useful corroboration of separate UI pipelines, not a solution to the strict Bluetooth-row requirement.
