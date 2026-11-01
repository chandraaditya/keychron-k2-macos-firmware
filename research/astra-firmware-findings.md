# Original Keychron K2: independent firmware and hardware investigation

Investigated 2026-10-27. Scope: research and offline inspection only. No device configuration, connections, RAM, or firmware were changed. This report deliberately distinguishes the installed Bluetooth capture, downloaded main-controller reference firmware, and other physical keyboards.

## Assessment

The best technical explanation is a **power-management contract between the two processors that is adequate for coordinated disconnect-and-sleep, but does not yet establish safe, independent sleep of the scanner while the radio remains connected**. This is more specific than saying that somebody omitted an optimization. The contract has an electrical timing requirement: the Bluetooth processor controls incoming transfers, while the scanner stops its peripheral clocks during deep sleep. A wake interrupt is insufficient unless the scanner's receiver is ready before the first transferred byte.

There is now a strong comparison supporting this explanation. A photographed K8 Pro retains a CYW20730 radio, while Keychron's public Pro firmware implements independent scanner sleep and explicitly solves a wake-to-data timing problem. Thus the older radio silicon does not, by itself, explain the missing behavior. Conversely, a two-byte change to the original scanner's sleep policy is not a demonstrated solution: it can create an unsupported interface state.

This is a leading, falsifiable engineering explanation, not a finding about Keychron's historical intent. The original K2's actual transfer timing, whole-device current, and accepted Bluetooth low-power parameters remain unmeasured. Its 8–10-second reconnect delay and missing native battery display also have separate mechanisms; one sleep-policy fix cannot be assumed to fix all three.

## 1. The discriminating later-generation comparison

### Same radio family, different surrounding implementation

The K8 Pro FCC internal photographs, exhibit 6826572, page 3, figure 5, show **CYW20730 A2KFBG** on the Bluetooth module. This is the same radio family identified for original K2 V2 hardware. The photograph establishes one certified K8 Pro design, not every Pro production revision or the user's installed K2 board. [FCC photographs](https://fccid.io/2ASF4-K8PRO/Internal-Photos/Internal-photos-6826572.pdf).

Keychron's official K2 Pro source specifies STM32L432 as its main controller. Its CKBT51 module interface explicitly states that BLE is unsupported. Therefore “Bluetooth 5.1” on this platform is not evidence of a switch to BLE or its Battery Service. The radio chip's later datasheet itself describes Bluetooth 5.1 compliance. [K2 Pro hardware definition](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/k2_pro/info.json), [CKBT51 interface](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/ckbt51.h).

### Pro scanner sleep is independently implemented

The official `lpm.c` enters a low-power state when Bluetooth is selected, the inactivity gate has expired, indicators have finished, the LED driver is shut down, no matrix key remains held, and the startup battery sample is complete. The default scanner inactivity gate is 1,000 milliseconds; the default power mode is STM32 STOP1. This is distinct from disconnecting the radio. [Low-power policy](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/lpm.c), [timer default](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/lpm.h), [mode default](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/bluetooth.h).

K2 Pro separately configures the Bluetooth module with a 7,200-second connected-idle timeout. Thus the support article's two-hour sleep setting coexists with much earlier scanner sleep when its conditions allow. Its source sets a five-second reconnect-attempt timeout; that is an attempt budget, not a promise to reconnect in five seconds. [K2 Pro initialization](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/k2_pro/k2_pro.c).

### Keychron documents a real timing problem and its solution

The Pro low-power implementation enables wake from the Bluetooth attention pin, matrix rows, and USB-power detection, then restores clocks and the transport after wake. Its developer comment explains that normal STM32 clock initialization takes approximately 2 ms, but CKBT51 can start UART data approximately 200 us after asserting wake. The firmware therefore implements clock restoration taking under 100 us. This is direct manufacturer implementation evidence of an interface deadline that could otherwise break independent scanner sleep. It is not the measured deadline of the original K2. [STM32 low-power implementation, especially lines 269–275](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/lpm_stm32l432.c).

The reverse direction also has an explicit contract: CKBT51 powers down its UART after three seconds of inactivity, and the scanner's sender asserts its wake signal and waits 3 ms before transmitting. [Module transport](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/bluetooth/ckbt51.c).

The Pro board also uses a different matrix implementation: latched HC595 outputs can hold all columns selected for row-interrupt wake. Its configuration includes a separate LED-driver shutdown pin. The original RGB K2 instead shares scanner column pins with PWM-driven LED columns. Those are real integration differences, although shared pins do not prevent sleep when the lights are off. [Pro matrix](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/k2_pro/matrix.c), [Pro configuration](https://github.com/Keychron/qmk_firmware/blob/618127a725a1773e85f13455602cf6f72ab4de17/keyboards/keychron/k2_pro/config.h), [original K2 V2 reverse-engineered mapping](https://github.com/dexter93/keychron-k2).

These sources establish an architectural improvement. They do not establish 20–30 calendar days, a 1–2-second return reconnect, or native Mac battery display on every newer model. Keychron also published a K2 V3 ISO RGB firmware fix for excessive sleep/shutdown current on June 3, 2025, demonstrating that nominal low-power architecture alone does not guarantee correct board-level consumption. [Official firmware history](https://www.keychron.com/pages/firmware-and-json-files-of-the-keychron-qmk-k-pro-and-k-max-series-keyboards).

## 2. What specifically may constrain the original K2

### Incoming SPI traffic is the strongest concrete lead

The original scanner acts as SPI slave; the Bluetooth processor supplies the clock. The related original-K8 implementation arms the slave receiver on attention-line rising edges and finishes the receive on falling edges. Its experimental scanner sleep masks Bluetooth attention entirely and acknowledges potentially missing host Caps Lock updates. That experiment demonstrates key-triggered wake with a retained link over the reported short test; it does not validate complete connected-idle communication. [Original-K8 interface](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/drivers/bluetooth/iton_bt.c), [sleep implementation](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/keyboards/keychron/k8/rgb/sleep.c), [test limitations](https://github.com/goyamamoto/KeychronK8-QMK/blob/main/keyboards/keychron/k8/readme.md).

The installed Bluetooth capture's sender at `0x208498` configures the SPI interface, asserts a GPIO attention signal, calls ROM helper `0x29c6e` with argument 5, and then transfers bytes. It calls that helper with 30 between bytes and 5 before deasserting attention. **No receiver-ready polling or ACK wait occurs inside this visible transfer function.** The helper's units are not established; the value 5 must not be described as five microseconds. Evidence: `private/ram-disasm.txt`, lines 4017 onward; independently inspected during this consultation. A readiness check in a higher-level caller remains possible.

The Sonix manual states that deep sleep stops peripheral clocks while retaining registers, SRAM, and GPIO levels. GPIO edges can wake it. Section 4.3.2 gives 56 us wake at 3.3 V; section 4.4.2 separately gives 10 us for IHRC startup. Those are not interchangeable guarantees for full firmware and SPI readiness. The manual's normal-mode typical current is 14 mA at 48 MHz under its stated 5 V test conditions, versus microamp deep sleep. This supports scanner power as a substantial candidate, without converting the table into a measured K2 power budget. [Sonix manual, sections 4.3–4.4 and 17.2](https://www.sonix.com.tw/webapi/fl219873/SN32F248B_V2.4_EN.pdf).

**Testable hypothesis:** stock operation keeps the scanner receptive while the Bluetooth module may send unsolicited status/LED/battery traffic. Stock disconnect-and-sleep avoids this ordinary connected-traffic state. Allowing scanner deep sleep independently requires either a sufficiently early wake, a ready/acknowledgment exchange, buffered/retried transfer, or a shallower receive-capable idle state. If the existing sender already supplies adequate time and all callers enforce readiness, this hypothesis weakens sharply.

### Firmware generations have a potentially significant protocol difference

The parent investigation found a wake notification/acknowledgment path in downloaded K2 V2 RGB 1.13: incoming `B6 5A 0B` leads to an `A6 51 60` reply. The installed 20191025 Bluetooth parser does not recognize command `0x60` in the inspected dispatcher. Therefore one cannot use the newer scanner's wake handshake as proof that the installed Bluetooth firmware implements the matching side. Nor does this prove the user's installed scanner is mismatched: its exact image remains unknown. This is a useful compatibility discriminator before selecting either firmware image or patch. The downloaded non-backlit Bluetooth 1.09 reference has a materially different application structure; it is not evidence of an RGB-compatible wake-ACK upgrade.

### Physical impossibility is not presently supported

* **Missing 32 kHz crystal:** weak explanation. The CYW20730 block diagram makes the external 32 kHz crystal optional and includes an internal low-power oscillator. Its current table explicitly specifies sleep using the internal LPO. Missing an external crystal could affect timing margins or efficiency; it does not categorically remove connected low-power operation.
* **Radio silicon incapable of retaining a link cheaply:** contradicted at the capability level by documented sniff support and the same-family Pro comparison. The actual link mode negotiated with this Mac remains unknown.
* **Scanner cannot wake from keys and radio:** contradicted at the chip level by GPIO wake support. Whether the installed board's exact signals and startup timing are suitable is still a board/firmware question.
* **Shared matrix/RGB pins require perpetual scanning even with lights off:** not established. Static output levels plus row interrupts are used by existing sleep implementations. The shared pins do require careful ordering to avoid lighting or false key events.
* **Scanner sleep necessarily cuts radio supply:** no evidence. In the V2 reference, the previously suspicious GPIO B8 clear is now traced to a low-battery blinking indicator by the parent investigation. A complete verified schematic is still absent.

The CYW20730 facts above derive from its [manufacturer datasheet, block diagram, power management, and current table](https://www.infineon.com/assets/row/public/documents/non-assigned/57/infineon-cyw20730-single-chip-bluetooth-transceiver-for-wireless-input-devices-datasheet-additionaltechnicalinformation-en.pdf). The K2 FCC file exposes photographs but lists its schematic and block diagram as confidential; photographs cannot establish all power nets. [K2 filing](https://fccid.io/2ASF4-K2).

## 3. SDK and board constraints versus manufacturer intent

A real SDK boundary exists. Cypress/Infineon explicitly said in 2019 that CYW20730 was not supported through its broad-market tools/community and required a direct regional support engagement; the same limitation was reiterated in 2022. Consequently, examples for BCM20732/36/37 or modern WICED devices are not evidence that an equivalent supported API was available for this product's CYW20730 application. [2019 firmware/source request](https://community.infineon.com/t5/Studio-Bluetooth/BCM20730-firmware/td-p/45567), [2022 development-tools request](https://community.infineon.com/t5/AIROC-Bluetooth/CYW20730-dev-tools/td-p/380638).

This makes a module-specific power/wake contract a credible engineering boundary. It does **not** show that Keychron lacked vendor access, that a particular SDK bug forced the policy, or that the manufacturer chose it for cost, neglect, or planned replacement. A historical “why they chose it” claim needs design records. A present technical “what must be made true for this board to do it” claim can be investigated from the captured code.

## 4. Reconnect and battery are separate questions

### Return reconnect

With auto-sleep already disabled, the reported 8–10-second return reconnect cannot be attributed solely to restarting a sleeping scanner. A severed Bluetooth Classic link must be re-established through paging, listening, connection setup, and host HID handling. The local cached SDP says the K2 initiates reconnect but is not normally connectable. That affects which side can initiate recovery; it does not identify the exact observed delay.

The next discriminators are: which side actually initiates, when the first attempt starts, whether the peer is listening, whether an attempt times out/retries, and how much time remains after the link is up before HID input works. Keeping a nearby link in sniff avoids this sequence during desk idle; it cannot eliminate the sequence after the laptop leaves range. A strict return-time bound also depends on host behavior. [Bluetooth HID 1.1.1, sections 5.1 and 5.3.4](https://www.bluetooth.org/docman/handlers/downloaddoc.ashx?doc_id=309012).

No fixed 8- or 10-second constant has yet been causally tied to this symptom. Changing page-scan parameters is not a demonstrated fix, particularly if the K2 is the paging initiator. No new reconnect experiment was performed.

### Native battery percentage

The existing investigation already separates a usable ADC estimate from a stale/zero standard report cache, and then from macOS's UI publication path. Approximate battery estimation does not require replacing the radio or a precision fuel gauge. Repairing the first two layers still does not prove that macOS accepts the Classic HID field into its native Bluetooth battery display.

Later Pro boards are not a blanket counterexample: a separate author's captured K10 Pro descriptor has no battery collection, despite its module having an ADC and internal battery values. That author implements a Mac accessory-power-source helper, rather than demonstrating an ordinary stock Bluetooth battery field. These are author-reported measurements on their keyboard, not independently reproduced here. [K10 Pro research and implementation](https://github.com/bkovacev/keychron-macos/blob/main/docs/RESEARCH.md).

Thus there is no evidence that battery reporting is absent to save meaningful power, or that scanner sleep and battery UI have one common root cause.

## Confidence and competing explanations

| Claim or hypothesis | Assessment |
|---|---|
| Pro firmware has independent scanner sleep and an explicitly engineered wake deadline | High: official implementation, fixed commit |
| A certified K8 Pro retains CYW20730 radio silicon | High: readable FCC component photograph |
| Original scanner stays active under the inspected disable-sleep gate | High for the named downloaded reference images; installed scanner version unknown |
| Unsafe incoming-transfer timing is the specific obstacle to independent original-K2 sleep | Medium: concrete sender/receiver architecture, plausible failure mechanism; actual deadline and all caller guards unresolved |
| Scanner activity is a substantial cause of short always-on runtime | Medium: control flow and chip current scale support it; no rail-current measurement |
| Missing external 32 kHz crystal makes connected standby impossible | Low plausibility: optional crystal/internal LPO documented |
| A radio power-switch net necessarily prevents scanner-only sleep | Low on current evidence: the identified suspicious pin is a low-battery LED; remaining nets unverified |
| The delay reflects paging/retry/host reconnection rather than only scanner startup | Medium as a class of explanations; low for any particular timer |
| Manufacturer intent, historical SDK bug, or deliberate product restriction identified | Not established |

## 5. Recommended firmware-first investigation order

1. **Resolve the original incoming-transfer contract.** Identify the ROM delay helper's units; map every call into the SPI sender; trace any wake/ACK state machine and how it differs across available Bluetooth revisions. Establish the earliest safe receiver readiness point. This can continue offline before any device experiment.
2. **Identify the exact installed scanner/board pairing before packaging a patch.** Do not treat serial prefixes, USB device-version strings, or matching command families as the main firmware version. Keep the V1/V2 reference analyses separate.
3. **Design independent scanner idle as an explicit state.** Cover key wake, incoming Bluetooth wake, held keys, queued/in-flight packets, clock restoration, and battery/LED/state notifications. If necessary, revise the Bluetooth sender and scanner receiver together. A shallow idle mode is another candidate if deep sleep cannot meet the interface deadline; its current must eventually be measured.
4. **Determine actual radio connected-idle behavior.** Sniff/subrating capability is already known; whether it is used and whether the host accepts suitable parameters are the questions. Avoid assuming that stopping the 600-second disconnect timer disables sniff.
5. **After separate authorization for physical validation, measure current by state and timing by phase.** Compare scanner awake/idle, radio connected/disconnected, and whole-board draw. This distinguishes an active scanner from radio activity and regulator/peripheral leakage, and tests the 20–30-day budget. Do not promise that calendar runtime from chip tables.
6. **Keep reconnect and battery work separate.** Trace the reconnect state machine against timing evidence; repair battery cache/reporting and then validate the actual native Mac UI path.

The strongest change to the prior approach is the first item: investigate the **wake-to-transfer deadline and protocol version pairing before treating local sleep-gate bypass as a viable firmware fix**. The evidence supports continued work on the existing electronics; it does not establish a need for a donor controller or a newer keyboard.

## Evidence files

* `private/astra-research/keychron-tree.json`: official source tree at commit `618127a725a1773e85f13455602cf6f72ab4de17`.
* `private/astra-research/keychron-source/`: 30 relevant official source files from that commit.
* `private/astra-research/k8pro-fcc-internal.pdf`, especially page 3 figure 5; rendered `k8pro-fcc-3.png`.
* `private/astra-research/k2-fcc-internal.pdf`: original K2 filing photographs; no complete schematic.
* `private/astra-research/manifest.json`: downloaded artifact hashes and sizes.
* Existing local references inspected: Sonix manual, original K8 custom sleep/transport/readme, installed RAM disassembly, main investigation report. Parent's concurrent wake-ACK and GPIO findings are explicitly attributed above and saved with hashes/annotated disassembly in `private/original-spi-wake-analysis.json`.
