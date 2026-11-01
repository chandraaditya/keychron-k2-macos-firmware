/* Offline persistent-image integration for captured 2019 Bluetooth firmware.
 * A type-0A record loads this extension; the final type-0B invokes boot_entry.
 * Requires the verified NORMAL COLD-BOOT order, not an in-place hot reload.
 * All address_* slots are filled by the exact-input builder, not a linker.
 */
.syntax unified
.cpu cortex-m3
.thumb
.section .text,"ax",%progbits
.global boot_entry
.thumb_func
boot_entry:
    push {r4-r7, lr}
    sub sp, #4             /* Forward original callback with aligned stack. */
    ldr r12, =0x2067ed
    blx r12
    push {r0-r3}           /* Preserve original callback's caller-saved outputs. */
    ldr r4, =0x201344
    ldrb r0, [r4]
    cbnz r0, boot_done     /* Phase0: before heap/application-task construction. */
    ldr r4, =0x201350
    ldr r0, [r4]
    ldr r1, =0x209014
    cmp r0, r1
    bne boot_done
    ldr r5, =0x206aa8
    ldr r0, [r5]
    ldr r1, original_call_word
    cmp r0, r1
    bne boot_done
    ldr r0, reserved_end
    str r0, [r4]           /* Move the future application stack AND heap start. */
    ldr r0, replacement_call_word
    str r0, [r5]           /* Publish the RAM hook only after reservation. */
    dsb sy
    isb sy
boot_done:
    pop {r0-r3}
    add sp, #4
    pop {r4-r7, pc}

constructor_wrapper:
    push {r3-r7, lr}
    ldr r12, =0x208381
    blx r12                /* Forward the existing SPI singleton constructor. */
    mov r4, r0
    ldr r0, =0x208e80
    ldr r0, [r0, #0x28]    /* Resolve battery object after its constructor. */
    ldr r3, component_entry
    blx r3
    mov r0, r4             /* Preserve the original return used at 0x206aac. */
    pop {r3-r7, pc}
code_end:
    .balign 4
original_call_word:
    .word 0
replacement_call_word:
    .word 0
reserved_end:
    .word 0
component_entry:
    .word 0
    .ltorg
