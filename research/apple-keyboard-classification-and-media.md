# Apple keyboard classification and media contract

Offline assessment, 2026-10-28. No device, daemon, input, setting, or firmware operations are performed by this research. Hardware observations cited below were supplied by the parent investigation.

## Removing the BF descriptor override

The local ARM64e `/usr/sbin/bluetoothd` chooses the relevant Apple keyboard translator from DeviceID, independently of the FF00/1A marker in the physical report descriptor.

* Initializer `100574174` builds source enum0→1 / enum1→2 and vendor enum0→004C / enum1→05AC. Vendor constants are at `10095B638`; product map at `10095B660` maps enum0C→0267.
* Initializer `100574474..1005744BC` creates a classification entry with source enum0, vendor enum0, product enums `[0C,0D,0E,0F,10,19,1A,1B]` (literal `10095B818`), and flag4. The corresponding product IDs are 0267,026C,029A,029C,029F,0320,0321,0322.
* `10052088C` obtains DeviceID fields from the object's parsed identity, then `10052092C..1005209E4` compares only source/vendor/product to this table and ORs flag4 into object+388. It does not inspect a report descriptor.
* `100520F04` returns bit4. Selector `100613600..1006136E8` checks the shared Apple-device feature gate, tests this bit, and constructs keyboard translator `1002A5890`.
* Its creator `1002A5F88` selects fixed descriptors by product. For 0267 the ordinary path calls `1002A6664`, which copies the **182-byte** constant at `10095819A`. Some newer product IDs select a different207-byte constant. Management creation `1002A61EC` uses its own fixed83-byte constant and F0 keyhole selector.

Thus preserving the original valid323-byte physical HID descriptor while changing only original SDP DeviceID to source1/vendor004C/product0267 is a defensible compact candidate. The previously added1056-byte BF record is not needed by these observed classifier paths. This is static proof for this installed daemon, not a guarantee for every OS release. Actual original descriptors and keyboard behavior still need the normal trial verification.

`research/test_apple_keyboard_classifier.py` executes the actual ARM64 classifier loop against literal product/vendor tables:3 test methods pass, covering all8 accepted keyboard IDs and4 mismatched identity cases. Only C++ map lookup and table allocation are modeled; no descriptor memory is supplied to the executed loop. This supplements the initializer/selector/creator static traces in `private/apple-profile/apple-classifier-initializers.txt`.

## Report1 length and Fn bit correction

The original K2 descriptor already declares72 payload bits for keyboard report1: modifier8, reserved8, six key bytes48, and an8-bit FF/03 Fn field. Its complete report is10 bytes including ID. **Do not append another byte.**

The fixed Apple182 descriptor retains the same total length, but splits the last byte: bit0 is Consumer/Eject(B8), and bits1..7 are FF/03 Fn. A logical Fn value1 must therefore be encoded as final byte02. Passing original final byte01 unchanged would request Eject, not Fn.

The original scanner may keep its physical Fn processing local. The actual emitted original Fn-byte value must come from source or the parent's bounded report observation; do not assume every original F-key report carries Fn1.

## Function-key translation

Primary Apple source, pinned IOHIDFamily commit777ccd9698845aadf711e32d843c8c9b777431d9, `IOHIDEventSystemPlugIns/IOHIDKeyboardFilter.mm`:

* lines411–416 load the service's `FnFunctionUsageMap`.
* lines1676–1686 apply that map exactly when `FnKeyDown == !!_fnKeyMode`.
* `_fnKeyMode` initializes to0; lines988–995 update it from `kIOHIDFKeyModeKey`.
* Fn also activates other modified-key maps; it is not a modifier scoped solely to F keys.

Source: https://github.com/apple-oss-distributions/IOHIDFamily/blob/777ccd9698845aadf711e32d843c8c9b777431d9/IOHIDEventSystemPlugIns/IOHIDKeyboardFilter.mm . Local copy: `private/apple-profile/IOHIDKeyboardFilter.mm`.

Installed Apple keyboard personality maps explicitly contain F10(07/43)→mute(0C/E2), F11(07/44)→volume-down(0C/EA), and F12(07/45)→volume-up(0C/E9). With the owner's standard-F preference OFF, Fn0 allows that mapping and Fn1 suppresses it. **The actual current0267 K2 service must expose the map**; installed mappings for other keyboard personalities alone do not establish that it does. Metadata-only inspection can settle that field without changing settings.

A minimal candidate is therefore: Consumer2 volume bits become ordinary report1 F10/F11/F12 with final Fn byte0; explicit original standard F keys use final Fn byte02. Preserve10-byte length, held keys, releases, modifiers, and consistent Fn state. Do not set Fn02 on every ordinary key report: Fn-arrow, Fn-backspace, and Fn-return may receive other transformations. A mixed chord containing original standard F keys and synthesized media F keys shares one Fn bit and cannot express both meanings in one simultaneous report; define a bounded priority or separate state transitions rather than silently promising both.

The fixed descriptor also defines Input52 playback bits0=CD(play/pause),1=B3(fast-forward),2=B4(rewind),3=B5(next-track),4=B6(previous-track). Report9 is Feature, not an input consumer-volume channel. Brightness can use the service's F1/F2 map if present; other original Consumer usages need explicit supported routing and must not be fabricated.

Remaining physical proof is narrow: volume up/down/mute, Fn+F11/F12 standard-key behavior, release/repeat, and one ordinary typing/navigation check after the guarded candidate. It is not necessary to expand this into a new broad investigation.

## Concrete missing configuration found — supersedes the generic mapping hypothesis

The parent then observed that the actual K2 `AppleHIDKeyboardEventDriverV2` service has `FnKeyboardUsageMap` and `HIDFKeyMode=0`, but **no `FnFunctionUsageMap`**. Plain and physical-Fn F12 both emitted ordinary F12. This makes restoring the keyboard configuration response the smallest justified next candidate; F-key conversion alone would not repair an absent host map.

The captured native kernelcache provides named V2 driver functions. Kext header is file offset51D900; text executes at FFFFFE0009712190. `private/apple-profile/inspect_keyboard_driver.py` reproducibly extracts the relevant functions into `keyboard-driver-configuration.txt`.

`initKeyboardConfigurationGated` at FFFFFE0009716030 allocates512 bytes, asks its HID provider for Feature report2 (IOKit type2, reportID2; instructions62AC–62C4), and calls `parseKeyboardConfiguration` with offset1 at637C. The parser at64CC reads a four-byte configuration header after the reportID. Header version1 selects the known parser; byte1 specifies physical layout (1→ANSI), byte2 language, byte3 design. Remaining two-byte records are glyph/action enums. `createFKeyMapping` at5724 converts them to a mapping string and the parser publishes it under literal `FnFunctionUsageMap` at678C–67A0.

Minimal logical Feature2 response, **11 bytes including reportID**:

```
02 01 01 00 00 0A 0D 0B 0E 0C 0F
```

The last six bytes mean F10→mute, F11→volume-down, F12→volume-up. Native glyph enum0A/0B/0C maps to07/43,07/44,07/45; native action enum0D/0E/0F maps to0C/E2,0C/EA,0C/E9. These are decoded from the actual driver, not assumed HID usage bytes.

The Bluetooth daemon keyboard creator stores keyhole **F1** at context+8. Callback1002A6810 preserves IOKit type, requested reportID, buffer and length-pointer, and supplies F1 to the same keyhole getter used by management. Therefore the radio must accept Feature FF selector02 and answer Feature GET F1 with12 bytes: `F1` followed by the above11. Preserve ordinary Input2 and all updater traffic. This fits the existing48-byte channel cap; the long Feature34/MTU issue need not be coupled to this minimal media repair.

`research/test_apple_keyboard_configuration.py`: **3 test methods pass**. The valid case executes actual native parser→createFKeyMapping→getGlyphKeyMapping/getUsageMapping and observes publication of exactly:

```
0x00070043,0x000c00e2,0x00070044,0x000c00ea,0x00070045,0x000c00e9
```

The other cases reject an invalid configuration version and execute the actual daemon callback to verify the Feature2/F1 argument contract. PAC is neutralized only in emulator copies. OS metadata factories, allocation/string formatting, and property publication are modeled; no HID provider or host setting is touched. This establishes parser/protocol compatibility, not physical success or automatic driver reinitialization on an already-connected service.

This minimal response intentionally restores only volume/mute mappings. It does not promise brightness/playback or Fn distinction without the corresponding firmware reports. An observed9-byte GET1 response does not prove the live interrupt report length or the physical Fn state; the parent's cached-query probe did not change with keypresses and cannot be used as an input trace. After the firmware candidate, verify actual map publication and a bounded plain/Fn key behavior check before making any broader claim.

## A89 physical follow-up: protocol works; initialization remains unresolved

Parent observations after A89: the exact892-byte extension is installed, native keyboard182 FeatureGET2 with capacity11 returns the expected11 bytes, but `FnFunctionUsageMap` remains absent. Raw22 FeatureGET2 is not a reliable test of the keyboard interface; manual raw FF selection was refused by macOS privileges. Native management GET90 still returns the correct percentage even though the widget disappeared after fresh pairing.

Two additional complete-wire emulator cases in `research/test_radio_keyboard_full_hidp.py` execute actual ROM14482→1602E→161E→D3E→142A8/1050E→1559A→E172. Direct HIDP`43 02` queues exactly`A3`+logical11; selector`53 FF 02` followed by`4B F1 00 02` queues exactly`A3 F1`+logical11. Management90 continues working afterward. Pool allocation/free, activity notifications and final L2CAP queue are modeled; over-air scheduling is not. This rules out the proposed hidden Feature2 dispatch bypass in the captured ROM; its special FeatureGET shortcut is IDFE, not02/F1.

The native V2 start function calls `initKeyboardConfiguration` unconditionally once the provider is valid (971330C–3328; vtable+B48 resolves9715EA4). It then continues and only subsequently queries keyboard-enabled state. Therefore Feature9 is **not** a prerequisite to this configuration request; adding Feature9 is not presently justified.

The512-byte buffer hypothesis also has contrary primary evidence. Apple IOHIDResourceUserClient response handling explicitly sets an IOBufferMemoryDescriptor's length to actual transferred bytes (pinned source lines930/950). A successful11-byte callback should therefore reach the parser as11 bytes, not512. The parent can discriminate runtime behavior with one native keyboard capacity512 query and compare returned length, without settings or firmware changes.

A specific remaining lifecycle hypothesis is shared request blocking: management F0 and keyboard F1 callbacks serialize through the same translator object's mutex+178. Management `handleStart` calls BluetoothInfo34 before BatteryState90. The known48-byte radio cap drops its79-byte HIDP response, so an outstanding34 request can delay both keyboard configuration and battery initialization. The V2 start path does not retry configuration after an error. However, the management code does **not** condition BatteryState90 on the34 return value; a delay is not proof of a permanent gate. Last selector34 before the manual probe is consistent with this hypothesis, not sufficient to establish it.

Discriminating read-only evidence: native `initKeyboardConfigurationGated`/GET-report timeout logs; per-user-client `GetReportTimeoutCount` and completion counts; `kblang-calibration` and `KeyboardLanguage`/`StandardType`/physical-design properties indicating which initialization branch executed. Do not replace the validated protocol with another guessed response while these distinguish a startup failure from a parser failure.
