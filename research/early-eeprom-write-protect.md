# Neutral rollback trial: missing early write-protect setup

2026-10-28. Astra, offline analysis only. Original candidate/source files were not modified. Parent reports the physical neutral trial left SS0 valid and selecting DS4000, SS100 valid selecting A86DS8000, and the running selectedDS global was8000 with exact working A86 extension/methods. That establishes that the guard's failure redirect worked physically; SS0 invalidation did not. No Apple profile ran.

## Concrete omitted dependency

The normal EEPROM writer atROM2C9B2 calls function pointer `[200A18]` with argument0 before starting its write and argument1 immediately after controller completion, before ACK polling. The pointer is **17541**, Thumb entry17540. This is not merely an optional interrupt wrapper:

- It reads the configured pin selector byte at200A02. FF means disabled/no operation.
- Otherwise it splits the byte into port=`selector>>5`, pin=`selector&31`.
- On argument0 it saves current GPIO mode via17CA2 and current level via17C48 in2009E6/2009E2, then calls17BE4(port,pin,4000,0): output mode, low level.
- On argument1 it restores the saved mode and level through17BE4.
- Installed application configuration has selector40: **CYW port2, pin0**, with GPIO configuration register390280 and output-data register390118 bit0. These are radio GPIOs, not Sonix matrix pins.

The original bounded boot guard directly called async I2C setup2C754/status2C6FE and omitted this GPIO bracket. That is sufficient to explain an EEPROM which accepts traffic but does not program while hardware write protection remains asserted.

There is a second required detail: **the callback exists early, but its pin selector is initiallyFF**. Actual execution of ROM scatter initialization and the full normal pre-DS chain1C798→2C6B6→2C91C→1C258, stopped at1D15C, gives `[200A18]=17541` and `[200A02]=FF`. Adding calls to17540 at the original prefix location alone would therefore still do nothing.

The original application’s **A7 configuration record** enables the pin:

```
A7 14 00
40 00 F0 00 00 FF 0F 00 00 B0 7F 00 00 00 00 00 00 00 00 00
```

It occurs at offsetAF7 in the working A86 dynamic section. The20-byte payload copies to200A02..200A15. It sets selector40, storagebaseF000, storage length0FFF and the other original configuration fields. It does not overwrite callback200A18 or perform a GPIO transition itself. Actual-ROM parsing of this standalone record changes only bytes within that20-byte configuration range outside the parser stack.

The chip-family [Fremont FT24C512A datasheet](https://media.digikey.com/pdf/Data%20Sheets/Fremont/FT24C512A.pdf), page3, documents that WP high disables programming for the whole array while leaving reads unaffected; WP low enables writes. The exact PCB continuity from CYW port2/pin0 to the photographed EEPROM’s WP pin has not been measured. The callback behavior, configured selector and physical failure pattern make this a strong specific explanation; they are not a measured pin-voltage trace.

## Minimal correction to review

The defensible proposal is to apply the **exact unchanged original A7 record before the guard**, retain the callback guard/pointer checks, and bracket only the byte-write transaction with original17540(0)/17540(1). Restore on completion, error and timeout before any redirect or return. ACK polling and readback remain bounded. Normal ROM restores immediately after controller completion and before ACK polling; there is no need to keep write protection disabled while waiting for ACK or reading.

The original A7 appears again later in the unchanged DS and writes the same values, so no final configuration change is needed. This is a proposal for parent implementation/review, not a modified candidate in this report. A write timeout still leaves controller/bus state uncertain; restoring the GPIO is required cleanup, not proof the fallback EEPROM read can recover a physically stuck bus.

## Regression evidence

`private/bt-persistence-research/test_early_eeprom_write_protect.py` passes four tests. It executes actual ROM scatter, full pre-DS initialization, A7 parsing, GPIO save/drive/restore and I2C controller setup. Its explicit hardware model assumes the GPIO drives EEPROM WP, an external pull-up when configured as input, and controller ACK completion:

1. Before A7, callback exists but FF disables it; async write leaves the modeled EEPROM byte unchanged.
2. A7 alone enables the callback configuration but does not lower the pin; an unbracketed async write still does not program.
3. The original synchronous EEPROM writer invokes the callback, lowers the pin during the transaction, programs the byte and restores GPIO mode.
4. Bracketing the async write with the original callback produces the same modeled GPIO/programming/restoration behavior.

Results are saved in `early-write-protect-results.json`. These tests deliberately expose the dependency missing from the earlier controller-only model. They do not claim physical write success, board-net continuity or guaranteed recovery from electrical bus faults.
