/* OFFLINE ONLY. Exact captured ROM DS-parser callback adapter.
 * Writes SS0 validity byte0 only, bounded async I2C, then reads it back.
 * Failure arms the ROM's one-use config hook to load known A86 DS8000.
 * Host must first verify SS100 selects the untouched A86 bank8000.
 */
.syntax unified
.cpu cortex-m3
.thumb
.section .text,"ax",%progbits
.global one_boot_guard
.thumb_func
one_boot_guard:
    push {r4-r7, lr}
    sub sp, #12
    ldr r7, poll_budget
    /* Address00:00 + data00. Separate readback starts as FF. */
    movs r0, #0
    str r0, [sp, #8]
    movs r0, #0xa0
    str r0, [sp]
    movs r0, #1
    str r0, [sp, #4]
    add r0, sp, #10
    movs r1, #1
    add r2, sp, #8
    movs r3, #2
    ldr r4, =0x2c755
    blx r4
    bl wait_complete
    cmp r0, #1
    bne redirect
ack_probe:
    cmp r7, #0
    beq redirect
    add r0, sp, #8
    movs r1, #2
    movs r2, #0
    movs r3, #0
    blx r4
    bl wait_complete
    cmp r0, #3
    beq ack_probe
    cmp r0, #1
    bne redirect
    movs r0, #0
    str r0, [sp, #4]
    movs r0, #255
    strb r0, [sp, #11]
    add r0, sp, #11
    movs r1, #1
    add r2, sp, #8
    movs r3, #2
    blx r4
    bl wait_complete
    cmp r0, #1
    bne redirect
    ldrb r0, [sp, #11]
    cmp r0, #0
    bne redirect
    b done
redirect:
    ldr r0, =0x200c80
    ldr r1, redirect_address
    str r1, [r0]
done:
    add sp, #12
    pop {r4-r7, pc}

wait_complete:
    push {r4, lr}
    ldr r4, =0x2c6ff
poll:
    cmp r7, #0
    beq exhausted
    subs r7, #1
    lsls r0, r7, #22      /* Service existing watchdog each1024 polls. */
    bne poll_status
    ldr r0, =0x2c429
    blx r0
poll_status:
    blx r4
    cmp r0, #0
    beq poll
    pop {r4, pc}
exhausted:
    movs r0, #0
    pop {r4, pc}
redirect_once:
    movs r1, #0
    ldr r2, =0x200c80
    str r1, [r2]
    ldr r0, =0x8000
    ldr r2, =0x205e1c
    str r0, [r2]
    bx lr
code_end:
    .balign 4
redirect_address:
    .word 0               /* Builder fills exact redirect_once address|1. */
poll_budget:
    .word 100000
    .ltorg
