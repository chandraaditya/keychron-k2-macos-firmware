/* Identification only, for an ALREADY enumerated 0c45:7040 USB bootloader.
 * No firmware files, boot entry, reset, erase, program or security operations.
 * Protocol source: SonixFlasherC73f9fab, device.c/chip.c/hid_io.h.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "../installers/sonix_lock.h"

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 |
           (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}

static bool make_query(unsigned command, uint8_t out[64]) {
    if (command != 1 && command != 6) return false;
    memset(out, 0, 64);
    out[0] = (uint8_t)command;
    out[1] = 0xaa; out[2] = 0x55;
    return true;
}

static bool valid_reply(unsigned command, const uint8_t *p, CFIndex size) {
    return (command == 1 || command == 6) && size == 64 &&
           read32(p) == ((0x55aaU<<8) | command) && read32(p+4) == 0xfafafafa;
}

static int security_level(const uint8_t response[64]) {
    unsigned value = (unsigned)response[14] | (unsigned)response[15]<<8;
    if (value == 0 || value == 0xffff) return 0;
    if (value == 0x5a5a) return 1;
    if (value == 0xa5a5) return 2;
    return -1;
}

static void timeout(int signum) {
    (void)signum;
    const char message[] = "Bootloader identification timed out; stopped.\n";
    (void)write(STDERR_FILENO, message, sizeof(message)-1);
    _exit(1);
}

static bool query(IOHIDDeviceRef device, unsigned command, uint8_t reply[64]) {
    uint8_t request[64];
    if (!make_query(command, request)) return false;
    alarm(8);
    IOReturn status = IOHIDDeviceSetReport(device, kIOHIDReportTypeFeature,
                                         0, request, sizeof(request));
    if (status) {
        alarm(0);
        fprintf(stderr, "Identification request failed: %08x\n", status);
        return false;
    }
    memset(reply, 0, 64);
    CFIndex size = 64;
    status = IOHIDDeviceGetReport(device, kIOHIDReportTypeFeature, 0, reply, &size);
    alarm(0);
    if (status || !valid_reply(command, reply, size)) {
        fprintf(stderr, "Identification reply rejected (status %08x, length %ld).\n",
                status, (long)size);
        return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1], "--detect") && strcmp(argv[1], "--query"))) {
        fprintf(stderr, "Usage: probe-sonix-bootloader --detect | --query\n");
        return 2;
    }
    bool active = !strcmp(argv[1], "--query");
    int lock=-1;
    if(active && (lock=k2_sonix_lock())<0) {
        fprintf(stderr,"Another bootloader operation is active, or its lock is unsafe. No device opened.\n");return 1;
    }
    signal(SIGALRM, timeout);
    const void *keys[] = {CFSTR(kIOHIDVendorIDKey), CFSTR(kIOHIDProductIDKey), CFSTR(kIOHIDTransportKey)};
    int vid = 0x0c45, pid = 0x7040;
    CFNumberRef vendor = CFNumberCreate(NULL, kCFNumberIntType, &vid);
    CFNumberRef product = CFNumberCreate(NULL, kCFNumberIntType, &pid);
    const void *values[] = {vendor, product, CFSTR("USB")};
    CFDictionaryRef match = CFDictionaryCreate(NULL, keys, values, 3,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    IOHIDManagerRef manager = IOHIDManagerCreate(NULL, 0);
    IOHIDManagerSetDeviceMatching(manager, match);
    CFRelease(match); CFRelease(vendor); CFRelease(product);
    int result = 1;
    CFSetRef devices = NULL;
    IOReturn opened = IOHIDManagerOpen(manager, 0);
    if (opened) { fprintf(stderr, "HID identification access failed: %08x\n", opened); goto cleanup; }
    devices = IOHIDManagerCopyDevices(manager);
    CFIndex count = devices ? CFSetGetCount(devices) : 0;
    if (!active) {
        printf("{\"usb_id\":\"0c45:7040\",\"matching_collections\":%ld,\"commands_sent\":0}\n", (long)count);
        result = 0; goto cleanup;
    }
    if (count != 1) {
        fprintf(stderr, "Expected exactly one 0c45:7040 USB bootloader; found %ld. No commands sent.\n", (long)count);
        goto cleanup;
    }
    IOHIDDeviceRef device;
    CFSetGetValues(devices, (const void **)&device);
    uint8_t response[64];
    if (!query(device, 1, response)) goto cleanup;
    int level = security_level(response);
    if (response[8] != 32 || response[9] != 3 || level < 0) {
        fprintf(stderr, "Unexpected chip family/security; no further query sent.\n");
        goto cleanup;
    }
    unsigned revision = response[11];
    if (!query(device, 6, response)) goto cleanup;
    unsigned checksum = (unsigned)response[8] | (unsigned)response[9]<<8;
    printf("{\"usb_id\":\"0c45:7040\",\"family\":\"SN32F24xB\",\"profile_flash_bytes\":65536,"
           "\"revision\":%u,\"security_level\":%d,\"flash_checksum\":%u,"
           "\"commands_sent\":2,\"flashed\":false,\"protection_changed\":false}\n", revision, level, checksum);
    result = 0;
cleanup:
    if (devices) CFRelease(devices);
    IOHIDManagerClose(manager, 0); CFRelease(manager);
    if(lock>=0)close(lock);
    return result;
}
