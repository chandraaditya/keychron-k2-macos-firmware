# Original K2 connected idle and 500 ms wake: Apple comparison and feasibility

Investigated 2026-10-27. This consultation used existing captures, offline analysis, local driver files, and public primary sources. No live device operations were performed by this agent. Parent-agent observations are identified separately. Neither a hardware-tested patch nor an installed-scanner image has been obtained.

## Assessment

**The original K2 has a credible firmware-only path to remaining connected while its scanner idles and becoming locally ready within approximately 500 ms. The strongest current candidate is Sonix Sleep mode with the SPI receiver and its clock retained.** This is more concrete than relying on the Bluetooth chip's advertised capabilities: the manufacturer's manual permits it, and the parent investigation has now exercised the actual reference firmware's sleep entry and incoming-message handlers offline.

This does not yet establish the combined target of 20–30 calendar days and 500 ms end-to-end input. The first uncertainty is current with the oscillator and SPI retained. The second is actual radio/host scheduling. A deeper scanner sleep may save more, but the installed radio's short attention-to-data gap makes incoming transfers a specific obstacle. A radio firmware change is therefore **conditional**, not inherently required for the first workable candidate.

Apple is a useful existence proof that long runtime and prompt input can coexist on Bluetooth Classic with several chips. Public evidence does not disclose Apple's complete idle state machine, sensor duty cycles, or interprocessor wake contract. There is no basis for promising equivalent results by copying an Apple identity or a few SDP attributes.

## 1. Separate the three timing requirements

| Situation | What must happen | What the investigation can currently say |
|---|---|---|
| K2 scanner idle; Bluetooth link retained; Mac awake | Wake scanner, restore matrix service, deliver subsequent key reports over the existing link | A 500 ms local-readiness target is technically credible; reference-code and manual evidence support a concrete candidate |
| K2 scanner idle; Mac asleep but accepting Bluetooth wake | Recover scanner and deliver a genuine HID input event that wakes the host; then accept subsequent typing | The K2 advertises remote wake. A first key discarded entirely inside the keyboard cannot itself wake the Mac |
| Laptop left range and returned | Discover/listen/page, establish the link and HID channels, then deliver input | This is the existing 8–10-second reconnect problem. Scanner idle changes do not automatically fix it |

The practical firmware contract should preserve a real key press and its release after recovery, allowing the OS to consume the first event as wake. If another device wakes the Mac, discarding a local wake key may be acceptable. Those are different behaviors. No fabricated extra keystroke is needed.

“Ready when the display comes on” is a useful user-visible acceptance condition, but display wake is host-controlled. Keyboard-local readiness, first report delivery, and host display readiness must not be reported as the same measurement. [Apple's documented wake actions](https://support.apple.com/en-ie/guide/mac-help/mh10330/27/mac/27).

## 2. What the original K2 code now supports

### Receive-capable scanner sleep

Sonix manual §4.3.1 says Sleep mode stops the CPU while selected peripheral clocks continue; their interrupts can resume execution. Registers, SRAM and pin levels are retained. Entry is PMU value 4 followed by WFI. Section 4.4.2 explicitly distinguishes retained-clock sleep from restarting an oscillator: there is no oscillator wake delay when the clock remains running. The SPI controller has an eight-frame receive FIFO. These are relevant hardware capabilities, not a claim that every existing ISR is automatically race-free. [Sonix SN32F240B-series manual, §§4.3–4.4 and 10.2](https://www.sonix.com.tw/webapi/fl219873/SN32F248B_V2.4_EN.pdf).

Parent analysis of the downloaded K2 V2 RGB 1.13 image establishes:

* Existing sleep entry stops the scan/PWM timer's AHB clock, but leaves the SPI clock-enable bit set.
* The deeper path explicitly switches to the low-speed oscillator before selecting PMU mode 2. Omitting that switch and selecting mode 4 can retain the normal peripheral clock.
* SPI IRQ 6 remains enabled. The inspected SPI ISR directly receives bytes when the attention line is high; no separate edge-triggered receiver priming was found in this reference path.
* Four offline cases passed in `research/test_connected_sleep_candidate.py`. The entry case retained SPI clock and interrupt, stopped scanning/SysTick, and reached WFI with mode 4. Separate manual ISR/parser replays correctly applied a host LED message and a low-battery notification.

Evidence: `private/connected-sleep-candidate-emulation.json`. These are reference-image control-flow and register-model results. The replay manually invokes the ISR and does not model physical FIFO reception, interrupt timing, WFI exit, voltage, current, or the user's unidentified installed scanner image. Entry also assumes a quiet bus; checking a transaction and then sleeping needs a race-safe guard.

This candidate can plausibly retain unsolicited radio-to-scanner traffic **without a radio patch**. It must also preserve existing outgoing report handling, wake on matrix keys, handle USB/mode changes, and avoid an interrupt or restore loop that defeats idle savings. It is a prototype direction, not a flashable or accepted firmware release.

### Why immediate deep sleep is a different problem

The installed 20191025 radio sender at `0x208498` asserts attention, calls helper `0x29c6e` with argument 5, then starts transferring. There is no receiver-ready polling inside this transfer function. Parent read-only ROM captures now show CPU-frequency-dependent calibrated delay loops; the evidence strongly supports a **microsecond-scale** gap, rather than a five-millisecond recovery window. Actual pin timing has not been measured, and higher-level caller safeguards still need to be established.

Sonix §4.3.2 gives 56 microseconds for deep-sleep wake at 3.3 V and says peripheral clocks stop. Its separate 10-microsecond IHRC startup statement is not full firmware/SPI readiness. Thus changing only the original sleep-policy gate can allow a radio message to start before the scanner is capable of receiving it. Allowing the user's first key to be consumed does not repair an unsolicited message already lost while the scanner was asleep.

For deep sleep, the defensible solutions are an adequate advance wake delay, a proven ready/acknowledgment exchange, or a retry/buffering protocol that survives the receiver's absence. A delay patch must preserve Bluetooth real-time obligations; a long busy-wait in the radio is not automatically an acceptable implementation. Available RAM-hook/packaging space and startup installation remain separate engineering questions.

The newer scanner reference recognizes `B6 5A 0B` and replies `A6 51 60`, but the inspected installed radio dispatcher does not recognize `0x60`. This does not establish a matching installed pair or an available deep-idle handshake. Evidence: `private/original-spi-wake-analysis.json` and parent ROM captures `private/rom-029c00.bin`, `rom-029980.bin`, `rom-029900.bin`, `rom-02aa00.bin`, `rom-000780.bin`.

### Key-only deep sleep with later state refresh

The related original-K8 custom firmware provides an existence example of key-only sleep while the link remains up during a short reported test. It masks radio attention during sleep and acknowledges possible missed host LED updates. Its test does not cover the separate ten-minute radio timer or the installed K2 board. [Author's implementation and test notes](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/keyboards/keychron/k8/readme.md).

Such a compromise might satisfy basic typing while tolerating a stale Caps Lock LED, but “resynchronize on wake” needs actual protocol support. The inspected interface contains battery queries; it has not established a complete query/replay mechanism for current host LEDs, link transitions, pairing state and shutdown notifications. The first lost packet can carry more than cosmetic state. Therefore key-only sleep is a useful bounded experiment, not yet a complete alternative to preserving incoming traffic.

### Battery-life constraint

Moving from 3–4 days to 20–30 days under comparable use requires roughly **80–90% lower average draw**. Mode 4 removes CPU/bus switching activity but retains oscillator and selected peripheral consumption. The Sonix table's approximately 200-microamp Sleep figure is specified with the low-speed 32 kHz clock; it must not be assigned to this fast-clock SPI candidate.

The scanner, radio schedule, regulator losses, and board leakage all contribute. Chip data sheets cannot establish their installed sum. The user's long runtime with disconnecting auto-sleep is encouraging evidence that the board can reach a low-current state; it does not establish that receive-capable connected idle reaches the same state. A month of runtime remains unproven even if all offline protocol cases pass.

## 3. What the Lightning Apple devices actually contain

Firsthand 2015 teardowns identify **BCM20733 and STM32F103VB** in both Magic Keyboard A1644 and Magic Trackpad 2 A1535. The keyboard battery is 2.98 Wh. The trackpad contains a BCM5976 touch controller, four force-sensing strain gauges, a Taptic actuator, and a 7.65 Wh battery. These observations refute a simplistic explanation that Apple succeeds because the entire accessory is one exceptionally low-power chip. [Magic Keyboard teardown, steps 7 and 9](https://www.ifixit.com/Teardown/Magic+Keyboard+Teardown/50995), [Magic Trackpad 2 teardown, steps 5, 7, 8 and 10](https://www.ifixit.com/Teardown/Magic+Trackpad+2+Teardown/51032).

**The component photographs do not establish the processors' division of labor.** In particular, they do not prove that Apple's STM32 is a continuously running key scanner equivalent to the K2 Sonix, or establish which wake lines and buses connect the chips. The trackpad's richer active sensing workload also does not imply that every sensor, processor and haptic stage remains fully active while untouched. Reduced sensing duty cycles and event-driven recovery are plausible; their exact implementation has not been demonstrated here.

Apple documents approximately a month or more between charges for the 2015 keyboard, with a stated automated-use test on paired iMacs. This is manufacturer product evidence, not a 500 ms latency specification. [Apple specifications and test conditions](https://support.apple.com/en-ae/112443).

## 4. Actual Apple Bluetooth evidence, and its limits

### Product observation: ordinary sniff really is used

A published firsthand macOS System Profiler dump identifies a Magic Trackpad 2, product `0x0265`, firmware `0x0100`, Broadcom controller subversion `0x240c`, connected in **Sniff Mode with an 11.25 ms interval**, and host-connectable. This supports actual use of standard Bluetooth Classic low-power operation by a Lightning trackpad on a Mac. It is one configuration snapshot, not a controlled idle trace or latency measurement. It does not reveal an eventual sniff-subrating factor or whether a later state uses another mechanism. A sanitized excerpt is saved as `private/apple-wake-research/trackpad-profiler-sanitized.txt`. [Original system report](https://gist.github.com/tperfitt/9386183bc247e7d7de5f1df1247e5dd2).

The InternalBlue researchers independently list the Magic Keyboard's BCM20733 controller version as `0x240c`; their table explicitly identifies these as real-world observations. It provides a firmware-family lead, not a decoded power-management state machine. [InternalBlue firmware table](https://github.com/seemoo-lab/internalblue/blob/master/doc/firmware.md).

### Owner's actual cached service attributes

The parent's fresh passive cache read shows that both the owner's Apple trackpad and K2 advertise remote wake and device-initiated reconnect. The Apple trackpad advertises normally-connectable; the K2 does not. Optional host SSR latency attributes are absent in both cached records. Evidence: `private/cached-hid-wake-feasibility.json`.

Therefore the K2 does not simply lack the advertised permission to wake its host. Nor is the optional SSR-attribute absence alone an explanation for the difference. Normally-connectable can affect which side can initiate reconnect, but does not by itself explain the whole 8–10-second delay. These service declarations do not expose current radio link parameters.

### Apple's accessory requirements are useful guidance, not its firmware dump

Apple's current Accessory Design Guidelines §57.3 require sniff and sniff-subrating support and recommend a 15 ms base interval; §57.13 recommends SDP host maximum latency 450 ms and minimum timeout 45 ms. Those demonstrate the intended interoperability model: brief base scheduling with reduced idle activity. They do not prove that a particular Magic device uses those exact values, and the 450 ms attribute is not an end-to-end keyboard wake guarantee. [Apple Accessory Design Guidelines](https://developer.apple.com/accessories/Accessory-Design-Guidelines.pdf).

### A real alternative exists in the Apple radio silicon

CYW20733 manufacturer documentation §1.18 describes proprietary BPCS/TBFC operation: radio traffic may stop while L2CAP/HID remain logically connected, then resume through fast baseband recovery with a supporting peer. Thus an accessory appearing connected in macOS does not necessarily prove continuously scheduled RF traffic. **There is no evidence here that Apple enables this feature**, and no requirement to reproduce it for the K2 to achieve useful connected idle. Standard sniff remains an evidenced Apple operating mode. [CYW20733 manufacturer datasheet, §1.18, distributor-hosted copy](https://media.digikey.com/pdf/Data%20Sheets/Cypress%20PDFs/CYW20733_RevS_11-9-17.pdf).

That datasheet's class-2 examples give 240 microamps at 495 ms sniff versus 4.46 mA at 11.25 ms under its specified optimized-peer conditions. This illustrates why actual radio scheduling matters. It is neither Apple's measured draw nor a K2 runtime estimate; board current and sniff subrating are not captured by applying one row to a whole product.

### What host driver code does not establish

Linux's `hid-magicmouse.c` handles Apple multitouch reports, feature initialization and selected battery operations. It does not expose the accessory's internal idle power policy. Its 500 ms delayed work relates to feature reinitialization paths, including USB resume, and must not be cited as Lightning Bluetooth wake latency. [Inspected Linux source](https://github.com/torvalds/linux/blob/d135ab453a7400a34930bdda1ef4bdc8acfac80e/drivers/hid/hid-magicmouse.c).

Local Apple driver plists expose battery features and polling entries for particular product IDs, but the inspected BNB trackpad personality matches `0x030e`, not the Lightning trackpad's `0x0265`. Those entries were not used to invent the Lightning product's policy. No publicly inspected Apple accessory firmware state machine establishes its exact sensor wake, bus startup, or long-idle timing here.

## 5. Engineering judgment and remaining discriminators

| Proposition | Judgment | What would resolve the remaining uncertainty |
|---|---|---|
| Original K2 electronics can plausibly retain Bluetooth while scanner CPU sleeps | Strongly supported as a firmware design direction | Confirm installed scanner variant; validate real mode-4 entry and reception |
| Scanner-local recovery can plausibly fit 500 ms | Strongly plausible; the documented CPU/clock times are far smaller | Bound full restore, matrix debounce, queue service and report transmission |
| A Bluetooth patch is mandatory for any workable connected idle | Not supported | Mode-4 reception offers a specific route without it |
| Deep scanner sleep can safely receive the current radio's first packet after wake | Significant contrary timing evidence | Establish caller handshake or introduce a reliable wake/transfer contract |
| Mode 4 alone yields 20–30 days | Unproven | Establish actual retained-clock board current and radio schedule |
| Consuming a wake key solves all integration problems | False | It relaxes local key handling; incoming radio messages and host wake still need correct handling |
| Apple's exact behavior is known from its chips and marketing | False | Actual controller scheduling and firmware evidence would be needed |
| Faster local wake automatically fixes away-and-return reconnect | False | Identify initiation, page/listen timing, retry and HID setup separately |

The most informative next engineering sequence is to finish the reference/installed-image and bus-entry analysis for the receive-capable Sleep candidate, then determine whether its current budget is sufficient. If it is not, deeper coordinated sleep becomes the next target. This orders the work around a concrete implementation that can preserve normal input and status traffic, while keeping a separate investigation for radio reconnect. No replacement electronics or Apple identity spoofing is required by this approach.
