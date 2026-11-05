# Battery current measurement plan (A94 + scanner CPU-idle A)

2026-11-01. Nothing measured yet.

## Why measure first

From the owner's observation (about 13% per day on the voltage estimate, roughly a week per
charge) and the K2's rated 4,000 mAh, average draw is about **20–25 mA**. Before the scanner
idle patch, 3–4 days implied 42–56 mA. These are rough: the percentage is a voltage guess and
the cell's real capacity is unknown.

Targets at 4,000 mAh: 20 days = 8.3 mA, 30 days = 5.6 mA. So connected idle needs to drop
about 3–4×.

Candidate consumers:
- **Sonix scanner:** 14 mA typical at 48 MHz in normal mode (manual). CPU-idle A only adds a
  CPU WFI between scan IRQs; the clocks, scan timer and PWM keep running.
- **RGB LED drivers / PWM**, even with lighting off.
- **CYW20730 radio:** in sniff the chip should be around 1 mA or less, but the Mac sets a
  15 ms interval, which is on the expensive end. The datasheet example gives 4.46 mA at 11.25 ms.
- Regulators, the charger and leakage.

Each fix targets a different one of these, so the readings decide what comes next.

## Measurements (meter in series with the battery, lighting off)

| # | State | Separates |
|---|---|---|
| 1 | Connected to the Mac, idle 30 s+ after the last key | the main number (connected idle) |
| 2 | Typing continuously | scanner and radio active |
| 3 | Lighting on, one static mode, medium | LED cost (sanity check) |
| 4 | Mac Bluetooth off, K2 on (not connected) | radio page-scan vs sniff |
| 5 | K2 power switch off | leakage floor |

Record the average reading after it settles about 10 s, plus min/max if the meter has them.
A meter averages the radio's millisecond pulses well enough for this.

## Safety

- Li-po cell: never let the two battery leads or meter probes touch each other.
- Turn the lighting off first. RGB at full brightness can exceed a meter's mA fuse.
- Use the mA range (200/400 mA), not µA. The µA shunt drops too much voltage, and the
  radio can brown out.
- Every disconnect reboots the keyboard. Under A94 that's fine while the Mac's Bluetooth is
  on; it re-arms on reconnect. For measurement 4, turn the Mac's Bluetooth off while the K2
  is already running; that boot has already re-armed. If the K2 reboots while the Mac's
  Bluetooth is off, turn Bluetooth back on and let it reconnect before switching the K2
  off. Otherwise the next power-on goes to A86.

## Data point: 22% then dead overnight (2026-11-04/05)

The owner saw 22% in the evening and found the keyboard dead the next morning. At
4,000 mAh that would mean 880 mAh in about 8–10 hours, roughly 90–110 mA, which is
4–5× the ~22 mA estimated average. So the 22% was almost certainly wrong. Likely causes,
not yet separated:
- the estimator's low end: Li-ion voltage falls off a cliff near empty, so a
  voltage-to-percent table that is linear or tuned for a fresh cell reads high there;
- reduced cell capacity (age), which shifts the whole curve;
- the scanner's or radio's cutoff voltage sitting well above the cell's real empty.

Use this when calibrating the percentage: the measured idle current lets us check how
much charge was really left. Record the voltage at cutoff if possible.
