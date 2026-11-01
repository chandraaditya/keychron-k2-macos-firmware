/* Default build has hardware programming COMPILED OUT. --plan is file-only.
 * --check queries only an already-entered bootloader; no normal-mode reboot.
 * Write capability can only be compiled in after explicit owner authorization.
 */
#include "sonix_core.h"
#include "sonix_lock.h"
#include <CommonCrypto/CommonDigest.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static const char expected_sha[]="0d5da2541dcc54be0909b6ce9fde79da46a20a45c38aafb3b26e35c7c97e4293";
typedef struct { IOHIDDeviceRef device; bool program_authorized; } native_context;

static void expired(int signal_number) {
    (void)signal_number;
    const char message[]="USB operation timed out; stopped without reset.\n";
    (void)write(STDERR_FILENO,message,sizeof(message)-1);_exit(1);
}
static bool native_send(void *opaque, enum k2_operation operation, const uint8_t data[64]) {
    native_context *ctx=opaque;
    if (operation==K2_READ_COMMAND) {
        if (data[0]!=1 && data[0]!=6) return false;
    } else {
#ifdef K2_ENABLE_HARDWARE_PROGRAMMING
        if (!ctx->program_authorized || (operation!=K2_PROGRAM_COMMAND && operation!=K2_IMAGE_BLOCK)) return false;
#else
        (void)ctx;return false;
#endif
    }
    alarm(8);
    IOReturn status=IOHIDDeviceSetReport(ctx->device,kIOHIDReportTypeFeature,0,data,64);
    alarm(0);return status==kIOReturnSuccess;
}
static bool native_receive(void *opaque,uint8_t data[64]) {
    native_context *ctx=opaque;CFIndex length=64;alarm(8);
    IOReturn status=IOHIDDeviceGetReport(ctx->device,kIOHIDReportTypeFeature,0,data,&length);
    alarm(0);return status==kIOReturnSuccess && length==64;
}
static bool load_image(const char *path,uint8_t image[65536]) {
    int fd=open(path,O_RDONLY|O_NOFOLLOW);
    if (fd<0) { perror("Image open");return false; }
    struct stat st;
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size!=65536) {
        fprintf(stderr,"Image must be a regular65536-byte file; no padding/modification is performed.\n");close(fd);return false;
    }
    size_t used=0;
    while (used<65536) { ssize_t n=read(fd,image+used,65536-used);if(n<=0){close(fd);return false;}used+=(size_t)n; }
    close(fd);
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(image,65536,digest);
    char hex[65];
    for(size_t i=0;i<sizeof(digest);i++)(void)snprintf(hex+i*2,3,"%02x",digest[i]);
    if (strcmp(hex,expected_sha)) { fprintf(stderr,"Image SHA256 differs from the reviewed candidate. No device opened.\n");return false; }
    return true;
}
int main(int argc,char **argv) {
    if(argc!=3 || (strcmp(argv[1],"--plan") && strcmp(argv[1],"--check") && strcmp(argv[1],"--flash"))) {
        fprintf(stderr,"Usage: k2-sonix-installer --plan|--check|--flash CANDIDATE.bin\n");return 2;
    }
    bool flash=!strcmp(argv[1],"--flash");
#ifndef K2_ENABLE_HARDWARE_PROGRAMMING
    if (flash) { fprintf(stderr,"Hardware programming is disabled in this build. No device opened.\n");return 2; }
#endif
    uint8_t image[65536];if(!load_image(argv[2],image))return 1;
    if(!strcmp(argv[1],"--plan")) {
        printf("{\"mode\":\"file-only-plan\",\"image_sha256\":\"%s\",\"bytes\":65536,\"offset\":0,"
               "\"blocks\":1024,\"word_sum\":%u,\"expected_security\":\"CS1\",\"expected_baseline\":48036,"
               "\"replaces_main_settings_with_reference_defaults\":true,\"device_access\":false}\n",expected_sha,k2_word_sum(image,sizeof(image)));
        return 0;
    }
    int lock=k2_sonix_lock();
    if(lock<0){fprintf(stderr,"Another bootloader operation is active, or its lock is unsafe. No device opened.\n");return 1;}
    signal(SIGALRM,expired);
    IOHIDManagerRef manager=IOHIDManagerCreate(NULL,0);
    int vid=0x0c45,pid=0x7040;
    CFNumberRef v=CFNumberCreate(NULL,kCFNumberIntType,&vid),p=CFNumberCreate(NULL,kCFNumberIntType,&pid);
    const void *keys[]={CFSTR(kIOHIDVendorIDKey),CFSTR(kIOHIDProductIDKey),CFSTR(kIOHIDTransportKey)};
    const void *values[]={v,p,CFSTR("USB")};
    CFDictionaryRef match=CFDictionaryCreate(NULL,keys,values,3,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    IOHIDManagerSetDeviceMatching(manager,match);CFRelease(match);CFRelease(v);CFRelease(p);
    int result=1;CFSetRef devices=NULL;IOHIDDeviceRef device=NULL;bool seized=false;
    if(IOHIDManagerOpen(manager,0)!=kIOReturnSuccess){fprintf(stderr,"Bootloader access failed.\n");goto done;}
    devices=IOHIDManagerCopyDevices(manager);
    CFIndex count=devices?CFSetGetCount(devices):0;
    if(count!=1){fprintf(stderr,"Expected one already-entered0c45:7040bootloader; found%ld. No commands sent.\n",(long)count);goto done;}
    CFSetGetValues(devices,(const void **)&device);
    if(flash) {
        if(IOHIDDeviceOpen(device,kIOHIDOptionsTypeSeizeDevice)!=kIOReturnSuccess){
            fprintf(stderr,"Exclusive bootloader access failed. No commands sent.\n");goto done;
        }
        seized=true;
    }
    native_context context={device,flash};
    k2_transport transport={&context,native_send,native_receive};k2_result outcome;
    if(!k2_run(transport,image,sizeof(image),0xbba4,flash,&outcome)) {
        fprintf(stderr,"Stopped: %s. Image blocks sent:%u.\n",outcome.error,outcome.successful_image_blocks);goto done;
    }
    printf("{\"mode\":\"%s\",\"verified\":true,\"security\":\"CS1\",\"baseline_checksum\":%u,"
           "\"candidate_checksum\":%u,\"image_blocks_sent\":%u,\"protection_change_requested\":false,\"reboot_requested\":false}\n",
           flash?"programmed-and-verified":"read-only-preflight",outcome.initial_checksum,outcome.image_checksum,outcome.successful_image_blocks);
    result=0;
done:
    if(seized)IOHIDDeviceClose(device,kIOHIDOptionsTypeSeizeDevice);
    if(devices)CFRelease(devices);IOHIDManagerClose(manager,0);CFRelease(manager);close(lock);return result;
}
