# Radio candidate boot-phase correction

2026-10-28. Offline investigation; no device operations by this advisor.

## Finding

The A85 candidate required the wrong boot phase. The earlier analysis correctly
found that ROM `0x2CFEC` initially clears byte `0x201344`, but missed the later C
runtime scatter initialization. That initialization sets the byte to **1** before
dynamic-section loading. The A85 wrapper consequently declines installation,
leaves the original constructor call and arena start, and permits the unused
extension area to become the original application stack.

This corrects the phase-zero assertion in the earlier
`bluetooth-persistent-integration-review.md`; that assertion must not be used as
current integration evidence.

## Captured ROM evidence

- Reset path `0x2B8` calls `0x1C636 -> 0x2CFEC`, which clears the phase.
- The path subsequently reaches `0x2E8 -> 0x2F0`, the actual scatter initializer.
- Its table at `0x4CEC0` specifies compressed data source `0x4F204`, destination
  `0x200400`, length `0x1458`, and decompressor `0x324`.
- Running those captured instructions through the stop at `0x454` produces
  bytes `01 03 00 00` at `0x201344`; the phase byte is one.
- The later startup dispatch `0x47B86` invokes the DS loader. The actual parser
  `0x1D15C/0x1CBCA` calls both the pre-existing `0x205EDA` callback and the final
  boot callback through `0x29F30`.
- The initialization task sets phase two at `0x4031C`, immediately before its
  heap initialization call at `0x40328`; it later sets phase three.

Executing scatter initialization followed by the complete DS parser reproduces
the original candidate's guard failure: at `0x209024`, R0 is one; the CBNZ takes
the skip path. Arena `0x201350` remains `0x209014`, and constructor instruction
`0x206AA8` remains `01 f0 6a fc`. This agrees with the parent's reported physical
watchdog-reboot and subsequent full-OFF observations. The stack watermark itself
is a physical observation reported by the parent, not an emulated result here.

The original tests preloaded all RAM records, manually seeded phase zero, and
called the final callback directly. They verified that conditional scenario but
did not establish its actual reset-time precondition. Their passing results were
insufficient boot-integration evidence.

## Separate correction

`research/radio_boot_phase1.S` changes the phase check from CBNZ to:

```asm
cmp r0, #1
bne boot_done
```

All arena, original-instruction, reservation-before-hook, forwarding and ABI
guards remain. Phases zero, two and three are rejected. The added halfword
consumes pre-existing alignment padding, so the extension remains 440 bytes and
the reserved arena begins at `0x2091CC`. The constructor wrapper shifts from
`0x209050` to `0x209052`; its rebuilt call instruction is `02 f0 d3 fa`.
The battery component remains byte-identical at `0x209094`.

`firmware/build_radio_candidate.py` now accepts optional keyword parameters.
Its default output remains byte-identical to the original binary, extension,
manifest and disassembly. `firmware/build_radio_phase1_candidate.py` builds only
the separate A86/20261028 artifacts in `private/candidates/radio-battery-phase1`.

The new DS is 14,322 bytes, SHA-256:

`272c7f60a926c65dab10685375aadbb94bc1ddaff88ebfedaa00e84dcd69be3f`

The original A85 source and candidate artifacts were not modified. No SS, bank
assignment, installer change or EEPROM transaction is included in this correction.

## Regression evidence and limits

`research/test_radio_boot_phase1.py`: eight methods pass. They cover original
failure reproduction, exact historical build preservation, actual scatter and
full DS parsing, reserve-before-hook ordering, actual ROM heap initialization,
extension preservation, rejection of phases 0/2/3, alternate hardware-probe and
original-instruction guards, new identity, and the shifted constructor wrapper's
return value, callee-saved registers and vtable installation.

The tests explicitly model the EEPROM reader, hardware patch-register writes,
watchdog service and startup hardware probe. They do not execute the whole reset,
scheduler, radio or physical EEPROM. The reset-vector alternate branch to
`0x100281` remains outside the captured ROM window; it must not be described as
an independently verified identical ROM alias. Corrected physical activation,
battery reports and native macOS publication still require observation.

Reproducible supporting artifacts:

- `private/bt-persistence-research/reproduce_boot_phase.py`
- `private/bt-persistence-research/boot-phase-failure-reproduction.json`
- `private/bt-persistence-research/phase1-regression-results.json`

The retained original SS100/DS3C0 recovery route remains separate from this
code correction. A valid newer SS0 is not automatically abandoned merely because
its application hook fails or its application crashes.
