# CYW Apple management profile: configuration and recovery findings

2026-10-28, offline only. This investigation reads the exact installed-radio captures and creates separate analysis fixtures. It does not change the installed A86, historical candidates, pairing state, or hardware. Parent owns the new firmware component/image and any future trial.

## Profile configuration is identified

The active HID report descriptor is **323 bytes at RAM 0x208773**. It is embedded in the application's compact SDP database at **0x2085E0..0x208993**, 947 bytes. The factory DS contains this database at EEPROM 0x2FEA; the captured, hash-checked A86 bank contains the same bytes at 0xAC2A. Config A3 is a key mapping table, not this descriptor.

The compact format is: service count byte; each service begins `7D attribute_count`; each attribute begins `D7 attribute_id_be16 length`, with a one-byte length except `FF` followed by a big-endian uint16 length. The database has three services with 9, 22 and 13 attributes, respectively. The middle service is HID; the last is DeviceID/PnP.

| Field | RAM value start | Factory EEPROM | Installed A86 EEPROM |
|---|---:|---:|---:|
| HID attribute0206 (nested descriptor-list element) | 208768 | 3172 | ADB2 |
| Descriptor bytes within0206 | 208773 | 317D | ADBD |
| DeviceID0201 vendor element | 208975 | 337F | AFBF |
| DeviceID0202 product element | 20897C | 3386 | AFC6 |
| DeviceID0205 vendor-source element | 208990 | 339A | AFDA |

Current DeviceID values are vendor05AC, product024F, vendor-source0002 (USB vendor namespace). The separate proposed Apple keyboard management profile uses vendor004C, product0267, vendor-source0001 (Bluetooth SIG/company namespace). Changing only the product would leave the vendor namespace inconsistent.

A clean ROM-supported override exists: **config TLV type BF**. Handler0x1CE90 sets `[0x202C64+8]` to the payload's EEPROM address, its uint16 length at+0C, and clears its cached allocation at+10. ROM0x17754 allocates and reads that payload when requested. The application constructor0x206838 calls0x17754 before setting up SDP; if the result is zero it uses the original literal0x2085E0 at0x206988, otherwise it passes the override to0x10670. Therefore no relocation of the original application data or original descriptor bytes is needed to supply an expanded SDP database. BF stores an EEPROM pointer during parsing, not the whole database in a fixed-size config buffer.

`private/apple-profile/analyze_sdp.py` reconstructs and round-trips every original attribute, validates the nested SDP elements, and emits a **data-only fixture**, not a firmware/update image:

- `baseline-sdp.bin`: 947 bytes.
- `proposed-sdp.bin`: 1030 bytes.
- `proposed-bf-record.bin`: BF header plus the 1030-byte payload.
- `sdp-analysis.json`: exact offsets, changed fields and hashes.

Only HID0206 and DeviceID0201/0202/0205 change. All 44 attributes retain their order; all other values remain byte-identical. The original323-byte descriptor is preserved as an exact prefix and the parent's observed83-byte Apple management descriptor is appended, giving406bytes. Every nested SDP length and the compact attribute length is recomputed.

**That append-only fixture is now historical, not the recommended trial descriptor.** It proves SDP construction and report compatibility but not host interface routing. Use the separately named grouped fixture below for the next offline A87 build; the old files remain unchanged.

The observed management descriptor has **two** top-level collections: FF00/0B with InputE0 and Input9A, followed by FF00/14 with Input90. Input90 is three status bits, five padding bits and an eight-bit percentage. Feature34 is not declared in those83bytes, despite the parent's successful physical GET; do not assume declaring it is a prerequisite. The original K2 descriptor declares IDs01,02,08,03,04,FF,0C,B1,B2, so the appended E0/9A/90 do not collide. The isolated0x90 byte at config200438+8 is not a report-ID declaration; its independent config meaning was not assigned here.

## Host interface grouping: concrete candidate and remaining experiment

Appending collections alone can leave all reports on one IOHIDInterface. A matching management driver could then take the combined keyboard interface. Conversely, simply enabling multiple interfaces splits every root Application collection, including separating Input90 from the FF00/0B management interface. Neither is the intended layout.

The Apple source `IOHIDDevice::supportsMultipleInterfaces` enables grouping when the first collection has Apple's multiple-interface usage and no explicit overriding property. `mapElementsToInterfaces` removes that marker and creates one interface per remaining root Application collection. `IOHIDElementContainer::createFlattenedCollections` recursively includes all descendant elements under each root Application. `IOHIDDevice` then routes input reports to interfaces containing their report ID. The reviewed current kernelcache confirms the marker is **usage page FF00, usage1A**, and the property is `MultipleInterfaceEnabled`; this numeric marker is not guessed from the public header. Disassembly is saved in `private/apple-profile/interface-routing-disassembly.txt`.

Matching also follows these groups: `IOHIDDevice::publishProperties` derives each interface's usage pairs and primary usage from that interface's elements. `IOHIDInterface::matchPropertyTable` matches its own properties when `MultipleInterfaceEnabled` is true; otherwise it delegates to the parent device. The current binary confirms that branch at0xFFFFFE000AD4A070, with the true path at0xFFFFFE000AD4A1D0 calling `MatchPropertyTable(this, ...)`. Additional disassembly is `private/apple-profile/interface-matching-disassembly.txt`. Thus the proposed marker provides both report routing and interface-specific driver matching, provided the descriptor reaches this kernel layer intact.

Primary source: [Apple IOHIDDevice.cpp](https://github.com/apple-oss-distributions/IOHIDFamily/blob/777ccd9698845aadf711e32d843c8c9b777431d9/IOHIDFamily/IOHIDDevice.cpp), alongside the downloaded `IOHIDElementContainer.cpp`. The actual installed binary corroborates the relevant grouping behavior; public source alone is not treated as proof of its version.

The concrete revised descriptor is **429 bytes**:

1. Empty Application marker: `06 00 FF 09 1A A1 01 C0`.
2. Outer Generic Desktop/Keyboard Application: `05 01 09 06 A1 01`, original323bytes unchanged, `C0`.
3. Outer Apple FF00/0B Application: `06 00 FF 09 0B A1 01`, observed83management bytes unchanged, `C0`.

Under the reviewed kernel grouping rule, the marker produces no interface; the first real interface contains every original K2 report, and the second contains E0/9A/90 together. Nesting preserves both original descriptor byte strings and all report fields while intentionally changing their collection ancestry. This also preserves the original grouping of keyboard, consumer, system and diagnostic reports instead of unnecessarily splitting the K2 into numerous interfaces. Feature34 remains serviced by GET_REPORT independently of its absence from the observed descriptor, as in the reviewed Apple implementation.

`private/apple-profile/build_grouped_fixture.py` is a reproducible, stdlib-only structural/equivalence check. It checks balanced collections, all field globals/local usages/counts/sizes/flags, original323-byte and observed83-byte exact substrings, disjoint interface report IDs, Input90's16payload bits, and nested SDP length roundtrips. It writes separate data-only artifacts:

| File | Bytes | SHA256 |
|---|---:|---|
| `grouped-descriptor.bin` | 429 | `33b270e5ee2639a049ae19ef44dc9b8bc40ff2ecabde88269faf519622dfbb86` |
| `grouped-sdp.bin` | 1053 | `6d7bbbf0b7db0837ddb3819fe978607460b40f5ecf00695e4d77f9c630ed1813` |
| `grouped-bf-record.bin` | 1056 | `2639e809c89d583beedd5c74c76ac867ed7a0bed09d0ffdef60f117ccb545c31` |

**The remaining host behavior is a bounded trial question.** Saved registry metadata shows the actual Magic Trackpad2 already arrives as five separate IOHIDUserDevices, with descriptors22/83/110/36/27bytes. The83-byte management device has primaryFF00/0B and no multiple-interface property. Therefore an earlier host component partitions the real Apple device before the kernel rule above; the metadata does not reveal the exact Bluetooth preprocessing algorithm. Sanitized extraction is `private/apple-profile/trackpad-grouping-metadata.json`. The grouped429-byte fixture is a deliberate compatibility experiment, not a claim to reproduce Apple's physical descriptor or its preprocessing exactly.

This uncertainty does not require guessing another PID or indefinitely expanding offline research. After the separate neutral-profile rollback preflight succeeds, the explicit two-group profile is a defensible one-boot experiment with native laptop input available. Inspect resulting IOHIDUserDevice/IOHIDInterface/driver grouping, keyboard/media operation, Input90 delivery and native battery publication. If Bluetooth preprocessing removes or splits the groups differently, stop the profile trial and retain the working A86 fallback. The fixture has not executed Apple's HID parser or created any host/device interface.

## Dispatch and address source

The root app table208D04+28 points to ROM0x161F. Its fallback0xD3E asks the battery object's getter at vtable+0C, then delegates unsupported requests to the updater. Thus extending the battery getter for Input90 and Feature34 can preserve the root handler and updater unchanged. Parent has independently tested this route through the actual ROM dispatch.

The battery object's **bytes+6..+11 already contain the local Bluetooth address in displayed order**. Application206900 calls connection getter14CA0, which returns connection+44, and passes this to constructor27E0; ROM284C..2852 copies six bytes to battery+6. Saved RAM matches this to reversed SS type40 bytes, and the result matches the K2 SerialNumber order in the saved HID registry. No address is printed here. Config40's global205E54 uses the opposite byte order, so using it directly would be wrong for Feature34.

Independent review of the current152-byte-allocation `firmware/radio_apple_component.S` found no blocking ABI, bounds, offset or send-order bug. Feature34 writes complete-report offsets4..9 correctly and returns77bytes. Input90 returns3bytes. Table publication happens after initialization; normal report3 remains and unsupported reports delegate. Eight parent component test methods also passed independently. These tests model allocation/transmission and do not establish on-air behavior or native UI eligibility.

The requested stdlib-only protocol fixtures are in `research/apple_management_fixture.py` with five passing test methods in `research/test_apple_management_fixture.py`. They cover the exact83-byte descriptor, all101 percentages and eight declared status combinations, Feature34/address ordering, and malformed lengths. They contain no HID/device APIs.

## One-boot recovery: what is proved

Normal ROM entry0x1C798 initializes I2C through0x2C6B6 and EEPROM geometry through0x2C91C **before** parsing DS. Geometry initialization selects a16-byte boundary. TLV0A loads RAM immediately; TLV0B invokes its target immediately via0x29F30. Therefore a first-record0A+0B prefix can run before new profile/BF records are applied. Its temporary code can be overwritten by the later normal application/extension load after it has returned, provided no live callback pointer remains.

If SS0 is invalidated successfully, the already-running parser keeps its current DS cursor, so this boot can continue the prototype. The next normal boot can select SS100 pointing to the working A86 bank8000. Host-side staging must verify that backup selection and the whole A86 bank before committing a prototype. This is a recoverable one-boot design under successful EEPROM operations, not yet a physically validated boot writer.

**Returning failure from0B does not stop loading.** At1CDD4 the target is called, then execution unconditionally continues at1CD16. Actual-ROM regression verifies return values0,1,2,4,255 all continue to apply the following BF record.

A supported parser-control mechanism can redirect a recoverable failure:

1. Prefix arms function pointer `[0x200C80]`.
2. For the next record, parser1CC92..1CCA8 calls it with R0=type, R1=full length, R2=temporary prefix buffer, R3=EEPROM payload address. This is before default config application.
3. The one-use hook clears its own slot, sets selected DS base `[0x205E1C]=0x8000`, and returns0x8000.
4. A nonzero hook return is interpreted as the **next TLV address**, so the outer parser starts the unchanged A86 bank. Updating205E1C is necessary for relative config-record bookkeeping; changing only the parser cursor is incomplete.

`private/apple-profile/redirect-proof.S` and `test_recovery_order.py` prove this using the actual ROM scatter initializer and config parser, modeled EEPROM reads, original A86 DS and actual final A86 boot hook. The new BF never becomes active; A86 marker, constructor hook, extension and arena are restored. The callback is cleared before A86 overwrites the temporary code. Two test methods pass. The emulator must invalidate translated code after modeled RAM-load writes because the same RAM address first holds temporary prefix code and later A86 code; the test explicitly does so. No EEPROM writer is present in this proof.

## One-boot recovery: the remaining real boundary

The ordinary ROM EEPROM writer is unsuitable for a fail-closed boot guard without more work:0x2C822 waits indefinitely for controller completion and0x2C94C repeatedly ACK-polls without a bound. An early stalled writer can prevent Bluetooth startup. An unchanged-A86 identity trial is useful, but does not magically remove this risk from the first boot-writer test.

A concrete bounded alternative is available for implementation and review: ROM0x2C754 starts a small transaction without polling; ROM0x2C6FE returns pending0, error3, or completed1 and is bounded for controlled transfer lengths. The latter's only loop copies the configured received-byte count. Calling these with a shared finite poll budget avoids the blocking wrappers. A single-byte invalidation uses EEPROM address00:00 and data00; a separate readback must begin with a nonzero sentinel and require completed status plus an exact zero byte. The ACK probe should send two address bytes with no EEPROM data, matching the established ROM poll's transaction shape, rather than assume a zero-length controller transfer is valid. Parent is developing that separate guard; it is not implemented by this report.

Subsequent independent review of the parent's implemented guard found no new blocking ABI/frame issue, and the latest `research/test_radio_one_boot_guard.py` passed five methods, including periodic watchdog servicing. The actual I2C initializer finishes with201021=00: although2C6B6 first writes10, its tail path through2C67A clears that bit. The earlier suggestion that normal initialized control must retain10 was incorrect and was withdrawn before trial. The tests execute that initializer rather than seed the mistaken value. These remain offline results with modeled controller completions and EEPROM reads.

A bus timeout remains different from an ordinary NACK/readback failure. The fallback DS reader itself uses blocking I2C. After timeout, redirecting to8000 only works if the controller/bus is readable again. Resetting the I2C block through its normal initialization may recover a controller state, but the physical effect after an incomplete transaction has not been established here. A physically stuck bus cannot be made safe by a parser redirect alone.

Recommended bounded progression: complete offline tests of the async guard's actual ROM/MMIO path, error/timeout/readback branches and supported redirect; then validate the one-boot prefix on the **unchanged working A86 profile**, including the next power cycle selecting the fallback. Only after that should the Apple profile use the same reviewed prefix. An independently tested EEPROM restore path is a stronger safeguard against a corrupted early callback or persistent bus failure, but it is not a logical requirement of Apple reporting itself. No current evidence supports calling the unbounded writer safe, promising the first prefix trial cannot require physical recovery, or treating an emulator's readable-bus fallback as physical recovery proof.
