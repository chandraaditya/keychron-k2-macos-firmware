#define main bootloader_probe_main
#include "probe_sonix_bootloader.c"
#undef main
#include <assert.h>

int main(void) {
    uint8_t packet[64], before[64];
    for (unsigned command = 0; command < 256; command++) {
        memset(packet, 0xcc, sizeof(packet));
        memcpy(before, packet, sizeof(packet));
        bool allowed = make_query(command, packet);
        assert(allowed == (command == 1 || command == 6));
        if (!allowed) { assert(!memcmp(packet, before, sizeof(packet))); continue; }
        assert(packet[0] == command && packet[1] == 0xaa && packet[2] == 0x55);
        for (unsigned i = 3; i < 64; i++) assert(packet[i] == 0);
    }
    memset(packet, 0, sizeof(packet));
    packet[0]=1; packet[1]=0xaa; packet[2]=0x55;
    memset(packet+4, 0xfa, 4);
    assert(valid_reply(1, packet, 64));
    assert(!valid_reply(1, packet, 63));
    assert(!valid_reply(1, packet, 65));
    assert(!valid_reply(6, packet, 64));
    assert(!valid_reply(2, packet, 64));
    packet[4] ^= 1; assert(!valid_reply(1, packet, 64)); packet[4] ^= 1;
    assert(security_level(packet) == 0);
    packet[14]=packet[15]=0xff; assert(security_level(packet) == 0);
    packet[14]=packet[15]=0x5a; assert(security_level(packet) == 1);
    packet[14]=packet[15]=0xa5; assert(security_level(packet) == 2);
    packet[14]=0xaa; packet[15]=0x55; assert(security_level(packet) == -1);
    puts("Bootloader query allowlist and response-validation checks passed; no hardware access.");
    return 0;
}
