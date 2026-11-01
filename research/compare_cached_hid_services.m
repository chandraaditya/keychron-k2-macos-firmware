#import <Foundation/Foundation.h>
#import <IOBluetooth/IOBluetooth.h>

/* Read cached SDP only. Never query, connect, disconnect or set link policy. */
int main(void) {
    @autoreleasepool {
        NSMutableArray *devices = [NSMutableArray array];
        NSDictionary *attributes = @{
            @0x0201: @"HIDParserVersion", @0x0204: @"HIDVirtualCable",
            @0x0205: @"HIDReconnectInitiate", @0x0209: @"HIDBatteryPower",
            @0x020a: @"HIDRemoteWake", @0x020b: @"HIDProfileVersion",
            @0x020c: @"HIDSupervisionTimeout", @0x020d: @"HIDNormallyConnectable",
            @0x020e: @"HIDBootDevice", @0x020f: @"HIDSSRHostMaxLatency",
            @0x0210: @"HIDSSRHostMinTimeout"
        };
        for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) {
            NSString *name = [device name];
            BOOL keyboard = [name isEqualToString:@"Keychron K2"];
            BOOL trackpad = [name rangeOfString:@"Trackpad" options:NSCaseInsensitiveSearch].location != NSNotFound;
            if (!name || (!keyboard && !trackpad) || ![device isConnected]) continue;
            IOBluetoothSDPServiceRecord *hid = [device getServiceRecordForUUID:[IOBluetoothSDPUUID uuid16:0x1124]];
            NSMutableDictionary *row = [@{
                @"device": keyboard ? @"Keychron K2" : @"Apple Trackpad",
                @"connected": @YES, @"cached_hid_record_found": @(hid != nil)
            } mutableCopy];
            NSDate *updated = [device getLastServicesUpdate];
            if (updated) row[@"cached_services_date"] = [updated description];
            NSMutableDictionary *values = [NSMutableDictionary dictionary];
            for (NSNumber *attribute in attributes) {
                IOBluetoothSDPDataElement *element = [hid getAttributeDataElement:(BluetoothSDPServiceAttributeID)[attribute unsignedShortValue]];
                NSNumber *value = [element getNumberValue];
                values[attributes[attribute]] = value ?: (id)[NSNull null];
            }
            row[@"attributes"] = values;
            [devices addObject:row];
        }
        NSError *error = nil;
        NSData *json = [NSJSONSerialization dataWithJSONObject:devices options:NSJSONWritingPrettyPrinted error:&error];
        if (!json) { fprintf(stderr, "Could not encode cached attributes.\n"); return 1; }
        fwrite([json bytes], 1, [json length], stdout);
        putchar('\n');
    }
    return 0;
}
