# Installed K2 Bluetooth image: persistent battery-patch integration review

2026-10-27. Astra. Offline review of the parent's guarded read-only captures; no device access or changes by this investigation. This is a design review, not a flashable image or deployment clearance.

## Stronger basis than the downloaded update

The exact installed EEPROM capture identifies SS at 0, VS at 0x1C0–0x3BF, and DS at 0x3C0–0x39F2 inclusive. The VS contains pairing material and remains private. These locations differ from the unrelated downloaded 1.09 reference. The active-prefix capture is a backup of the decoded active sections, not proof of whole-chip capacity, page size, or an independently working recovery route.

Every byte of the 9,800-byte application loaded at 0x206838–0x208E7F matches the earlier runtime RAM capture. The 76-byte startup block at 0x2067EC also matches. The data block at 0x208E80 has expected runtime modifications, and the early patch block at 0x205EA0 has 12 changed bytes. Therefore, patch the original EEPROM-loaded bytes using verified mappings, not an indiscriminate runtime-RAM-to-EEPROM conversion.

The C4 record decodes into address/value pairs `(0x60021C,0x6D8)`, `(0x600220,0x6D8)`, `(0x600224,0x6D8)`, `(0x600344,0x20)`. ROM 0x1D59A–0x1D5C2 reads each eight-byte pair and directly stores the value to the address. This is register programming, not a RAM reservation. The registers’ hardware meanings remain unestablished; preserve the record.

## What startup and allocation now establish

The final type-0B record points to 0x2067ED. That function:

1. Skips a data copy because source and end literals are both 0x208E78.
2. Calls ROM 0x48370 to zero 0x3C bytes beginning at 0x208FD8, ending at 0x209014. ROM 0x48370 is the zero-fill primitive.
3. Calls ROM 0x40E86. If it returns zero, writes 0x209014 to global 0x201350.
4. Tail-calls 0x2085D0, which registers application constructor 0x206839 at global 0x200400; it does not itself construct the application.

ROM 0x40E86 is a hardware-status probe. It temporarily changes MMIO 0x32007C, samples bit 2 at 0x360428 repeatedly, restores saved MMIO, and returns a Boolean. Its exact hardware-mode meaning is not yet established. It is not itself an allocator.

The constructor allocates objects through ROM 0x1676E → 0x16754 → 0x2D222 → 0x2917C. The final routine is a four-byte-aligned bump allocator using cursor 0x200E90. It rejects reaching 0x20F000 and asserts on reaching 0x20EF00. ROM initializer 0x291C8 receives the arena start in r0, records it at 0x20104C, reserves four times the halfword at 0x20103C, then constructs runtime pools.

The existing runtime snapshot has 0x201350 = 0x20104C = 0x209014, halfword 0x20103C = 0x180, and cursor 0x200E90 = 0x20CC80. This gives 0x2280 (8,832) bytes between the observed cursor and the assertion boundary. It supports the plausibility of a small extension; it does not establish worst-case headroom. The 0x600-byte reservation is also used by OS-task creation at ROM 0x2D56E; it must not be treated as spare code space.

The complete 320-KiB captured ROM now establishes the normal cold-start ordering:

1. ROM 0x47B86 sets the preliminary arena pointer, runs optional pre-initialization, then calls 0x1C798.
2. 0x1C798 obtains the DS offset and tail-calls 0x1D15C. That loop calls TLV parser 0x1CBCA until the terminating record.
3. Type 0A at 0x1CDB2 copies the record’s bytes to its RAM destination. Type 0B at 0x1CDD4 calls trampoline 0x29F30, which branches to the requested Thumb entry while preserving the parser return address.
4. The final installed 0B runs the startup described above and returns to that parser. Its final branch registers the application constructor; it does not call the constructor.
5. Only after 0x1C798 returns does 0x47B86 tail-call 0x403C6, creating the initialization task with entry 0x401D3 and stack at 0x205660, below the application extension.
6. That task loads arena pointer 0x201350 at 0x40326 and calls allocator initialization 0x291C8 at 0x40328. This is the sole direct BL/B.W caller of that initializer in the complete ROM; no literal word matching its function pointer was found.
7. Later, 0x2D56E creates the application task using the stack reservation based on the initialized arena. Its stack therefore moves with the arena start.

Thus aligned 0x209014, immediately after the original BSS, is a defensible **cold-boot candidate code location**, if the final 0B installer reserves through the extension’s aligned end before arming the constructor hook. Existing application globals and original BSS need not move. This resolves the normal-boot heap-overlap gate; it does not prove every computed entry path or make live configuration reload safe.

The proposed installer should call original 0x2067EC first, require heap-start global 0x201350 still equals 0x209014, and require startup phase byte 0x201344 equals zero. ROM 0x2CFEC initializes that phase to zero before DS loading; the initialization task changes it before heap setup. Only after reserving the extension should the installer replace the constructor call. If either guard fails, it should leave the constructor unchanged and return. These guards do not make an incorrectly hot-loaded type-0A record safe: the copy occurs before the installer. Activation remains cold-boot-only.

Independent Unicorn execution of the original trampoline/startup/ROM zero-fill/constructor registration passed both modeled Boolean outcomes of hardware probe 0x40E86. It preserved R4–R11 and SP, returned to the parser, cleared exactly 0x208FD8–0x209013, and left 512 sentinel bytes at 0x209014 untouched. Probe result zero set the expected arena; result one left the earlier arena pointer, so the proposed guard would decline installation. This is a focused ABI/BSS check, not full reset, scheduler, candidate, or physical-memory validation.

The other two direct calls to TLV parser 0x1CBCA are static-section parsing loops at 0x1D120 and 0x1D152. The installed final callback is in the DS handled by 0x1D164. Static direct-call and literal scans cannot exclude arbitrary computed calls; no hot-load authorization follows from this analysis.

## Constructor hook and battery component review

The exact installed constructor loads its newly constructed battery object at 0x206AA4, stores it at global root 0x208E80 + 0x28, and calls 0x208380 at 0x206AA8. A wrapper at this call can preserve the original return value while installing a battery-specific vtable override. It must resolve the object through the root rather than hardcode the snapshot object address.

The captured ROM table at 0x4C2F4 has 15 entries. Offset +8 points to notifier 0x28E3; +0xC points to getter 0x290B. Copy every entry, substitute only the intended methods, and publish the new table pointer last. Use storage proven reserved with the code or storage obtained from the existing allocator. Validate the original vtable pointer and preserve the constructor ABI. If allocation fails, leave the original table unchanged.

The query-handler prototype already emulates refresh of the standard cache from the measured percentage. A complete notification fix must additionally prove the changed notifier is actually called in the installed application's control flow; merely overriding an unused virtual method would not fix periodic publication. The parent is tracing that call path. A corrected HID report still does not establish native macOS battery UI publication.

A smaller type-08 ROM-patch record could theoretically replace the notifier's BHS with BEQ without extra RAM. Thirteen existing records use indices 0–12, each with 15 payload bytes. That does not prove slot 13 is available, the complete loader record semantics, or whether ROM uses additional slots. Do not substitute an unverified patch-slot mechanism for an unverified allocation mechanism. Neither is cleared just because the bytes fit.

The current component’s method offsets and transport calling convention match the captured ROM. The installer copies all 15 methods, allocates 68 bytes through the existing allocator, validates the expected original table, and publishes the replacement last. The reviewed version checks cursor alignment and the allocator’s assertion boundary before allocation. It also retains the validated measured battery byte across clock calls. These checks improve fail-soft behavior but do not establish worst-case memory demand or eliminate every concurrent-allocation concern.

The component tests use a mocked allocator and transport; they cannot prove real allocation failure returns null or that the host accepts a notification. The clock helper and 28-bit wrap handling are ROM-derived; the 60-second interpretation depends on the Bluetooth half-slot clock rate. The getter, notifier and connection hook still require integration tests in the relocated candidate, and native macOS UI publication remains separate.

## Read safety and recovery limits

[Manufacturer AN214820](https://www.infineon.com/assets/row/public/documents/30/42/infineon-an214820-eeprom-format-information-and-firmware-upgrading-applicationnotes-en.pdf?fileId=8ac78c8c7cdc391c017d0d27da5a62fd) explicitly defines EEPROM virtual base 0xFF000000 and commands 71/72 as SETUP_READ/READ, separately from enable, erase, write and launch. Its example reads static sections before enabling updates. This supports the parent's separated, bounded backup-read implementation. It also documents UART download fallback when no valid SS is found; it does not guarantee fallback for a valid SS pointing to a broken application. Actual radio UART access remains unverified.

The same note requires new SS/DS blocks to avoid current SS/DS/VS and verification before activation. Its sample code should not be copied literally: the Perl example writes the current DS offset into the new SS, and the C example's validity assignments are inconsistent. Use the stated transaction design and an independently checked implementation. A zero-filled captured tail is not proof that a second full DS fits without address wrap.

The actual ROM update reader at 0x26C6 pre-fills its destination with 0xAA, then sends FF-prefixed requests through the EEPROM reader at 0x2C97A. The latter transmits a two-byte address and has no observed capacity lookup or 16-KiB clamp. Below offset 0x10000 the update reader uses I²C address byte 0xA0; bit 16 selects another address. Consequently, captured zeros at 0x4000 are not explained by a visible software zero-fill beyond a 16-KiB limit. Absence of an SS alias there weakens ordinary 16-KiB wrap as an explanation, but does not prove the EEPROM’s physical size or write-page geometry. An inactive-bank update plan still needs those facts or equally strong physical evidence.

[Manufacturer AN214822](https://www.infineon.com/dgdl/Infineon-AN214822_CYW20730_Downloading_Firmware_to_CYW20730_Modules_Using_Bluetool-ApplicationNotes-v03_00-EN.pdf?fileId=8ac78c8c7cdc391c017d0d27eafd6305) documents UART/BlueTool downloading on reference boards, including a minidriver and chip erase. That proves a manufacturer recovery mechanism exists; it is not a ready-to-use recovery recipe for this keyboard or permission to erase it.

Local redacted evidence: `private/bt-persistence-research/integration-analysis.json` records load ranges, patch records, startup literals, runtime-boundary observation and the ROM vtable without including addresses of paired Bluetooth devices or their keys.

Additional reproducible offline evidence: `private/bt-persistence-research/boot-and-reader-disassembly.txt`, `boot-evidence.json`, `check_boot_contract.py`, and `boot-contract-results.json`. The ROM hash is recorded in those artifacts. No candidate was flashed, no live configuration was loaded, and this review does not clear flashing.
