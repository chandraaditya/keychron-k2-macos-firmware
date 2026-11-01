# A88 Apple battery request wrapper

28 October2026. User resumed after a pause and explicitly requested identifying the running firmware and proceeding with A88. The short read-only resume check verified A87, current bank4000, invalid trial header and valid A86 fallback8000. The maintenance interface allowed an owner-only exclusive claim with the hardware update gate still disabled. This permits the reviewed transaction to run without administrator privileges; the current transaction journal records `root_used:false`.

## Why A87 showed an empty native widget

Fresh pairing changed the actual host topology to Apple VID004C/source1/PID0267 with four synthesized IOHIDUserDevices:22-byte raw maintenance,83-byte management,182-byte keyboard, and27-byte vendor interface. The owner saw the keyboard in the native Batteries widget with an empty/zero ring, no percentage in the Bluetooth row, and completed Keyboard Setup Assistant. Management properties had neither BatteryPercent nor BD_ADDR, so widget appearance alone was not working charge reporting.

The exact83-byte management descriptor is synthesized by bluetoothd. Its get-report bridge sends Feature SET `[FF, requestedID]`, GETs F0 using the requested report type, then removes the initial F0 byte. Native GET34 therefore is not proof of direct physical GET34. Direct unsolicited90 notifications are forwarded unchanged. The daemon serializes its selector/get pair, while raw maintenance uses a separate transport lock. The existing22-byte interface forwards diagnostics directly; actual71/72 reads and a full fresh64KiB capture succeeded through it.

## A88 change

`firmware/radio_apple_keyhole_component.S` adds a guarded root SET hook and keeps original delegation for other requests. At the radio root callback, SET FeatureFF has one payload byte because the original HIDP parser already removed the report ID. Supported selectors34/90 set private state; unsupported selectors invalidate prior state and return unsupported. GET InputF0 returns `[F0,90,status,percent]`; GET FeatureF0 returns `[F0,34,03,fwLo,fwHi,address6,tail67]`. Existing direct90/34, standard report3, keyboard/media/system reports and diagnostics remain.

The152-byte allocation is unchanged. Selector149 and valid150 remain beyond the response buffer71..148. Short F0/90 uses71..74; the longer34 path explicitly rebuilds overwritten header/version bytes. Direct90 remains68..70. The initialized shadow table is published before the root SET hook, and installation checks the exact original root setter first. No new ADC reads, background helper or OS modification is introduced.

The full one-boot DS is16027bytes, SHA256 `b379a195e36de62c59a1e6baea2a727a48a33010ba37e9aede7fbd8fe9d7adae`. The extension is816bytes, SHA256 `34b17627521810fc57a2fcfa0fb9646c4621cab971b3873f9736c2e32e48b346`. Its recovery prefix is byte-identical to the physically verified neutral WP trial. It ends357bytes before A86 bank8000. Historical A87 images remain retained.

## Update safeguards and evidence

`installers/radio_keyhole_trial.py` pins the fresh A87 snapshot SHA256 `f150d79de2ad2f26054e26c44915e8270fd5d9fffca33823993a46bb633cc691`. Its only outside-VS transition from the previous completed image is16 independently stable bytes inside the first saved host-slot record. The live strict comparison still accepts no later outside-VS drift. A fresh full backup precedes comparison and any update enable. Only DS4000 and SS0 byte0 are writable; fallback8000, original3C0, backup header, SS0 body, pairing and metadata are retained. Activation is last.

The isolated loader checks all dependency hashes. The owner-mode orchestration uses the same pinned NativeHID, guard, plan, runner and durable journal; it claims/checks/releases, reclaims, then backs up and runs the transaction as the normal project owner. It acquires no root privileges. The administrator-helper path remains available and separately pinned.

Sixteen component methods cover every selector, all101 percentages, direct and wrapped reads, shared-buffer reuse, wrong shapes and original read-setup delegation. Three full startup methods cover actual ROM pre-DS/DS/GPIO/I2C setup, heap, constructor and unchanged failure fallback. Independent full HIDP packet tests confirm the stripped selector ABI. Six transaction methods cover16028 completed-byte cuts, protected ranges, lost-ACK stop and predecessor/proof checks. Actual electrically torn writes and physical bus faults remain outside the model. Astra independently reviewed component, loader, selector, staging and reader.

## Acceptance

The owner confirmed that A88 displays **83% in the existing native Batteries widget**. This is accepted for widget visibility and a live nonzero value, not for calibrated state of charge, the Bluetooth row, or measured runtime. The long Feature34 request still fails with the live control-channel cap of48 bytes.

The owner also found a regression: K2 volume keys no longer control volume, with or without Fn, while the built-in keyboard behaves normally and the standard-function-key preference is off. A bounded Terminal test produced normal F12 escape sequences for both combinations. Cached GET Input1/2 did not track the presses; those empty cached observations are not evidence of absent key transmission. Investigation is restricted to restoring the Apple keyboard configuration/report contract before another firmware trial. No later image has been installed.

`installers/verify_radio_keyhole_trial.py` verifies A88 through the raw maintenance interface, including the exact816-byte extension, root GET/SET hooks, all15 methods, current bank and rollback headers. It then releases that handle and queries the native83-byte management interface. Those reads internally perform the FF/F0 selection exchange, not an EEPROM write. It records Input90, Feature34 address agreement and the matching native management BatteryPercent. Raw addresses and serials are not printed. Owner observation of the widget and Bluetooth row remains required.

This remains a one-boot experiment until physically accepted and a persistent version is deliberately prepared. Charging flags are still zero and the percent remains the existing voltage-based estimate. Low-battery UI behavior and battery-runtime improvement remain unmeasured.
