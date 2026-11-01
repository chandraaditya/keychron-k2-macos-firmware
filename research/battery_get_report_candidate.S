/* Offline experiment only. Not a complete firmware or a deployable image.
 * Original ABI: r0=battery object, r1=report type, r2=report ID,
 * r3=output report size (in bits). Returns report buffer or NULL.
 * A real integration would replace the object's get-report virtual method.
 */
.syntax unified
.cpu cortex-m3
.thumb
.section .text
.global battery_get_report_candidate
.thumb_func
battery_get_report_candidate:
    cmp r1, #1
    bne original
    ldr r12, battery_config
    ldrb.w r12, [r12, #0x11]
    cmp r2, r12
    bne original
    ldrb.w r12, [r0, #0x14]
    cmp.w r12, #100
    bhi invalid
    strb.w r12, [r0, #5]
original:
    ldr r12, original_get_report
    bx r12
invalid:
    movs r0, #0
    bx lr
.align 2
battery_config:
    .word 0x2005c8
original_get_report:
    .word 0x290b
