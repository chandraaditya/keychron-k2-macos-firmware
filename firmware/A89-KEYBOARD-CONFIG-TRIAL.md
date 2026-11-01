# A89: restore the Apple keyboard volume mapping

28 October 2026. Built and reviewed offline; not installed.

The owner confirmed A88's native Batteries widget shows83%, but plain and physical-Fn F12 both produce ordinary F12 Terminal escape sequences. The Mac's standard-function-key preference is off and the built-in keyboard behaves correctly. Metadata on the K2's AppleHIDKeyboardEventDriverV2 shows HIDFKeyMode0 and FnKeyboardUsageMap, but no FnFunctionUsageMap. Cached Input1/2 reads did not track presses; they cannot establish live Fn state or absent input transmission.

The actual native V2 keyboard initializer requests Feature2. Its parser expects version1 configuration with glyph/action pairs. The Bluetooth keyboard bridge routes it through selectorFF/02 and FeatureF1. A88 supports management F0/34/90 only, so this initialization request fails.

A89 adds a constant logical reply `02 01 01 00 00 0A 0D 0B 0E 0C 0F`, returning it directly for Feature2 and with prefixF1 for the selected keyboard keyhole. The actual Mac parser builds F10→mute, F11→volume-down, F12→volume-up from these bytes. Existing Input2, keyboard reports, updater, battery notifications, estimator, SDP identity, MTU and recovery remain unchanged. Selector/type mismatches reject; unsupported selections invalidate old state.

The candidate is16103 bytes, SHA256 `84b9a586ae905ca57bebeebf2d1d6d1d1e14e94cb0a4c6c7a46a74781104f87d`. Its892-byte extension is SHA256 `23469bcb877690b272ef87c2a2b8422bc16d1cc1f114ca19eedcdb5062c48eb9`. The protected A86 bank begins8000; this trial ends7EE7. The physically accepted WP prefix is byte-identical.

Offline checks passed: inherited battery/updater and new configuration callback tests; actual native Mac parser and daemon callback tests; full startup/heap/constructor tests; transaction tests including16104 completed-byte cuts and stop-after-error behavior; exact-runtime verifier tests; administrator-helper privilege-drop tests and isolated pinned dependency loading. Astra independently reviewed the emitted candidate, framing, guards and protected ranges and found no blocking defect. EEPROM electrical faults and live Mac behavior remain outside these models.

The new installer accepts exact A88 runtime and storage, constructed from the pinned A87 baseline plus the pinned installed A88 image. It saves a full fresh backup before strict comparison or enabling updates. Only inactive DS4000 and final SS0 validity byte may change; A86, SS100, original code and settings remain protected. A normal restart after the trial returns to A86. Do not treat this as a persistent release.

Owner-operated installation, with Bluetooth selected and USB power connected:

```sh
sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-keyboard-config-trial
```

After completion, keep power on, allow reconnection, then run the read-only verifier:

```sh
/usr/bin/python3 installers/verify_radio_keyboard_config_trial.py
```

Acceptance requires the native map to appear, mute/volume/release/repeat to work, and typing plus Fn behavior to be checked physically while the battery widget remains functional. This minimal reply does not yet restore other function-row mappings or establish Fn distinction. Long Feature34 and the Bluetooth row remain a separate unresolved issue. No state-of-charge calibration or battery-runtime gain is claimed.
