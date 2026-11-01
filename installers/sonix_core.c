/* Exact24xB protocol; no security, erase or reboot command exists here.
 * Source reference: SonixFlasherC73f9fab, device.c/flash.c/hid_io.h.
 * A simulation callback can exercise programming without any device library.
 */
#include "sonix_core.h"
#include <stdio.h>
#include <string.h>

static uint16_t u16(const uint8_t *p) {
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1]<<8);
}
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static bool fail(k2_result *r, const char *message) {
    (void)snprintf(r->error,sizeof(r->error),"%s",message);
    return false;
}
uint16_t k2_word_sum(const uint8_t *image, size_t length) {
    uint16_t sum=0;
    for (size_t i=0;i+1<length;i+=2) sum=(uint16_t)(sum+u16(image+i));
    return sum;
}
static bool reply(k2_transport t, unsigned command, uint8_t response[64], k2_result *r) {
    memset(response,0,64);
    if (!t.receive(t.context,response)) return fail(r,"USB reply failed; stopped without retry or reset");
    if (u32(response)!=((0x55aaU<<8)|command) || u32(response+4)!=0xfafafafaU)
        return fail(r,"Unexpected reply command/status; stopped without fallback");
    return true;
}
static bool read_command(k2_transport t, unsigned command, uint8_t response[64], k2_result *r) {
    if (command!=1 && command!=6) return fail(r,"Internal command allowlist rejected operation");
    uint8_t request[64]={0};request[0]=(uint8_t)command;request[1]=0xaa;request[2]=0x55;
    if (!t.send(t.context,K2_READ_COMMAND,request)) return fail(r,"USB query failed; no retry or reset");
    return reply(t,command,response,r);
}
static bool identity(const uint8_t p[64], k2_result *r) {
    if (p[8]!=32 || p[9]!=3 || p[11]!=0) return fail(r,"Unexpected controller family/revision");
    if (u16(p+14)!=0x5a5a) return fail(r,"Expected existing CS1 protection; refusing any security change");
    return true;
}
bool k2_run(k2_transport t, const uint8_t *image, size_t length,
            uint16_t baseline, bool program, k2_result *r) {
    if (!r) return false;
    memset(r,0,sizeof(*r));
    if (!image || length!=65536) return fail(r,"Image must be exactly65536bytes");
    if (u32(image+65532)!=0xaaaa5555U) return fail(r,"Unexpected image footer");
    if (!t.send || !t.receive) return fail(r,"Missing transport");
    r->image_checksum=k2_word_sum(image,length);
    uint8_t response[64];
    if (!read_command(t,1,response,r) || !identity(response,r)) return false;
    if (!read_command(t,6,response,r)) return false;
    r->initial_checksum=u16(response+8);
    if (r->initial_checksum!=baseline) return fail(r,"Installed checksum changed; image approval needs a fresh baseline");
    if (!program) { r->verified=true; return true; }

    /* Offset0,1024reports. No separate erase or protection downgrade. */
    uint8_t request[64]={5,0xaa,0x55};request[9]=4;
    r->program_enable_sent=true;
    if (!t.send(t.context,K2_PROGRAM_COMMAND,request)) return fail(r,"Program-enable transfer failed; keep bootloader connected");
    if (!reply(t,5,response,r)) return false;
    for (size_t i=0;i<1024;i++) {
        if (!t.send(t.context,K2_IMAGE_BLOCK,image+i*64))
            return fail(r,"Image transfer failed; stopped, no automatic retry/reset/security change");
        r->successful_image_blocks++;
    }
    if (!reply(t,5,response,r)) return false;
    if (u32(response+60)!=u32(image+65532)) return fail(r,"Programming final-word verification failed");
    if (u16(response+8)!=r->image_checksum) return fail(r,"Programming receipt checksum failed");
    if (!read_command(t,1,response,r) || !identity(response,r)) return false;
    if (!read_command(t,6,response,r)) return false;
    if (u16(response+8)!=r->image_checksum) return fail(r,"Whole-flash checksum verification failed");
    r->verified=true;
    return true;
}
