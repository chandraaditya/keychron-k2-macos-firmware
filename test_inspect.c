#define main inspect_program_main
#include "inspect.c"
#undef main
#include <assert.h>
#include <limits.h>

int main(void) {
    assert(allowed_range(0x200000, 0x10000));
    assert(allowed_range(0x20ffff, 1));
    assert(!allowed_range(0x20ffff, 2));
    assert(!allowed_range(0x210000, 1));
    assert(!allowed_range(0x40000000, 32));
    assert(!allowed_range(0xff000000, 32));
    assert(!allowed_range(ULONG_MAX, 32));
    assert(!allowed_range(0x200000, 0));
    assert(allowed_eeprom_read(0, 0x10000));
    assert(allowed_eeprom_read(0xffff, 1));
    assert(!allowed_eeprom_read(0xffff, 2));
    assert(!allowed_eeprom_read(0x10000, 1));
    assert(!allowed_eeprom_read(0, 0));
    assert(!allowed_eeprom_read(0, 0x10001));
    assert(!allowed_eeprom_read(ULONG_MAX, 32));
    assert(!allowed_eeprom_read(0xff000000, 32));
    assert(valid_object_pointer(0x20c9d4));
    assert(!valid_object_pointer(0x20c9d5));
    assert(!valid_object_pointer(0x208000));
    assert(!valid_object_pointer(0x20fff0));

    uint8_t response[9] = {0x72,0xe8,0xc9,0x20,0,1,0,58,0};
    for (unsigned i = 0; i < 8; i++) response[8] -= response[i];
    assert(valid_memory_response(response, 9, 0x20c9e8, 1));
    assert(!valid_memory_response(response, 8, 0x20c9e8, 1));
    assert(!valid_memory_response(response, 9, 0x20c9e9, 1));
    assert(!valid_memory_response(response, 9, 0x20c9e8, 0));
    assert(!valid_memory_response(response, 9, 0x20c9e8, 33));
    response[7]++;
    assert(!valid_memory_response(response, 9, 0x20c9e8, 1));
    response[7]--;
    response[0] = 0x73;
    assert(!valid_memory_response(response, 9, 0x20c9e8, 1));
    uint32_t methods[15] = {0x28a9,0x28dd,0x209141,0x209119,0x209145,0x2949,0x296d,
        0x298b,0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1};
    assert(valid_patched_methods((const uint8_t *)methods,sizeof(methods)));
    assert(!valid_patched_methods((const uint8_t *)methods,sizeof(methods)-1));
    for(unsigned i=0;i<15;i++){
        methods[i]^=2;assert(!valid_patched_methods((const uint8_t *)methods,sizeof(methods)));methods[i]^=2;
    }
    /* An original ROM getter inside an otherwise plausible A86 table is not accepted. */
    methods[3]=0x290b;assert(!valid_patched_methods((const uint8_t *)methods,sizeof(methods)));
    puts("Read-response validation and address-boundary checks passed (no hardware access).");
    return 0;
}
