# Native macOS battery integration after A86

2026-10-28. Bounded static assessment; no device calls, firmware changes,
descriptor changes, identity changes or host-setting changes.

## Present evidence

The parent reports verified A86 installation, a persistent matching extension
and shadow vtable, and standard battery reports tracking the internal estimate
from86 to87 while charging. The parent also reports no native battery UI after
fresh pairing/cold boot. A temporary BatteryCapacity service property persisted
across separate clients but did not produce that UI; reconnect/re-pair removed
the temporary properties. These are parent-observed hardware results, not new
observations by this advisor.

The remaining gap is therefore host recognition/publication, not evidence that
the corrected percentage cannot cross Bluetooth. A standard HID report, an
IORegistry/HID-service property, and a Bluetooth UI battery item are distinct
stages. Passing one stage does not prove the next.

## What the installed Apple implementation actually specifies

The installed AppleBluetoothHIDKeyboard Info.plist has explicit legacy keyboard
personalities. For example, Wireless Keyboard2009 B ANSI matches vendor0x05AC,
product0x0255, providerIOBluetoothL2CAPChannel, PSM17. Its ExtendedFeatures maps
BatteryPercent to report **0x47** (decimal71), IOKit type2/Feature, size1 and
range0..100. BatteryState uses input report0x30. The same personality also
describes naming, user-mode, shutdown and factory-default operations.

That is direct Apple-shipped configuration evidence for a legacy route; it is
not proof that this legacy kernel-driver personality is active or sufficient on
the present macOS Bluetooth user-space transport. In particular, changing a PID
does not by itself prove driver attachment or safe protocol compatibility.

The Lightning Magic Keyboard uses a different installed personality:
AppleDeviceManagementHIDEventService, providerIOHIDInterface, Bluetooth vendor
0x004C/product0x0267, and vendor-defined usage page0xFF00/usage0x0B. The Lightning
Magic Trackpad2 personality similarly matches0x004C/0x0265 and that management
usage. Both advertise HasBattery and HIDServiceSupport. These exact personality
matches are stronger evidence than assuming any standard battery field selects
the management driver. Their presence does not reveal the complete management
report framing, initialization sequence or any additional runtime probe.

No primary evidence found in this bounded inspection establishes a universal
AppleWirelessKeyboard **Feature report6** that can simply be added to the K2 to
obtain native UI. Report numbers are scoped to a descriptor/device protocol.
The verified legacy example is0x47; modern management is a separate contract.

Static inspection of the installed bluetoothd already identifies a BatteryPercent
lookup through IOAppleBluetoothHIDDriver, AppleDeviceManagementHIDEventService or
IOBluetoothHIDDriver, using BD_ADDR to associate the accessory. Its fallback
function0x100524AB0 enumerates HID services, associates SerialNumber and reads
BatteryCapacity. Crucially, caller0x100523858 first invokes eligibility function
0x100520F50. The latter references BluetoothFeatures/GameControllerBlockListRemoval,
HID/EnableGamepads, a device-flag mask and a gamepad-authentication log message.
This is not an unconditional fallback for every keyboard with BatteryCapacity.
Exact live K2 eligibility is unproven; the failed property experiment is consistent
with this gate. It does not establish which individual condition failed.

## Next routes and requirements

1. **Finish host selection analysis before another firmware change.** Determine
   the live-stack selection rules for an Apple-compatible battery publisher and
   the meaning of the fallback's device flags. Inspect the management driver or
   user-space counterpart's report parser to establish report ID, type, length,
   fields and initialization requirements. The UI's refresh/publication trigger
   also needs proof. This work can initially remain static and read-only.
2. **Firmware compatibility emulation is a separate possible project.** A
   legacy0x47 battery endpoint looks smaller than the modern management protocol,
   but requires a demonstrated host-binding path first. If it requires another
   vendor/product identity or proprietary management collection, that change
   should be discussed explicitly. Inventory every initialization/get/set
   command that the selected driver may send; preserve normal typing, existing
   diagnostics, and recovery. Do not assume an Apple-looking identity plus one
   percentage byte constitutes compatibility. No such change is proposed here.
3. **A host publisher would need a supported publication/association path.**
   Merely rewriting BatteryCapacity has already failed this device's observed
   native-UI test. A custom driver or privileged/private Bluetooth integration
   has additional installation and OS-version constraints. A small standalone
   percentage display could consume the now-working report, but would be a
   different result from the requested native Bluetooth UI.

Changing the ADC mapping, increasing report frequency, repeatedly re-pairing,
or adding a guessed report6 currently lacks an evidence-based causal path to
the missing UI. Firmware-emulating HFP headset or UPS identities would also
change the device's role and is not a justified keyboard solution.

## Reproducible primary evidence

`private/apple/native-battery-next-route-evidence.json` records SHA-256 hashes
and selected personalities from the installed Apple plist files, plus the
bluetoothd binary hash and directly decoded gate strings. Existing static
disassembly is in `private/apple/bluetooth-battery-callers.txt` and
`private/apple/bluetooth-battery-fallback.txt`.

The public Apple IOHIDEventDriver source inspected locally has no battery
processing path identified; absence in that source is not proof about every
closed Apple driver or every macOS release. Reference:
https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDFamily/IOHIDEventDriver.cpp

This assessment makes no native-UI promise and does not establish battery-life
or wake-latency improvements from the installed changes.
