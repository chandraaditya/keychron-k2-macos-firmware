/* Apple-management experiment for captured Bluetooth application. OFFLINE ONLY.
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
    str r6, [r4]           /* Publish only after the complete table is ready. */
    movs r0, #1
    pop {r3-r7, pc}
install_skip:
    movs r0, #0
    pop {r3-r7, pc}

get_report:
    cmp r1, #3
    bne check_apple_input
    cmp r2, #0x34
    bne get_original
    /* Original constructor stores the connection's display-order address+6. */
    push {r4-r7, lr}
    sub sp, #4
    ldr r4, [r0]
    adds r5, r0, #6
    movs r6, #0
copy_bdaddr:
    ldrb r7, [r5, r6]
    add r0, r4, r6
    strb r7, [r0, #76]
    adds r6, #1
    cmp r6, #6
    blo copy_bdaddr
    movs r0, #77
    strb r0, [r3]
    adds r0, r4, #72
feature_done:
    add sp, #4
    pop {r4-r7, pc}
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
code_end:
    .balign 4
address_getter:
    .word 0               /* Filled for an EMULATOR address by the test builder. */
address_notify:
    .word 0
address_connect:
    .word 0
    .ltorg
