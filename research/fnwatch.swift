import IOKit.hid
import Foundation
// Prints K2 key-related HID element changes (keyboard page 7, Fn FF/03, Eject C/B8). Ignores key identity of letters.
let m = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
IOHIDManagerSetDeviceMatching(m, ["Product": "Keychron K2", "PrimaryUsagePage": 1, "PrimaryUsage": 6] as CFDictionary)
IOHIDManagerRegisterInputValueCallback(m, { _, _, _, v in
  let e = IOHIDValueGetElement(v); let p = IOHIDElementGetUsagePage(e); let u = IOHIDElementGetUsage(e); let x = IOHIDValueGetIntegerValue(v)
  let interesting = (p == 0x07 && u >= 0x3a && u <= 0x45) || p == 0xff || p == 0xff01 || (p == 0x0c)
  if interesting { print(String(format: "page=%04x usage=%04x value=%d", p, u, x)); fflush(stdout) }
}, nil)
IOHIDManagerScheduleWithRunLoop(m, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
let r = IOHIDManagerOpen(m, IOOptionBits(kIOHIDOptionsTypeNone))
print(String(format: "open=0x%08x devices=%d", r, (IOHIDManagerCopyDevices(m) as? Set<IOHIDDevice>)?.count ?? 0)); fflush(stdout)
RunLoop.main.run(until: Date().addingTimeInterval(Double(CommandLine.arguments.dropFirst().first ?? "3") ?? 3))
