/* A93: A92 (full F-row, Fn translation, battery keyhole) plus an accepted Apple
 * SET_CONNECTION_INTERVAL_CONTROL (feature C6). Offline source.
 * Separate from installed A86. Status bits remain zero; charging flags unverified.
 * Code placement and boot hook are deliberately unresolved here.
 * Public installer takes the dynamically resolved battery object in R0.
 * Its shadow table is allocated through the existing allocator, never placed
 * at the captured object's address or in an assumed unused RAM hole.
 */
.syntax unified
.cpu cortex-m3
.thumb
.section .text,"ax",%progbits
.global battery_install
.thumb_func
battery_install:
    push {r3-r7, lr}
    mov r4, r0
    cmp r4, #0
    beq install_skip
    tst r4, #3
    bne install_skip
    ldr r1, =0x200000
    cmp r4, r1
    blo install_skip
    ldr r1, =0x20ef8c
    cmp r4, r1
    bhi install_skip
    ldr r0, =0x208d30     /* Root SET slot in this exact original app table. */
    ldr r0, [r0]
    ldr r1, =0x206ad5
    cmp r0, r1
    bne install_skip
    ldr r5, [r4]
    ldr r1, =0x4c2f4
    cmp r5, r1
    bne install_skip       /* Also makes installation idempotent. */
    ldr r0, =0x200e90      /* Existing bump cursor; avoid known fatal OOM bound. */
    ldr r0, [r0]
    tst r0, #3
    bne install_skip
    ldr r1, =0x200000
    cmp r0, r1
    blo install_skip
    ldr r1, =0x20ee68      /* cursor + 152 must be strictly below 0x20ef00. */
    cmp r0, r1
    bhs install_skip
    movs r0, #152          /* A86 state68 + Input90 buffer4 + Feature34 buffer77 + pad3. */
    ldr r3, =0x1676f
    blx r3
    cbz r0, install_skip
    mov r6, r0
    tst r6, #3
    bne install_skip
    ldr r1, =0x200000
    cmp r6, r1
    blo install_skip
    ldr r1, =0x20ef68
    cmp r6, r1
    bhi install_skip
    movs r7, #0
copy_methods:
    ldr r0, [r5, r7]
    str r0, [r6, r7]
    adds r7, #4
    cmp r7, #60
    blo copy_methods
    ldr r0, address_notify
    str r0, [r6, #8]
    ldr r0, address_getter
    str r0, [r6, #12]
    ldr r0, address_connect
    str r0, [r6, #16]
    movs r0, #0
    str r0, [r6, #60]
    str r0, [r6, #64]
    /* Clear new report state. No address or guessed charging bits in image. */
    movs r7, #68
clear_apple:
    str r0, [r6, r7]
    adds r7, #4
    cmp r7, #152
    blo clear_apple
    movs r0, #0x90
    strb r0, [r6, #68]
    movs r0, #0x34
    strb r0, [r6, #72]
    movs r0, #3
    strb r0, [r6, #73]
    dmb sy
    str r6, [r4]           /* Publish initialized state before the SET hook. */
    dmb sy
    ldr r0, =0x208d30
    ldr r1, address_setter
    str r1, [r0]
    movs r0, #1
    pop {r3-r7, pc}
install_skip:
    movs r0, #0
    pop {r3-r7, pc}

/* Apple SET FF receives a one-byte body: report ID was stripped by ROM.
 * All other type/ID/length shapes retain the original root setter and ABI.
 */
root_set_report:
    cmp r2, #3
    bne set_original
    cmp r3, #0xc6
    beq set_connection_interval
    cmp r3, #0xff
    bne set_original
    ldr r12, [sp, #4]
    cmp r12, #1
    bne set_original
    ldr r12, [sp]
    cmp r12, #0
    beq set_original
    ldrb.w r12, [r12]
    ldr r0, =0x208ea8
    ldr r0, [r0]
    ldr r0, [r0]
    movs r2, #0
    strb r2, [r0, #150]   /* Unsupported new selection invalidates old state. */
    cmp r12, #2
    beq selector_supported
    cmp r12, #0x34
    beq selector_supported
    cmp r12, #0x90
    beq selector_supported
    movs r0, #2
    bx lr
selector_supported:
    strb.w r12, [r0, #149]
    movs r2, #1
    strb r2, [r0, #150]
    movs r0, #0
    bx lr
/* macOS sends feature C6 (slots, attempts, multiplier) right after connecting
 * and retries it for ~9 s while the original setter rejects it. Its HID queue
 * holds the kernel's keyboard-configuration GET behind those retries, past the
 * kernel's 5 s timeout. Acknowledge it; the host sets sniff itself.
 */
set_connection_interval:
    movs r0, #0
    bx lr
set_original:
    ldr r12, =0x206ad5
    bx r12

get_report:
    cmp r2, #0xf1
    beq get_keyboard_keyhole
    cmp r1, #3
    bne check_battery_keyhole
    cmp r2, #2
    beq get_keyboard_direct
check_battery_keyhole:
    cmp r2, #0xf0
    beq get_keyhole
    cmp r1, #3
    bne check_apple_input
    cmp r2, #0x34
    bne get_original
feature_info:
    /* Original constructor stores the connection's display-order address+6. */
    push {r4-r7, lr}
    sub sp, #4
    ldr r4, [r0]
    adds r5, r0, #6
    movs r7, #0x34
    strb r7, [r4, #72]
    movs r7, #3
    strb r7, [r4, #73]
    movs r7, #0
    strh r7, [r4, #74]    /* Reset fields overwritten by a short F0/90 reply. */
    movs r6, #0
copy_bdaddr:
    ldrb r7, [r5, r6]
    add r0, r4, r6
    strb r7, [r0, #76]
    adds r6, #1
    cmp r6, #6
    blo copy_bdaddr
    cmp r2, #0xf0
    beq feature_keyhole
    movs r0, #77
    strb r0, [r3]
    adds r0, r4, #72
    b feature_done
feature_keyhole:
    movs r0, #0xf0
    strb r0, [r4, #71]
    movs r0, #78
    strb r0, [r3]
    adds r0, r4, #71
feature_done:
    add sp, #4
    pop {r4-r7, pc}
/* Apple keyboard configuration uses F1, distinct from management F0.
 * Feature2 is version1/ANSI plus F1-F4, F7-F12 action pairs.
 * Input2 retains the original consumer-report path.
 */
get_keyboard_keyhole:
    cmp r1, #3
    bne get_invalid
    ldr r12, [r0]
    ldrb.w r0, [r12, #150]
    cmp r0, #1
    bne get_invalid
    ldrb.w r0, [r12, #149]
    cmp r0, #2
    bne get_invalid
    adr r0, keyboard_configuration
    movs r1, #26
    strb r1, [r3]
    bx lr
get_keyboard_direct:
    adr r0, keyboard_configuration
    adds r0, #1
    movs r1, #25
    strb r1, [r3]
    bx lr
get_keyhole:
    ldr r12, [r0]
    ldrb.w r12, [r12, #150]
    cmp r12, #1
    bne get_invalid
    ldr r12, [r0]
    ldrb.w r12, [r12, #149]
    cmp r1, #3
    bne keyhole_input
    cmp r12, #0x34
    bne get_invalid
    b feature_info
keyhole_input:
    cmp r1, #1
    bne get_invalid
    cmp r12, #0x90
    bne get_invalid
    ldrb.w r12, [r0, #0x14]
    cmp r12, #100
    bhi get_invalid
    ldr r0, [r0]
    strb.w r12, [r0, #74]
    movs r1, #0xf0
    strb r1, [r0, #71]
    movs r1, #0x90
    strb r1, [r0, #72]
    movs r1, #0
    strb r1, [r0, #73]
    movs r1, #4
    strb r1, [r3]
    adds r0, #71
    bx lr
check_apple_input:
    cmp r1, #1
    bne get_original
    cmp r2, #0x90
    bne check_legacy
    ldrb.w r12, [r0, #0x14]
    cmp.w r12, #100
    bhi get_invalid
    ldr r0, [r0]
    strb.w r12, [r0, #70]
    movs r1, #3
    strb r1, [r3]
    adds r0, #68
    bx lr
check_legacy:
    cmp r1, #1
    bne get_original
    ldr r12, =0x2005c8
    ldrb.w r12, [r12, #0x11]
    cmp r2, r12
    bne get_original
    ldrb.w r12, [r0, #0x14]
    cmp.w r12, #100
    bhi get_invalid
    strb.w r12, [r0, #5]
get_original:
    ldr r12, =0x290b
    bx r12
get_invalid:
    movs r0, #0
    bx lr

notify:
    movs r2, #0
    b send_common
connected:
    movs r2, #1            /* Correct first report even when unchanged. */
send_common:
    push {r2-r6, lr}       /* Stack slots 0/4 become the existing send arguments. */
    mov r4, r0
    mov r5, r1
    cbz r5, send_done
    ldrb r0, [r4, #0x14]
    cmp r0, #100
    bhi send_done
    str r0, [sp]          /* Keep the validated byte across both clock calls. */
    ldr r6, [r4]
    cmp r2, #0
    bne send_now
    ldrb r1, [r4, #5]
    cmp r0, r1
    beq send_done
    ldr r0, [r6, #64]
    cbz r0, send_now
    ldr r0, [r6, #60]
    ldr r3, =0x16deb      /* Original elapsed-clock helper handles 28-bit wrap. */
    blx r3
    ldr r1, =192000       /* 60 seconds at 3200 Bluetooth half-slot ticks/sec. */
    cmp r0, r1
    blo send_done
send_now:
    ldr r3, =0x16db3
    blx r3
    str r0, [r6, #60]
    ldr r0, [sp]
    strb r0, [r4, #5]
    movs r0, #1
    str r0, [r6, #64]
    str r0, [sp]
    movs r0, #0
    str r0, [sp, #4]
    ldr r0, [r5]
    ldr r6, [r0, #0x2c]
    adds r1, r4, #4
    ldr r0, =0x2005c8
    ldrb r2, [r0, #0x12]
    movs r3, #1
    mov r0, r5
    blx r6                /* Preserve the standard report3. */
    ldr r6, [r4]
    ldrb r0, [r4, #5]
    strb r0, [r6, #70]
    adds r1, r6, #68
    ldr r0, [r5]
    ldr r6, [r0, #0x2c]
    movs r2, #3
    movs r3, #1
    mov r0, r5
    blx r6                /* Same transport; additional complete Input90. */
send_done:
    pop {r2-r6, pc}
/* Called by BL from the original scanner-frame handler at 0x206c9a, replacing
 * its `ldrb.w r0, [sp, #8]`. K2 sends Fn as 01 in report1's last byte; Apple's
 * descriptor reads bit0 as Eject and bits1..7 as Fn, so shift it into place.
 * SP is the caller's (BL pushes nothing); LR is restored by the caller's pop.
 */
    .global fn_shift
    .thumb_func
fn_shift:
    ldrb.w r0, [sp, #8]
    lsls r0, r0, #1
    bx lr
    .balign 4
keyboard_configuration:
    .byte 0xf1, 0x02, 0x01, 0x01, 0x00, 0x00
    .byte 0x01, 0x06, 0x02, 0x07, 0x03, 0x11, 0x04, 0x10   /* F1-F4: brightness-/+, Mission Control, Launchpad */
    .byte 0x07, 0x0a, 0x08, 0x0c, 0x09, 0x0b               /* F7-F9: rewind, play/pause, fast-forward */
    .byte 0x0a, 0x0d, 0x0b, 0x0e, 0x0c, 0x0f               /* F10-F12: mute, volume-/+ */
code_end:
    .balign 4
address_setter:
    .word 0
address_getter:
    .word 0               /* Filled for an EMULATOR address by the test builder. */
address_notify:
    .word 0
address_connect:
    .word 0
    .ltorg
