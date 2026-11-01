# EEPROM comparison refusal: narrow offline findings

2026-10-28. No device access or writes by this advisor. The initial investigation below identified a second mutable area. The parent's subsequent read-only capture was then independently compared offline, confirming that the actual refusal fits that area exactly.

## Confirmed refusal and narrow resolution

The new capture at `private/radio-preflight-diagnostics/1793159004971469000/eeprom-first.bin` has SHA256 `767dd6fe973c11aa6be53c204cb52330c6b2f78be6bfcb7d31c74bac53afe840`. Independent comparison finds exactly26changed bytes outside VS, all within **F027..F04C**, the second38-byte host-slot record. Every byte outside VS and that record matches the old A86 baseline, including SS0, SS100, all DS banks, and the remaining tail. The parent's diagnostic also independently reread changed blocks as16-byte requests and reports stable agreement with the new capture, not an AA-tail failure.

For this trial, the preferred correction is **a separately pinned new baseline from this reviewed capture, while leaving the strict fresh comparison unchanged**. Validate the transition from the historical baseline allows only VS and this exact second-slot record; preserve both historical and new snapshots. No general mutable-area allowlist is needed. Later legitimate host-slot changes may trigger another safe refusal. Sanitized independent results are in `private/bt-persistence-research/confirmed-drift-results.json`.

## A second mutable area exists outside the SS variable section

The original custom application stores its three Bluetooth host slots and two application settings through ROM `0x174B4` (read) and `0x174FA` (write). These adapters use a separate configuration structure at `0x200A02`:

- uint32 at `0x200A03`: base **0xF000** in the saved installed RAM.
- uint32 at `0x200A07`: size **0x0FFF**, 4,095 bytes.
- I2C slave byte at `0x20101C`: **0xA0**.

The adapters check the supplied offset/length against that configured size and call EEPROM routines `0x2C97A`/`0x2C9B2` with **base + offset**. This explains why the previously preserved but unclassified F000 metadata is not necessarily constant. It is separate from SS's VS at1C0..3BF.

The actual application proves these precise destinations; ranges below are inclusive:

| EEPROM bytes | Length | Proven writer / reader | Meaning established by code |
|---|---:|---|---|
| F000 | 1 | write2081D0, read208138 | Selected host-slot index. Startup accepts0,1,2; SPI commands81/82/83 map to slots0/1/2. |
| F001..F026 | 38 (0x26) | write20823A, read208118 | Host slot0 record. |
| F027..F04C | 38 (0x26) | same, offset1+38*slot | Host slot1 record. |
| F04D..F072 | 38 (0x26) | same | Host slot2 record. |
| F074 | 1 | writes206D8A/206DA4, read206B2C | Sleep policy: AA disables the radio's600-second connection-sleep timer;55 enables it. SPI65/68 persists the changed value. |
| F075 | 1 | write206C10, read206B56 | Binary application mode at root208E80+3. SPI74/75 sets0/1. Exact user-facing meaning is not assigned here. |

**F073 is not included. No part of F076..FFFF is included.** The configured adapter can address a much larger area, but that is not evidence that every byte is legitimately mutable during this application’s ordinary operation.

Host records are opaque private state. `0x20820C` writes a four-byte header followed by34bytes copied from the current connection context; the leading marker is80. The other three header bytes are not explicitly initialized in that visible writer, so they should not be interpreted as a stable checksum or forced to zero. `0x208240` clears all three records using38zero bytes each. The record reader checks the leading80marker before considering a slot present. Do not publish the34-byte payloads; their exact private-field layout was not decoded in this task. A connection-completion path at207A2A calls this record writer when its state field is3, and slot switching at2081A2 persists the selected index.

The captured original and A86 baselines both have selectedslot0, slot markers80/00/00, sleepAA and applicationmode0. Those are historical baseline values. The subsequent stable second-slot change above fits the actual application's host-record writer; no updater command is required for such a change. This comparison identifies the storage mechanism, without claiming to reconstruct every user action that caused its new private contents.

## VS geometry and other write facilities

The saved radio configuration has VS base `[205E20]=1C0`, length halfword `[205E14]=0200`, derived end `[202DAC]=3C0`, and EEPROM VS block unit `[200C84]=40` (64bytes). The original ROM's record insertion/removal/compaction paths use that base and block unit:1D94C moves records,1DA0A invalidates blocks, and1E738 writes a record header plus its data. These paths explain normal activity inside the512-byte VS. No evidence here enlarges the VS boundary beyond3C0.

Other general ROM facilities can write outside these regions: the updater's74 adapter272A, config-record replacement1D28A, and diagnostic/HCI memory-write path27F86. Their existence is not evidence that they ran. No automatic update-header rewrite was established. In particular, ordinary settings writes above do not authorize differences in SS0, SS100, any old/current/candidate DS, or unexplained tail bytes. Keep those comparisons exact.

The low-level EEPROM writer splits transfers into at most14data bytes and avoids crossing its configured16-byte boundary. That is compatible with the identified128-byte physical page geometry. Settings writes therefore do not require overwriting a whole physical page; a change nearF000 is not grounds for accepting every byte of that page.

## Header/checksum success can hide a partial EEPROM read

GET72 pre-fills its destination withAA, calls the memory-read adapter, and constructs a successful checksummed reply without propagating the adapter's failure. The underlying EEPROM read loop at2C846 uses at most16data bytes per controller transaction. A32-byte request can therefore return **16correct bytes followed by16AA bytes**, with the correct address, length and protocol checksum, when only its second I2C transaction fails. This passes an all-AA-only rejection test.

`private/bt-persistence-research/test_eeprom_drift.py` executes the actual ROM GET handler, read adapter, EEPROM reader and multi-transaction loop, modeling only transaction completion/data and allocation. Three tests pass: successful two-part read, partial second-part failure returning a valid non-all-AA reply, and exact settings-adapter destinations for all six offset/length shapes. Results are in `eeprom-drift-test-results.json`. These prove a software failure mode, not that a physical read failed this time.

Independent16-byte rereads of every changed32-byte block isolate that particular partial-read ambiguity: a failed sole transaction leaves allAA and is rejected. Repeated consistent data still does not create a cryptographic EEPROM integrity check; controller-success data is checksummed as received. Preserve the first full read before diagnostics, then compare independent rereads and classify exactly which bytes differ. Do not automatically retry mutations or broaden the mutable mask on a failed read.

## Requirements for any later general comparison-policy revision

The current trial instead uses the narrower new-baseline approach above. The following records the evidence needed if a general mutable-state policy is considered later; it is not a request to implement one now.

1. Inspect the refused capture and independent changed-chunk rereads. Establish stable changes confined to the already allowed VS and precisely proven F000..F072/F074/F075 fields. If not, investigate the additional bytes rather than classify them as settings.
2. Keep exact A86 identity, extension, constructor hook, updater object/mode/boundary, SS selections and all protected-bank comparisons. The fresh full backup must preserve current host records and settings along with the VS; no payload should rewrite them.
3. Verify the live settings adapter baseF000, size0FFF and I2C slaveA0, and fingerprint the corresponding code. `private/bt-persistence-research/settings-fingerprints.json` provides address, length and SHA256 for ROM174B4..1753F and four exact unchanged application code ranges. These are fingerprints, not new commands issued by the advisor.
4. A future narrowly scoped mask should contain exactly `[1C0,3C0)`, `[F000,F073)`, `[F074,F076)`—and only after actual evidence and review establish this is the needed correction. Masking allF000..FFFF or updating the immutable baseline to unexplained data is unsupported.

There is no need to relax the guard while collecting this evidence. The pre-enable refusal prevented the update from starting and exposed a previously incomplete definition of mutable application state.
