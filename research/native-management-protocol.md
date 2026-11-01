# Native battery management protocol: evidence and a host-only proof

Status: offline investigation, 2026-10-28. No device queries, virtual device creation, pairing changes, firmware changes, registry writes, or operating-system modifications were performed in this investigation. The working A86 radio battery component is unchanged.

The most useful next proof is a temporary **battery-only virtual management interface** serving a real battery percentage, with its Bluetooth-address report associating that interface with the K2. This can test the missing macOS publication path without changing the keyboard. It is a conditional proposal, not an implemented or proven solution: creation requires an accepted virtual-HID entitlement; matching the existing Apple driver also requires its matching properties, and the Bluetooth daemon may impose a separate eligibility condition. Merely adding FF00/0B or setting BatteryCapacity is not equivalent to this protocol.

## Evidence quality and provenance

The primary implementation evidence is the actual AppleDeviceManagementHIDEventService machine code from an existing, locally installed Apple kernelcache. The compressed IMG4 payload was decoded offline with Apple's libcompression LZFSE decoder. The decoded kernel identifies itself as Darwin 27.0.0, xnu-13432.1.9~1, RELEASE_ARM64_T6041. This is evidence for this installed cache; it is not a promise about all macOS releases or independently verified live kernel load addresses.

Decoded SHA-256: `753f8c8cf712ed2250feeb813096a5b8645844c2c5bb0a895d34c84c09d88916` (125829120 bytes). Private source path and original compressed hash are in `private/apple/management/kernelcache-provenance.json`. The embedded driver has symbols, allowing function identification rather than guesses from strings. Annotated instructions, symbols, matching personalities and analysis scripts are in that directory. The vtable's chained-pointer targets resolve to the named methods used below.

Independent corroboration: a [Linux driver author's battery patch](https://lkml.rescloud.iu.edu/2105.1/04331.html) uses input report 0x90 for Magic Trackpad 2/Magic Mouse 2. Apple's binary is stronger evidence for the macOS contract and supersedes any assumption that generic Feature report 6 supplies it.

## Exact battery contract recovered from Apple code

Addresses below are unslid addresses in the decoded cache, not live addresses.

| Operation | Proven implementation |
|---|---|
| Initial battery query | `getBatteryState` at `0xfffffe000a176aa0`: `simpleGetReport(0x90, buffer, &length, 0)`. IOKit report type 0 is **Input**. Initial buffer capacity is 512. It retries failure up to five additional times. |
| Report-ID handling | `simpleGetReport` at `0xfffffe000a178978` gets the report through IOHIDInterface, subtracts one from returned length, and copies from byte offset 1. The callback/underlying HID report therefore includes the report ID. |
| Battery payload | `processBatteryState` at `0xfffffe000a176c1c` requires at least two bytes after the ID. Payload byte 0 becomes `BatteryStatusFlags`; payload byte 1 becomes `BatteryPercent`, each stored as an 8-bit numeric property. |
| Asynchronous updates | `handleInterruptReport` at `0xfffffe000a176618` copies bytes after the ID; ID 0x90 dispatches to the same battery parser. No separate battery enable handshake is visible on this path. |
| Publication | When status or percentage changes, it calls `sendBatteryStatusChangedNotification` at `0xfffffe000a176f70`, which first obtains Bluetooth info and sends client message `0x62747374` (ASCII `btst`). This is stronger than setting a number on an unrelated HID service. |
| Additional status handling | Status bit 4 invokes `sendCurrentBatteryPercentNotification`; the exact meanings of all other bits are **not** established here. Do not invent charging/error flag assignments. The parser also invokes its low-battery notification method. |
| Resume | `_resumeFromSleepGated` asks for the battery again when the service is external and has a battery, and queries critical-error/wake-reason information. |

For percentage 87, a host HID callback or injected input report supplies **`90 SS 57`**, where `SS` is the status byte. For an offline protocol fixture, `00` is usable as an explicitly synthetic status with no asserted charging semantics. The Classic HID wire-level distinction remains important: an input GET_REPORT uses HIDP report-type 1 (e.g. `41 90` without a buffer-size field); IOKit uses enum 0 for input. The virtual-device API takes the HID report, **not** the HIDP header.

The parser itself does not clamp percentage to 100. A publisher must validate 0–100 and must not publish a stale value as fresh. This investigation establishes the host parser; it does not validate the K2's ADC percentage accuracy.

## Bluetooth association is a separate, exact report

`getBluetoothInfo` at `0xfffffe000a177008` requests **Feature 0x34** (IOKit enum 2). It requires precisely **76 payload bytes after the report ID** and payload byte 0 equal to **3**. In other words, the complete HID report has 77 bytes:

| Complete report offset | Meaning used by this Apple implementation |
|---|---|
| 0 | Report ID `34` |
| 1 | Structure version `03` |
| 2–3 | Little-endian Bluetooth firmware-version value, published as `BTFW Version` |
| 4–9 | Six Bluetooth-address bytes, in the order formatted as `%02x-%02x-%02x-%02x-%02x-%02x` |
| 10–76 | Remaining structure bytes; not read by the reviewed function, but required by its exact length check |

The six bytes are published as `BD_ADDR` data and a hyphenated `DeviceAddress` string. A successful result sets an internal obtained-info flag. A wrong version/length logs an error and leaves it eligible to retry. This is not a cryptographic authentication exchange. It supplies the association consumed by the separately investigated host Bluetooth battery lookup.

For a host-only proof, these bytes must refer to the **K2's own address**, read from an already authorized saved source, not the Trackpad's address. No real address is printed in this report. A fabricated unrelated address cannot prove association with the K2.

## Startup and matching requirements

The reviewed `handleStart` opens its IOHIDInterface and registers its report callback. It queries firmware versions and hardware ID; on the external-device path it reads `BluetoothDevice` and `HasBattery` from its personality, queries Bluetooth info and battery when appropriate, then initialization/error information and device color. `start` also asks for the wake reason. These other queries are useful to log in a prototype:

| ID | IOKit type | Observed interpretation |
|---|---|---|
| `BB` | Feature | Firmware-version records; failed request falls back to `B4`. |
| `B4` | Feature | Legacy firmware version, two payload bytes. |
| `BC` | Feature | Hardware ID, two payload bytes. |
| `E0` | Feature | Critical-error value, four payload bytes. |
| `C5` | Feature | Wake reason, one payload byte; a separate setter exists for the same report. |
| `14` | Feature | Device color, one payload byte. |

In the reviewed startup caller, failures of the informational query methods do not cause a branch to attachment failure. A minimal proof should initially return a clear unsupported result for unimplemented requests, record each request, and serve only the proven battery/address contracts. It should not fabricate large Apple firmware-information structures. It must handle callbacks promptly so an unsupported request does not become a timeout. `simpleSetReport` uses Feature type and prepends the report ID; there is no observed mandatory SET_REPORT enabling battery 0x90 in the reviewed startup path. This is not an exhaustive contract for every Apple personality or transport.

The installed `Keyboard DM - BT - External` personality matches:

- Provider class `IOHIDInterface`.
- Usage page `FF00`, usage `0B`.
- Vendor `004C`, product array containing `0267`.
- Personality properties include `BluetoothDevice=true`, `HasBattery=true`, `Built-In=false`, and `HIDServiceSupport=true`.

The Lightning Trackpad counterpart matches vendor `004C`, product `0265`. USB counterparts use vendor `05AC`. These IDs are **matching facts, not a recommendation to change the K2's radio identity**. All 33 installed management personalities were collected: the sole one without a vendor filter is explicitly the internal FIFO keyboard/trackpad personality, not a generic external battery fallback. Therefore adding FF00/0B to the K2's existing identity is insufficient to match these external personalities.

No cryptographic challenge or authentication check was found in the reviewed management startup/battery/address functions. That limited result does not prove the entire Bluetooth stack accepts an emulated Apple device. Parent investigation covers the separate bluetoothd eligibility gate. Apple-specific matching, unrelated driver attachment, daemon classification and virtual-device treatment remain distinct questions.

## Virtual-HID feasibility and its real privilege boundary

[Apple's IOHIDResourceDeviceUserClient source](https://github.com/apple-oss-distributions/IOHIDFamily/blob/777ccd9698845aadf711e32d843c8c9b777431d9/IOHIDFamily/IOHIDResourceUserClient.cpp) requires `com.apple.hid.manager.user-access-device` or `com.apple.developer.hid.virtual.device` in `initWithTask`. The private entitlement marks the client privileged. There is no root-user fallback in that function. The same entitlement branches are present in the decoded local kernelcache at `0xfffffe000ad8f388`; this is not merely a potentially stale source inference. The local macOS 27 SDK header also documents the developer entitlement for creation.

[Apple's IOHIDUserDevice source](https://github.com/apple-oss-distributions/IOHIDFamily/blob/777ccd9698845aadf711e32d843c8c9b777431d9/IOHIDFamily/IOHIDUserDevice.cpp) forces ordinary developer-created devices to `Virtual=true` and `Transport=Virtual`; overriding transport requires the private privileged route. The actual local `newTransportString` at `0xfffffe000ad1e680` confirms that behavior. An ordinary plist property cannot elevate this privilege.

Consequences: **sudo alone is not a justified plan**. A legitimately signed publisher with an accepted developer entitlement is the appropriate candidate. Whether this user's signing environment can obtain/use that entitlement has not been checked. Ad-hoc signing acceptance must not be assumed, and disabling OS protections is not proposed. An entitled Virtual-transport device might still match the external management personality, because that personality has no Transport match, but successful binding and battery association are unproved. Its virtual identity must remain honest; no transport-privilege bypass is necessary for the proposed test.

## Concrete next nonflash experiment (not executed)

1. Build a small, separately scoped host publisher, with the accepted virtual-HID entitlement verified before running it. Use delayed activation and install GetReport/SetReport callbacks before activation. No Bluetooth or USB handles to the keyboard are needed for the initial constant-value proof.
2. Create **only** a vendor management application collection (`UsagePage FF00`, `Usage 0B`), input report 0x90 containing two bytes, and Feature report 0x34 containing 76 bytes. No keyboard, mouse, touch, consumer-control or output usages; no synthetic typing.
3. A control with the existing K2 matching identity should establish whether it stays generic. A separately approved matching test can use the management driver's external-keyboard matching properties **on the temporary host object only**, while its address report associates it with the real K2. That is an explicit protocol-emulation experiment, not a hidden PID-only change to the physical keyboard.
4. Supply the exact known current percentage as a labeled test value, and log all host requests. Observe whether AppleDeviceManagementHIDEventService attaches, receives 0x34 and 0x90, publishes `BD_ADDR` plus `BatteryPercent`, and sends the status notification. These are separate acceptance checkpoints.
5. Only after those pass, check the native Bluetooth UI for the existing K2. If the properties appear but the UI does not, the remaining failure is the host eligibility/association path, not battery-report encoding. If the driver does not attach, stop at matching/virtual-device treatment; do not flash another radio image.
6. Destroy the temporary virtual device at process exit. Do not install a daemon or continuous reader until the native-UI proof succeeds. A production bridge would require live validated K2 samples and lifecycle/reconnect handling; a constant published test value is not a finished battery monitor.

This is the best bounded experiment because it can distinguish protocol, driver binding, and UI eligibility without risking another EEPROM update. If the entitlement or virtual-device gate blocks it, that is a concrete host-side constraint. A firmware management interface remains technically possible in principle, but would still need Apple matching treatment and complete host eligibility evidence; the present findings do not justify flashing one.

## Subsequent offline finding: the host-visible interface is translated

The preceding report describes the **IOHID-facing contract**, not a proven physical Bluetooth wire protocol. Further static analysis of the installed `/usr/sbin/bluetoothd` establishes an intervening translation. This section records offline analysis only; physical A87 observations are maintained by the parent investigator separately.

The management-interface creator at `0x100744464` constructs an83-byte report descriptor from constant `0x10095CC8A`, overriding its final four bytes with `65 81 02 C0`. The resulting83 bytes are **exactly equal** to `private/apple/trackpad-management-report-descriptor.bin`. It labels this virtual interface with keyhole ID `F0` at object+1C8 and registers GetReport callback `0x10074493C`. That callback dispatches object.vtable+70; the corresponding table `0x100B55230` resolves that slot to `0x10059C708`. Two other reviewed management creators also resolve their getter to this implementation.

`0x10059C708` is identified by its own logging text as `getReportWithKeyhole`. Its actual steps are:

1. Save the caller's requested report ID and capacity.
2. Execute block `0x10059CA28`: submit a **Feature SET_REPORT FF**, with two bytes `[FF, requestedReportID]`, via the underlying transport's setter. The transport report type is3 (HIDP Feature), not IOKit enum2.
3. Only after that succeeds, allocate requestedCapacity+1 and execute block `0x10059CA88`: GET the interface's keyhole report ID, `F0` for management, using the requested type converted from IOKit to HIDP by adding1.
4. Require a returned length between2 and the allocated capacity. Strip the first returned byte, copy the remaining bytes to the original caller and reduce returned length by1.

Consequently, a host-visible77-byte Feature34 reply corresponds, on this path, to an underlying78-byte response `[F0, 34, 03, ...]` after selecting34 using `[FF,34]`. This is **not** evidence that bluetoothd fabricates all76 payload bytes itself; the reviewed implementation obtains the bytes from the underlying transport. It is equally not evidence of a direct physical GET_REPORT34. The exact classifier that selects this translation for a newly paired K2 remains outside this finding.

Input notifications use another path. At `0x100743D04`, report90 falls through a constant report-ID routing mask to the virtual interface associated withF0. At `0x100744074..080`, bluetoothd passes the **original input buffer and length** to `IOHIDUserDeviceHandleReportWithTimeStamp`. It does not prepend or remove a keyhole byte on this reviewed unsolicited input path. Thus direct `[90,status,percent]` notifications and tunneled GET90/GET34 can coexist.

The selector GET pair is serialized under a pthread mutex at the bridge object's+178: getter59C708 enters301514→3014B0→301408→pthread_mutex_lock before either transfer, and unlocks through3015A0 during final cleanup. The translated setter59CAC0 uses the same mutex. An independent raw-report client does not automatically participate in this outer transaction lock; the generic transport uses another lock at+40. Firmware should not assume arbitrary external FF writes cannot interleave, nor retain a previously valid selector after an unsupported selector is received. A bounded minimal implementation can reject unsupported selectors and ensure subsequent F0 GET cannot disclose stale34/90 data. Existing K2 updater report IDs must retain their original behavior.

The exact original radio SET_REPORT parser at144F4..14564 strips the HIDP header and the report-ID byte before calling application.vtable+2C. A two-byte complete Feature report `[FF,34]` reaches that root method as R0=application, R1=connection, R2=3, R3=FF, stack[0]=pointer to the single selector byte34, stack[4]=1, stack[8]=0. The existing206AD4→DCC→2066A4 handler accepts Feature report IDs70,71,73,74,75 and returns2 for FF. The new selector interception therefore must recognize this **one-byte root-method payload**, not look for a second FF byte there. Its unsupported/wrong-type/wrong-length paths must preserve the original updater handler.

### Existing raw virtual interface can expose diagnostics

The22-byte FF00/12 device is different from the translated management interface. Creator59C3C4 uses descriptor constant10095B926, bytes `0600ff0912a1018501050075019503150025018102c0`, SHA-256 `72b22e181a2666679b2de4fabc93185f5149274fa1af75fd1842daed12bfe5da`. This exactly matches the corresponding descriptor in the saved Trackpad registry tree. The creator registers generic getter callback2BE758→2BEA64 and setter2BE75C. It does **not** register the keyhole callbacks.

The generic GET callback checks for non-null buffer/length, stores the caller's buffer pointers, converts IOKit report type to HIDP by adding1, and forwards the caller's report ID unchanged through the underlying transport. The examined callback has no report-ID allowlist. Thus this already-present FF00/12 interface is a concrete candidate for read-only diagnostic GET71/72, even though B2 is absent from its descriptor. Matching must use exact target identity/address plus this descriptor hash; it must not select the owner's Trackpad. Actual kernel admission, privilege and transport behavior remain physical-test questions. This analysis did not send a request or instantiate a device.

`research/test_apple_keyhole_host.py` executes the actual ARM64 bridge blocks offline: all256 selectors produce Feature FF with exactly `[FF,selector]`; the three IOKit types convert to their corresponding HIDP types for F0; raw diagnostic IDs are preserved; and both4-byte `[F0,90,status,percent]` and78-byte `[F0,34,...]` responses lose exactly the first byte. Four test methods pass. Authentication instructions are neutralized only in the emulator copy, transport calls are observed rather than executed, and memcpy is modeled. These tests do not prove native client admission or physical Bluetooth transfer success.

This matters for the prototype: implementing only direct radio getters34/90 does not implement the full translated Apple path. Any future FF-selector/F0 implementation must first preserve the K2's existing FF report semantics and updater reports, validate report types and lengths, and confirm which host path actually binds after SDP rediscovery. An old generic host's failed direct GET34 alone does not identify a77-byte firmware transport defect. Annotated instructions are saved in `private/apple-profile/daemon-keyhole-disassembly.txt`; the static Mach-O reader is `inspect_daemon_management.py` in the same directory. No host virtual devices, callbacks, or device requests were executed by this analysis.

## Native Apple parser check of the grouped descriptor

The local user IOKit framework did not expose the HIDOpenReportDescriptor parser symbol. Instead, the unmodified public Apple HID parser source was compiled in its existing userspace allocation mode from IOHIDFamily commit `777ccd9698845aadf711e32d843c8c9b777431d9`. See [Apple's HIDOpenCloseDescriptor.c](https://github.com/apple-oss-distributions/IOHIDFamily/blob/777ccd9698845aadf711e32d843c8c9b777431d9/IOHIDSystem/IOHIDDescriptorParser/HIDOpenCloseDescriptor.c).

Both normal flags0 and strict flags1 accept all three file buffers: original K2 descriptor323 bytes, observed Trackpad management descriptor83 bytes, and grouped A87 descriptor429 bytes. All six opens and closes return0. This removes a concrete source-parser rejection concern about the nested Applications; it does not prove current kernel interface grouping or bluetoothd classification. Source hashes, compile command, descriptor hashes and results are reproducible through `private/apple-profile/native-parser/check_descriptors.py` and its `results.json`. These tests instantiate only parser data structures in the test process, with no IOHID device creation or host changes.

## A88 long-reply failure: configured48-byte packet ceiling

The parent reports native Input90 now succeeds through the Apple translator and the owner sees the native battery widget. Feature34 remains unsuccessful. The following independent analysis is offline; the parent's current read-only confirmation is recorded in `artifacts/k2-initial-release/A88-live-control-MTU.json`.

The reply path is: root161E→D3E obtains the report and copies it into a size-aware GKI allocation; control GET handler160B2..CE copies/sends via connection.vtable+2C→1050E→143BA→155E8→1559A. The latter prepends one HIDP DATA header. Control-channel send129E6 chooses the live channel, whose send110D4 callsC32C→E172. E172 resolves the CID withEE32, compares packet.length against channel control-block+3A and **frees the packet and returns0 if oversized**. No segmentation occurs on this path. The upper GET handler160C4 ignores that send result and still frees its intermediate report buffer, explaining a missing reply rather than a useful error response.

Historical captured controlCID4B has control block202AB0 and outgoing limit48. The parent's fresh A88 check independently confirms currentCID41/control block2025D8 and limit48. The global limit2007D2 is also48. Direct report34 has77 report bytes plus one HIDP byte; keyholeF0/34 has78 report bytes plus one HIDP byte. Both exceed48. Their allocations,98 and99 bytes respectively, fit the existing284-byte GKI pool; allocation size alone is not the identified failure.

The control-block formula is `20255C + (CID-40)*7C`, valid only for in-use CIDs40..4B. Outgoing peer receive limit is at+3A; local receive limit is at+38. ROM EED4 accepts peer MTU configuration, enforces a minimum48, and clamps the outgoing value to the global uint16 at2007D2. The separate local configuration routineEF70 clamps the requested local receive value by the same global maximum. The immutable per-HID template at4AEF8 requests48, so increasing the global cap to128 leaves that template and the resulting local HID receive MTU at48.

**The global field is shared, not OUT-only.** All identified direct consumers of the2007C8 configuration base are:

| Site | Meaning |
|---|---|
|7062..86|Initializes two GKI pools from size/count fields+2/+4 and+6/+8; does not use cap+0A.|
|A3A4→FDE0|Passes cap+0A into HCI opcode0C33's ACL packet-length field; other arguments are30,20,10.|
|D706..10|Bounds accumulated incoming ACL/L2CAP reassembly by cap+4.|
|D8A6|Uses byte+0C, a separate parameter, unchanged by a two-byte cap override.|
|ED02..0C|Places cap+0A into an L2CAP information response.|
|EEEE..EF00|Clamps peer MTU and outgoing control-block+3A.|
|EF80..8A|Clamps local receive control-block+38.|

A full ROM/RAM literal scan finds these five executable configuration-base literals plus the loader-table entry4D2EC, and no additional pointer directly inside2007C8..2007D4. This is a static-reference audit, not proof that no dynamically calculated reference exists.

Incoming ACL handlerBB74 is size-aware: BC12..16 calls GKI70B6 with required length+12. It does not unconditionally use the68-byte pool. Actual captured GKI allocator execution confirms requests99,140,148 select the284-byte pool. A128-byte global cap consequently broadens stack/controller-level receive handling, but does not advertise a672-byte HID receive buffer or enlarge the pool. The existing four large buffers remain a finite resource; the emulator tests establish size fit, not a physical stress/availability guarantee.

The generic DS loader maps TLV AC to2007C8 with maximum13 bytes. The captured active DS has noAC override. Rather than replacing all13 configuration bytes from a live snapshot, an offline nine-byte0A record (`0A 06 00 D2 07 20 00 80 00`) writes only the cap halfword at2007D2 during initialization. In the offline fixture it is placed before the final boot callback. No candidate image is saved or changed by this test.

`research/test_radio_mtu_cap.py` passes five actual-ROM tests: peer MTU values48/79/128/672 clamp correctly at global48/128; unchanged local template still produces receiveMTU48; send rejects report+HIDP lengths above the actual channel limit and accepts those fitting it; existing GKI pool selection accommodates99/140/148-byte requests; and the two-byte initialization override survives real ROM scatter/pre-DS/DS loading while preserving every other configuration byte. Controller queues/transmission, critical-section primitives and EEPROM hardware remain modeled. A changed cap still requires a subsequent connection negotiation; writing only the global word on an already-connected device would not repair its existing channel+3A limit.

The proposed direction is a bounded128-byte configuration ceiling, **not DATC fragmentation**. Bluetooth HID1.1.1 deprecates DATC and says implementations shall not send it; it also requires Report-mode hosts to support an MTU of at least672. The actual ROM has a48-byte configured clamp despite historical application Report mode1. See the saved primary HID1.1.1 specification sections3.1.2.3,3.1.2.10 and5.2.3.1. The static failure and live channel cap establish why the long reply is dropped; they do not establish that a future cap change alone fixes every host presentation detail.
