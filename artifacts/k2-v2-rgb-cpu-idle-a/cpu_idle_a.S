/* Reference-only K2 V2 RGB 1.13 experiment. No peripheral shutdown.
 * Build script resolves the sole external BL; all other references are local
 * branches or explicit constants. Never assemble this at a different hook.
 */
.syntax unified
.cpu cortex-m0
.thumb
.section .text,"ax",%progbits
.global cpu_idle_a
.thumb_func
cpu_idle_a:
    push {r3-r7, lr}         /* 24 bytes: preserve input and 8-byte alignment. */
original_call:
    .hword 0xf000, 0xf800    /* Builder replaces with direct BL 0x0194. */

    ldr r4, =0x20000166     /* Apply only when stock auto-sleep is disabled. */
    ldrb r0, [r4]
    cmp r0, #0
    beq idle_done
    ldr r4, =0x200001b8
    ldrb r0, [r4]
    cmp r0, #1              /* Wireless foreground path only. */
    bne idle_done
    ldr r4, =0x20000193
    ldrb r0, [r4]
    cmp r0, #0              /* Keep stock forced shutdown authoritative. */
    bne idle_done

    ldr r4, =0x40044000
    ldr r0, [r4]
    movs r1, #3            /* Both SPI attention lines must be quiet. */
    tst r0, r1
    bne idle_done
    ldr r4, =0x20000104
    ldrb r0, [r4]
    ldrb r1, [r4, #1]
    orrs r0, r1
    ldrb r1, [r4, #3]
    orrs r0, r1
    bne idle_done
    ldr r4, =0x20000188
    ldrb r0, [r4]
    cmp r0, #0
    bne idle_done
    ldr r4, =0x4001c014     /* Raw SPI IRQ status, NOT FIFO data. */
    ldr r0, [r4]
    movs r1, #4
    tst r0, r1
    bne idle_done

    mrs r0, primask
    cmp r0, #0
    bne idle_done           /* Never modify interrupt masks. */
    ldr r4, =0xe000ed10     /* Avoid exceptional SLEEPDEEP/SLEEPONEXIT state. */
    ldr r0, [r4]
    movs r1, #6
    tst r0, r1
    bne idle_done

    ldr r4, =0xe000e100
    ldr r0, [r4]
    ldr r1, =0x00010040     /* Scan timer IRQ16 and SPI IRQ6 enabled. */
    ands r0, r1
    cmp r0, r1
    bne idle_done
    ldr r4, =0x4005e000
    ldr r0, [r4]
    ldr r1, =0x00001080     /* CT16B1 and SPI peripheral clocks retained. */
    ands r0, r1
    cmp r0, r1
    bne idle_done
    ldr r4, =0x40002000
    ldr r0, [r4]
    movs r1, #1
    tst r0, r1             /* Existing timer must actually be running. */
    beq idle_done
    ldr r0, [r4, #0x1c]
    movs r1, #1
    lsls r1, r1, #12
    tst r0, r1             /* MR24 interrupt enabled, not just timer clock. */
    beq idle_done

    ldr r4, =0x40032040
    ldr r5, [r4]
    cmp r5, #0
    bne idle_done
    movs r0, #4            /* Sonix CPU-only Sleep; clocks stay as stock. */
    str r0, [r4]
    dsb sy
idle_wfi:
    wfi
    str r5, [r4]           /* Restore prior PMU value, including after IRQ. */
idle_done:
    pop {r3-r7, pc}
code_end:
    .balign 4
    .ltorg
