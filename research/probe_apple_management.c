/* Read-only Feature34/Input90 queries to one existing Lightning Trackpad
 * management interface. No SetReport, input callback, reset or pairing calls.
 * Do not print address, serial or raw device-information payloads. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <signal.h>
#include <stdbool.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void expired(int n){(void)n;_exit(2);}
static bool number(IOHIDDeviceRef d,CFStringRef k,int value){CFTypeRef p=IOHIDDeviceGetProperty(d,k);int n=-1;return p&&CFGetTypeID(p)==CFNumberGetTypeID()&&CFNumberGetValue(p,kCFNumberIntType,&n)&&n==value;}
static bool is_bluetooth(IOHIDDeviceRef d){CFTypeRef p=IOHIDDeviceGetProperty(d,CFSTR("Transport"));return p&&CFEqual(p,CFSTR("Bluetooth"));}
static bool addr_matches_serial(IOHIDDeviceRef d,const uint8_t *addr,bool reverse){
 CFTypeRef serial=IOHIDDeviceGetProperty(d,CFSTR("SerialNumber"));char text[256],normalized[13];unsigned at=0;
 if(!serial||CFGetTypeID(serial)!=CFStringGetTypeID()||!CFStringGetCString(serial,text,sizeof(text),kCFStringEncodingUTF8))return false;
 for(unsigned i=0;text[i]&&at<12;i++)if(isxdigit((unsigned char)text[i]))normalized[at++]=(char)tolower((unsigned char)text[i]);
 if(at!=12)return false;normalized[12]=0;char expected[13];
 for(unsigned i=0;i<6;i++)snprintf(expected+i*2,3,"%02x",addr[reverse?5-i:i]);
 return !strcmp(normalized,expected);
}
int main(void){
 signal(SIGALRM,expired);IOHIDManagerRef manager=IOHIDManagerCreate(NULL,0);int vendor=76,product=613;
 CFNumberRef v=CFNumberCreate(NULL,kCFNumberIntType,&vendor),p=CFNumberCreate(NULL,kCFNumberIntType,&product);
 const void *keys[]={CFSTR("VendorID"),CFSTR("ProductID"),CFSTR("Transport")},*values[]={v,p,CFSTR("Bluetooth")};
 CFDictionaryRef match=CFDictionaryCreate(NULL,keys,values,3,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);IOHIDManagerSetDeviceMatching(manager,match);CFRelease(match);CFRelease(v);CFRelease(p);
 int result=1;CFSetRef devices=NULL;IOHIDDeviceRef selected=NULL;unsigned count=0;const void **list=NULL;
 IOReturn status=IOHIDManagerOpen(manager,0);if(status){fprintf(stderr,"Read-only HID access failed0x%08x\n",status);goto done;}
 devices=IOHIDManagerCopyDevices(manager);CFIndex n=devices?CFSetGetCount(devices):0;list=calloc(n?n:1,sizeof(void*));if(!list)goto done;if(n)CFSetGetValues(devices,list);
 for(CFIndex i=0;i<n;i++){IOHIDDeviceRef d=(IOHIDDeviceRef)list[i];if(number(d,CFSTR("PrimaryUsagePage"),0xff00)&&number(d,CFSTR("PrimaryUsage"),0x0b)&&is_bluetooth(d)){selected=d;count++;}}
 if(count!=1){fprintf(stderr,"Expected one Trackpad management interface; found%u. No reports requested.\n",count);goto done;}
 uint8_t info[77]={0x34};CFIndex size=sizeof(info);alarm(5);status=IOHIDDeviceGetReport(selected,kIOHIDReportTypeFeature,0x34,info,&size);alarm(0);
 printf("{\"feature_34_status\":\"0x%08x\",\"feature_34_complete_bytes\":%ld",status,(long)size);
 if(!status&&size==77&&info[0]==0x34){printf(",\"device_info_version\":%u,\"address_matches_serial_forward\":%s,\"address_matches_serial_reverse\":%s",info[1],addr_matches_serial(selected,info+4,false)?"true":"false",addr_matches_serial(selected,info+4,true)?"true":"false");}
 uint8_t battery[3]={0x90};size=sizeof(battery);alarm(5);status=IOHIDDeviceGetReport(selected,kIOHIDReportTypeInput,0x90,battery,&size);alarm(0);
 printf(",\"input_90_status\":\"0x%08x\",\"input_90_complete_bytes\":%ld",status,(long)size);
 if(!status&&size==3&&battery[0]==0x90){printf(",\"battery_status_flags\":%u,\"battery_percent\":%u",battery[1],battery[2]);result=battery[2]<=100?0:1;}
 printf(",\"read_only\":true,\"private_identifiers_omitted\":true}\n");
 done:free(list);if(devices)CFRelease(devices);IOHIDManagerClose(manager,0);CFRelease(manager);return result;
}
