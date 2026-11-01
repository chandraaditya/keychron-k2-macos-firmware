# Physical EEPROM identification and recovery review

2026-10-28. Astra. Inspection of owner photos and manufacturer documents, plus offline execution of captured ROM. No device queries, electrical connections, bridges, writes or flashing. Candidates and captures were not modified.

## What the photos establish

- `IMG_0891.JPG`: radio package clearly reads `CYW20730` and `A2KFBG`. The adjacent eight-lead device clearly reads `24C512A`; its second line appears to be `FT024CD`, with the final characters less certain. The package has exposed soldered leads. I do not see an unambiguous FMD logo or the complete `FT24C512A` ordering code. Fremont Micro Devices is a probable manufacturer identification, not a conclusively authenticated manufacturer/suffix identification. No primary marking legend was found that decodes the second line.
- `IMG_0890.JPG`: the main controller reads `HFD2201KBA`. The [SonixQMK project's own hardware table](https://sonixqmk.github.io/SonixDocs/) maps this marking to SN32F248B, Cortex-M0, LQFP64. This is implementation-community evidence, distinct from a manufacturer-issued cross-reference.
- `IMG_0889.JPG`: board text reads `CK8887RGB-1.2` and `20200427`.
- `IMG_0894.JPG`: front text reads `RGB Ver 1.2/20200515`.
- `IMG_0892.JPG`: two exposed through-hole pads are explicitly labeled `BOOT`. The photograph establishes their presence and label, not their electrical endpoints or tested recovery behavior.

The EEPROM's legible `512` capacity marking, its location beside the radio, the captured EEPROM protocol and the complete 64-KiB read without a simple 16/32-KiB alias now provide strong combined evidence for a physical 64-KiB serial EEPROM. Capacity should no longer be described solely as an unverified inference from a software address window. Exact manufacturer identification remains qualified, as does write behavior on this individual board.

## Geometry supported by the manufacturer reference

Fremont's [2016 FT24C512A datasheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/501/FT24C512A.pdf) specifies 65,536 bytes, 128-byte pages, two-byte addressing, partial-page writes, a 5-ms maximum programming cycle, and 1.8–5.5 V operation. Its package pinout is 1=A0, 2=A1, 3=A2, 4=GND, 5=SDA, 6=SCL, 7=WP, 8=VCC. WP high blocks programming while reads remain possible. Page writes wrap within the addressed page; ACK polling detects completion. The [2009 manufacturer datasheet](https://media.digikey.com/pdf/Data%20Sheets/Fremont/FT24C512A.pdf) agrees on capacity, page size and maximum write-cycle time. These are FT24C512A specifications, not a measurement of the board's supply or WP wiring.

The installed ROM's configured 16-byte boundary is conservative for 128-byte pages. ROM function `0x2C92E` chooses `min(remaining, 14, 16 - (address mod 16))`. Every 16-byte boundary aligns within a 128-byte page, so none of these chunks crosses a physical page boundary. There is no need to change the ROM configuration to 128 just because the chip supports larger writes.

`private/bt-persistence-research/check_128byte_geometry.py` executes the real captured chunk function for 2,048 cases covering all 128 physical-page offsets and all effective remaining-length classes. It also checks all 65,536 possible starting addresses mathematically. All passed. The 14,322-byte DS at `0x4000` ends at `0x77F2` exclusive; a single contiguous driver request would split into 1,791 chunks. Separate host requests can produce more chunks. The JSON result is saved beside the script.

SS0 occupies physical page `0x0000–0x007F`; backup SS100 occupies `0x0100–0x017F`. They are separate from each other and from the VS beginning at `0x01C0`. The inactive DS starts on a page boundary. This strengthens the proposed staging layout. It does not establish what happens to a physical EEPROM write interrupted mid-programming; the previous transaction test checked completed-byte prefixes only.

## What recovery is now plausible, and what is not yet established

The exposed EEPROM leads provide a plausible independent I²C programming route to restore the original SS or invalidate the new SS0 so the retained original SS100 becomes selected. This route does not depend on the candidate Bluetooth application successfully starting. It is more concrete than assuming an unidentified test header provides UART recovery.

It is not yet a verified in-circuit recovery procedure. Pin-one orientation, ground, the actual shared supply voltage, WP wiring, pull-ups, and the radio's behavior while another master drives the bus must be established. An externally powered programmer can energize other circuitry through the shared rail or signal paths; an attached radio can load or drive the bus. The EEPROM's voltage tolerance alone does not establish safe voltage for the surrounding module. Isolation might be necessary, but the photos do not establish whether a clip will work or which component would require isolation.

P2/P3/P4/P5 remain unidentified PCB connections. No pin on those headers or test points is assigned SDA, SCL, UART, reset, voltage or ground here. Datasheet EEPROM pin numbers must not be substituted for unverified board-header mappings.

The labeled BOOT pair concerns the main-controller recovery investigation. A Sonix bootloader session would not by itself repair the radio EEPROM. Likewise, an EEPROM restore would not recover an incorrectly flashed Sonix main image. The two recovery mechanisms must remain separately assessed.

A retained old SS100 is not automatic rollback when a valid SS0 points to a crashing DS: the captured ROM selects the first valid static header without testing successful application startup. The external restore route therefore still matters. These photos and geometry checks materially reduce uncertainty, but no working physical recovery method or flashing clearance is claimed.
