/* Temporary property experiment on one exact K2 service. Default probes a
 * custom property; explicit --battery-trial publishes a caller-validated value.
 * Recreate the Bluetooth service to clear test properties: CFNull did not
 * remove the underlying property. No firmware or pairing records are written. */
#include <CoreFoundation/CoreFoundation.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef CFTypeRef IOHIDEventSystemClientRef;
typedef CFTypeRef IOHIDServiceClientRef;
extern IOHIDEventSystemClientRef IOHIDEventSystemClientCreate(CFAllocatorRef);
extern CFArrayRef IOHIDEventSystemClientCopyServices(IOHIDEventSystemClientRef);
extern CFTypeRef IOHIDServiceClientCopyProperty(IOHIDServiceClientRef,CFStringRef);
extern Boolean IOHIDServiceClientSetProperty(IOHIDServiceClientRef,CFStringRef,CFTypeRef);
static bool string_property(IOHIDServiceClientRef s,CFStringRef key,CFStringRef expected){
 CFTypeRef v=IOHIDServiceClientCopyProperty(s,key);bool yes=v&&CFGetTypeID(v)==CFStringGetTypeID()&&CFEqual(v,expected);if(v)CFRelease(v);return yes;
}
static bool number_property(IOHIDServiceClientRef s,CFStringRef key,int expected){
 CFTypeRef v=IOHIDServiceClientCopyProperty(s,key);int n=-1;bool yes=v&&CFGetTypeID(v)==CFNumberGetTypeID()&&CFNumberGetValue(v,kCFNumberIntType,&n)&&n==expected;if(v)CFRelease(v);return yes;
}
int main(int argc,char **argv){
 bool battery=argc==3&&!strcmp(argv[1],"--battery-trial");int battery_percent=-1;
 if(battery){char *end;long value=strtol(argv[2],&end,10);if(*end||value<0||value>100)return 2;battery_percent=(int)value;}
 else if(argc!=1)return 2;
 IOHIDEventSystemClientRef client=IOHIDEventSystemClientCreate(NULL);if(!client)return 1;
 CFArrayRef services=IOHIDEventSystemClientCopyServices(client);IOHIDServiceClientRef selected=NULL;unsigned count=0;
 for(CFIndex i=0;services&&i<CFArrayGetCount(services);i++){
  IOHIDServiceClientRef s=CFArrayGetValueAtIndex(services,i);
  if(string_property(s,CFSTR("Product"),CFSTR("Keychron K2"))&&string_property(s,CFSTR("Transport"),CFSTR("Bluetooth"))&&number_property(s,CFSTR("VendorID"),0x05ac)&&number_property(s,CFSTR("ProductID"),0x024f)){selected=s;count++;}
 }
 int result=1;
 if(count!=1){fprintf(stderr,"Expected one exact Bluetooth K2 service; found%u. No properties changed.\n",count);goto done;}
 CFStringRef key=battery?CFSTR("BatteryCapacity"):CFSTR("K2BatteryBridgeProbeTransient");CFTypeRef old=IOHIDServiceClientCopyProperty(selected,key);
 if(old){CFRelease(old);fprintf(stderr,"Probe property already exists; no change.\n");goto done;}
 int value=battery?battery_percent:1;CFNumberRef n=CFNumberCreate(NULL,kCFNumberIntType,&value);if(!n)goto done;
 Boolean set=IOHIDServiceClientSetProperty(selected,key,n);CFRelease(n);
 CFTypeRef actual=IOHIDServiceClientCopyProperty(selected,key);bool appeared=actual!=NULL;if(actual)CFRelease(actual);
 if(battery){printf("{\"battery_trial_setter_success\":%s,\"local_readback_present\":%s,\"battery_percent\":%d,\"cleanup_requires_Bluetooth_service_reconnect\":true}\n",set?"true":"false",appeared?"true":"false",battery_percent);result=0;goto done;}
 Boolean removed=false;bool absent=!appeared;
 if(appeared){removed=IOHIDServiceClientSetProperty(selected,key,kCFNull);actual=IOHIDServiceClientCopyProperty(selected,key);absent=actual==NULL;if(actual)CFRelease(actual);}
 printf("{\"exact_K2_service_matched\":true,\"setter_returned_success\":%s,\"probe_appeared\":%s,\"remove_returned_success\":%s,\"probe_absent_after_test\":%s,\"battery_property_changed\":false}\n",set?"true":"false",appeared?"true":"false",removed?"true":"false",absent?"true":"false");
 result=absent?0:1;
 done:if(services)CFRelease(services);CFRelease(client);return result;
}
