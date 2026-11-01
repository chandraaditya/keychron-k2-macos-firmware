/* Read-only check of the same HID service properties used by bluetoothd. */
#include <CoreFoundation/CoreFoundation.h>
#include <stdbool.h>
#include <stdio.h>

typedef CFTypeRef IOHIDEventSystemClientRef;
typedef CFTypeRef IOHIDServiceClientRef;
extern IOHIDEventSystemClientRef IOHIDEventSystemClientCreate(CFAllocatorRef allocator);
extern CFArrayRef IOHIDEventSystemClientCopyServices(IOHIDEventSystemClientRef client);
extern CFTypeRef IOHIDServiceClientCopyProperty(IOHIDServiceClientRef service, CFStringRef key);

int main(void) {
    IOHIDEventSystemClientRef client = IOHIDEventSystemClientCreate(kCFAllocatorDefault);
    if (!client) { fprintf(stderr, "HID event client unavailable.\n"); return 1; }
    CFArrayRef services = IOHIDEventSystemClientCopyServices(client);
    unsigned matched = 0;
    for (CFIndex i = 0; services && i < CFArrayGetCount(services); i++) {
        IOHIDServiceClientRef service = CFArrayGetValueAtIndex(services, i);
        CFTypeRef product = IOHIDServiceClientCopyProperty(service, CFSTR("Product"));
        bool is_k2 = product && CFGetTypeID(product) == CFStringGetTypeID() &&
                     CFEqual(product, CFSTR("Keychron K2"));
        if (product) CFRelease(product);
        if (!is_k2) continue;
        matched++;
        CFTypeRef serial = IOHIDServiceClientCopyProperty(service, CFSTR("SerialNumber"));
        CFTypeRef capacity = IOHIDServiceClientCopyProperty(service, CFSTR("BatteryCapacity"));
        CFTypeRef probe = IOHIDServiceClientCopyProperty(service, CFSTR("K2BatteryBridgeProbeTransient"));
        printf("Transient bridge probe in fresh client: %s.\n", probe ? (CFGetTypeID(probe)==CFNullGetTypeID()?"null":"present") : "absent");
        if(probe)CFRelease(probe);
        printf("K2 HID service: serial identifier %s; BatteryCapacity %s.\n",
               serial ? "present" : "absent", capacity ? "present" : "absent");
        if (capacity && CFGetTypeID(capacity) == CFNumberGetTypeID()) {
            int value;
            if (CFNumberGetValue(capacity, kCFNumberIntType, &value))
                printf("Published BatteryCapacity: %d\n", value);
        }
        if (serial) CFRelease(serial);
        if (capacity) CFRelease(capacity);
    }
    printf("Matching K2 HID services: %u. No properties were changed.\n", matched);
    if (services) CFRelease(services);
    CFRelease(client);
    return matched ? 0 : 1;
}
