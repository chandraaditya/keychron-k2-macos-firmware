#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <stdio.h>
#include <stdlib.h>

/* Read only the K2 battery collection; never capture keyboard input or write reports. */
int main(void) {
    int exit_code = 1;
    IOHIDManagerRef manager = IOHIDManagerCreate(kCFAllocatorDefault, 0);
    const void *keys[] = {CFSTR(kIOHIDProductKey), CFSTR(kIOHIDTransportKey)};
    const void *values[] = {CFSTR("Keychron K2"), CFSTR("Bluetooth")};
    CFDictionaryRef match = CFDictionaryCreate(NULL, keys, values, 2,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    IOHIDManagerSetDeviceMatching(manager, match);
    CFRelease(match);
    IOReturn status = IOHIDManagerOpen(manager, 0);
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "Keyboard access unavailable (0x%08x).\n", status);
        CFRelease(manager);
        return 1;
    }

    CFSetRef devices = IOHIDManagerCopyDevices(manager);
    CFIndex count = devices ? CFSetGetCount(devices) : 0;
    const void **list = calloc(count > 0 ? (size_t)count : 1, sizeof(void *));
    if (!list) goto cleanup;
    if (devices) CFSetGetValues(devices, list);
    IOHIDDeviceRef selected = NULL;
    unsigned candidates = 0;
    for (CFIndex i = 0; i < count; i++) {
        IOHIDDeviceRef device = (IOHIDDeviceRef)list[i];
        CFArrayRef elements = IOHIDDeviceCopyMatchingElements(device, NULL, 0);
        if (!elements) continue;
        for (CFIndex j = 0; j < CFArrayGetCount(elements); j++) {
            IOHIDElementRef element = (IOHIDElementRef)CFArrayGetValueAtIndex(elements, j);
            if (IOHIDElementGetUsagePage(element) == 6 &&
                IOHIDElementGetUsage(element) == 0x20 &&
                IOHIDElementGetReportID(element) == 3 &&
                IOHIDElementGetLogicalMin(element) == 0 &&
                IOHIDElementGetLogicalMax(element) == 100 &&
                IOHIDElementGetType(element) == kIOHIDElementTypeInput_Misc) {
                selected = device;
                candidates++;
                break;
            }
        }
        CFRelease(elements);
    }
    free(list);
    if (candidates != 1) {
        fprintf(stderr, "Expected one battery collection; found %u across %ld HID collections.\n",
            candidates, count);
        goto cleanup;
    }

    unsigned char bytes[2] = {0};
    CFIndex length = sizeof(bytes);
    status = IOHIDDeviceGetReport(selected, kIOHIDReportTypeInput, 3, bytes, &length);
    if (status != kIOReturnSuccess) {
        fprintf(stderr, "Battery read failed (0x%08x).\n", status);
    } else if (length != 2 || bytes[0] != 3 || bytes[1] > 100) {
        fprintf(stderr, "Keyboard returned an invalid battery report.\n");
    } else {
        printf("{\"device\":\"Keychron K2\",\"raw_battery_percent\":%u,\"validated\":false}\n", bytes[1]);
        fprintf(stderr, "Raw report only. Historical A05 reads returned 0 despite a higher Fn+B band; validate this reading separately.\n");
        exit_code = 0;
    }
cleanup:
    if (devices) CFRelease(devices);
    IOHIDManagerClose(manager, 0);
    CFRelease(manager);
    return exit_code;
}
