#include <CoreFoundation/CoreFoundation.h>
#include <CommonCrypto/CommonDigest.h>
#include <IOKit/hid/IOHIDManager.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <unistd.h>

/* Only identification and SETUP_READ/READ. No ENABLE, ERASE, WRITE or LAUNCH. */
static IOHIDDeviceRef selected;
typedef struct {
    unsigned percent;
    unsigned cached_percent;
    uint32_t sensor_average_raw;
} BatterySample;

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static bool valid_memory_response(const uint8_t *bytes, CFIndex size,
                                  uint32_t address, unsigned length) {
    if (!length || length > 32 || size != length + 8 || bytes[0] != 0x72 ||
        le32(bytes + 1) != address || bytes[5] != length || bytes[6]) return false;
    unsigned sum = 0;
    for (CFIndex i = 0; i < size; i++) sum += bytes[i];
    return !(sum & 255);
}

static void timeout_handler(int signum) {
    (void)signum;
    const char message[] = "Read timeout; stopped.\n";
    (void)write(STDERR_FILENO, message, sizeof(message) - 1);
    _exit(1);
}

static bool memory_read(uint32_t address, unsigned length, uint8_t *out) {
    if (!length || length > 32) return false;
    uint8_t setup[8] = {0x71, address, address >> 8, address >> 16,
                        address >> 24, length, 0, 0};
    for (unsigned i = 0; i < 7; i++) setup[7] -= setup[i];
    alarm(8);
    IOReturn status = IOHIDDeviceSetReport(selected, kIOHIDReportTypeFeature,
                                          0x71, setup, sizeof(setup));
    if (status) {
        alarm(0);
        fprintf(stderr, "SETUP_READ failed at 0x%08x: %08x\n", address, status);
        return false;
    }
    uint8_t response[40] = {0x72};
    CFIndex size = length + 8;
    status = IOHIDDeviceGetReport(selected, kIOHIDReportTypeFeature, 0x72,
                                 response, &size);
    alarm(0);
    if (status) {
        fprintf(stderr, "READ failed at 0x%08x: %08x\n", address, status);
        return false;
    }
    if (!valid_memory_response(response, size, address, length)) {
        fprintf(stderr, "Read header/checksum mismatch at 0x%08x.\n", address);
        return false;
    }
    memcpy(out, response + 7, length);
    return true;
}

static bool valid_object_pointer(uint32_t pointer) {
    return pointer >= 0x209000 && pointer <= 0x210000 - 0x74 && !(pointer & 3);
}

static bool valid_patched_methods(const uint8_t *bytes, size_t size) {
    static const uint32_t expected[15] = {
        0x28a9,0x28dd,0x209141,0x209119,0x209145,0x2949,0x296d,0x298b,
        0x298f,0x2993,0x29cd,0x2a11,0x2a2f,0x2aaf,0x2ac1
    };
    if (size != sizeof(expected)) return false;
    for (size_t i=0;i<15;i++) if (le32(bytes+4*i)!=expected[i]) return false;
    return true;
}

static bool verify_custom_extension(void) {
    uint8_t bytes[440],digest[CC_SHA256_DIGEST_LENGTH],hook[4];
    static const uint8_t expected[] = {
        0x6f,0x6f,0x74,0x4b,0x89,0x8e,0x97,0x87,0xc0,0xd7,0xed,0xab,0x60,0x77,0xa7,0x1c,
        0x73,0xa5,0x08,0x7b,0xfd,0xbf,0x3e,0x92,0x5d,0xc9,0x56,0x57,0x52,0x3b,0x33,0xf8
    };
    for (unsigned i=0;i<sizeof(bytes);) {
        unsigned n=sizeof(bytes)-i<32?(unsigned)sizeof(bytes)-i:32;
        if(!memory_read(0x209014+i,n,bytes+i))return false;
        i+=n;
    }
    CC_SHA256(bytes,sizeof(bytes),digest);
    if(memcmp(digest,expected,sizeof(digest)) || !memory_read(0x206aa8,4,hook) ||
       memcmp(hook,(uint8_t[]){0x02,0xf0,0xd3,0xfa},4)) {
        fprintf(stderr,"Custom radio extension/hook mismatch.\n");return false;
    }
    return true;
}

static bool read_battery(BatterySample *sample, bool custom) {
    /* Installed code: getLevel loads object+0x14; Fn+B compares it to 70 and 30. */
    static const uint8_t code[] = {
        0x00,0x7d,0x70,0x47,0x10,0xb5,0x04,0x46,0xf8,0xf5,0x09,0xfc,0x21,0x7d,
        0x46,0x29,0x03,0xd9,0xd0,0xf8,0x20,0x01,0x0d,0x4a,0x08,0xe0,0xd0,0xf8,
        0x20,0x01,0x1e,0x29,0x02,0xd9,0x0a,0x4a,0x12,0x1f,0x01,0xe0,0x09,0x4a,
        0x08,0x3a,0xbd,0xe8,0x10,0x40,0x03,0x21,0x00,0xf0,0xd2,0xb8
    };
    uint8_t actual[sizeof(code)];
    if (!memory_read(0x2082be, 32, actual) ||
        !memory_read(0x2082de, sizeof(code) - 32, actual + 32)) return false;
    if (memcmp(actual, code, sizeof(code))) {
        fprintf(stderr, "Battery code fingerprint mismatch; refusing to interpret memory.\n");
        return false;
    }
    const uint8_t caller[] = {0xb0,0x6a,0x01,0xf0,0x7e,0xfa};
    uint8_t check[6];
    if (!memory_read(0x206dc0, sizeof(check), check)) return false;
    if (memcmp(check, caller, sizeof(check))) {
        fprintf(stderr, "Battery indicator caller mismatch.\n"); return false;
    }
    uint8_t pointer_bytes[4], vtable[4], again[4], value[1], cache[2], sensor[4];
    if (!memory_read(0x206dfc, 4, pointer_bytes) || le32(pointer_bytes) != 0x208e80) {
        fprintf(stderr, "Battery global-layout mismatch.\n"); return false;
    }
    if (!memory_read(0x208ea8, 4, pointer_bytes)) return false;
    uint32_t pointer = le32(pointer_bytes);
    if (!valid_object_pointer(pointer)) {
        fprintf(stderr, "Battery object pointer outside supported RAM.\n"); return false;
    }
    if (!memory_read(pointer, 4, vtable)) return false;
    if(custom) {
        uint32_t table=le32(vtable);uint8_t methods[60];
        if(pointer>0x20ef00-0x74 || table<0x2091cc || table>0x20ef00-68 || (table&3) ||
           !verify_custom_extension() || !memory_read(table,32,methods) ||
           !memory_read(table+32,28,methods+32) || !valid_patched_methods(methods,sizeof(methods))) {
            fprintf(stderr,"A86 battery method table mismatch.\n");return false;
        }
    } else if(le32(vtable)!=0x4c2f4) {
        fprintf(stderr,"Battery object type mismatch.\n");return false;
    }
    if (!memory_read(pointer + 0x14, 1, value) ||
        !memory_read(pointer + 4, 2, cache) ||
        !memory_read(pointer + 0x5c, 4, sensor) ||
        !memory_read(0x208ea8, 4, again)) return false;
    if (memcmp(pointer_bytes, again, 4) || value[0] > 100 || cache[0] != 3 || cache[1] > 100) {
        fprintf(stderr, "Battery object changed or returned an invalid percentage.\n"); return false;
    }
    sample->percent = value[0];
    sample->cached_percent = cache[1];
    sample->sensor_average_raw = le32(sensor);
    return true;
}

static bool allowed_range(unsigned long address, unsigned long length) {
    if (!length || length > 0x10000 || address > UINT32_MAX) return false;
    /* Direct ROM and RAM only. No device registers, EEPROM or flash operations. */
    return (address < 0x80000 && length <= 0x80000 - address) ||
           (address >= 0x200000 && address < 0x210000 &&
            length <= 0x210000 - address);
}

/* AN214820 defines the OTA virtual EEPROM window at 0xff000000.
 * Separate opt-in READ command; never treat this as directly mapped memory.
 * This permits backup reads only, not ENABLE/ERASE/WRITE/LAUNCH.
 */
static bool allowed_eeprom_read(unsigned long offset, unsigned long length) {
    return length && offset < 0x10000 && length <= 0x10000 - offset;
}

int main(int argc, char **argv) {
    if (argc != 1 && argc != 2 && argc != 5) {
        fprintf(stderr, "Usage: keychron-battery [battery | sample | version | dump ADDRESS LENGTH NEW_FILE | eeprom OFFSET LENGTH NEW_FILE]\n");
        return 2;
    }
    bool detailed = argc == 2 && !strcmp(argv[1], "sample");
    bool battery = argc == 1 || detailed || (argc == 2 && !strcmp(argv[1], "battery"));
    bool dump = argc == 5 && !strcmp(argv[1], "dump");
    bool eeprom = argc == 5 && !strcmp(argv[1], "eeprom");
    unsigned long address = 0, length = 0;
    if (dump || eeprom) {
        char *end;
        errno = 0; address = strtoul(argv[2], &end, 0);
        if (errno || *end) return 2;
        errno = 0; length = strtoul(argv[3], &end, 0);
        if (errno || *end || !(eeprom ? allowed_eeprom_read(address, length)
                                     : allowed_range(address, length))) return 2;
        if (eeprom) address += 0xff000000UL;
    } else if (!battery && (argc != 2 || strcmp(argv[1], "version"))) return 2;
    signal(SIGALRM, timeout_handler);
    int lock = open("private/read.lock", O_CREAT | O_RDWR | O_NOFOLLOW, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) {
        fprintf(stderr, "Cannot acquire private/read.lock.\n");
        return 1;
    }
    int result = 1;
    IOHIDManagerRef manager = IOHIDManagerCreate(NULL, 0);
    const void *keys[] = {CFSTR(kIOHIDProductKey), CFSTR(kIOHIDTransportKey)};
    const void *values[] = {CFSTR("Keychron K2"), CFSTR("Bluetooth")};
    CFDictionaryRef match = CFDictionaryCreate(NULL, keys, values, 2,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    IOHIDManagerSetDeviceMatching(manager, match); CFRelease(match);
    IOHIDManagerScheduleWithRunLoop(manager, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    IOReturn status = IOHIDManagerOpen(manager, 0);
    CFSetRef devices = NULL;
    if (status) { fprintf(stderr, "HID access failed: %08x\n", status); goto cleanup; }
    devices = IOHIDManagerCopyDevices(manager);
    CFIndex count = devices ? CFSetGetCount(devices) : 0;
    const void **list = calloc(count ? (size_t)count : 1, sizeof(void *));
    if (!list) goto cleanup;
    if (devices) CFSetGetValues(devices, list);
    unsigned candidates = 0;
    for (CFIndex i = 0; i < count; i++) {
        CFArrayRef elements = IOHIDDeviceCopyMatchingElements((IOHIDDeviceRef)list[i], NULL, 0);
        if (!elements) continue;
        for (CFIndex j = 0; j < CFArrayGetCount(elements); j++) {
            IOHIDElementRef e = (IOHIDElementRef)CFArrayGetValueAtIndex(elements, j);
            if (IOHIDElementGetReportID(e) == 0xb2 &&
                IOHIDElementGetType(e) == kIOHIDElementTypeOutput) {
                selected = (IOHIDDeviceRef)list[i]; candidates++; break;
            }
        }
        CFRelease(elements);
    }
    free(list);
    if (candidates != 1) { fprintf(stderr, "Expected one diagnostic collection, found %u.\n", candidates); goto cleanup; }
    /* Read the identity record directly. No output-report request or key callback. */
    const uint8_t expected[] = {0xb1,0x25,0x05,0x0a,0xc0,0x02,'2','0','1','9','1','0','2','5'};
    uint8_t version[sizeof(expected)];
    static const uint8_t custom_expected[] = {0xb1,0x25,0x86,0x0a,0xc0,0x02,'2','0','2','6','1','0','2','8'};
    if (!memory_read(0x208f02, sizeof(version), version)) goto cleanup;
    bool custom=!memcmp(version,custom_expected,sizeof(custom_expected));
    if(!custom && memcmp(version,expected,sizeof(expected))) {
        fprintf(stderr,"Unsupported radio application identity; refusing layout interpretation.\n");goto cleanup;
    }
    if (battery) {
        BatterySample sample;
        if (read_battery(&sample,custom)) {
            printf("{\"device\":\"Keychron K2\",\"battery_percent\":%u,"
                   "\"source\":\"firmware_indicator_state\",\"firmware_build\":\"%s\"",
                   sample.percent,custom?"20261028":"20191025");
            if (detailed) printf(",\"cached_report_percent\":%u,\"sensor_average_raw\":%u",
                                  sample.cached_percent, sample.sensor_average_raw);
            puts("}");
            result = 0;
        }
        goto cleanup;
    }
    printf("Verified Bluetooth build identity: %s (version byte 0x%02x).\n",custom?"20261028":"20191025",version[2]);
    if (!dump && !eeprom) { result = 0; goto cleanup; }
    int fd = open(argv[4], O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) { perror("New snapshot file"); goto cleanup; }
    unsigned long offset = 0;
    for (; offset < length;) {
        uint8_t bytes[32];
        unsigned block = length - offset < sizeof(bytes) ? (unsigned)(length - offset) : sizeof(bytes);
        if (!memory_read((uint32_t)(address + offset), block, bytes)) break;
        if (write(fd, bytes, block) != block) { perror("Snapshot write"); break; }
        offset += block;
        if (!(offset % 4096)) { printf("Read %lu / %lu bytes.\n", offset, length); fflush(stdout); }
    }
    close(fd);
    if (offset == length) {
        printf("Saved %lu bytes from 0x%08lx; all block checksums verified.\n", length, address);
        result = 0;
    } else fprintf(stderr, "Incomplete snapshot: %lu / %lu bytes.\n", offset, length);
cleanup:
    selected = NULL;
    if (devices) CFRelease(devices);
    IOHIDManagerUnscheduleFromRunLoop(manager, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    IOHIDManagerClose(manager, 0); CFRelease(manager);
    close(lock);
    return result;
}
