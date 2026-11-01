/* Simulation only: no HID, USB or framework dependency. Every output is checked.
 * Fault injection verifies stops before data on rejected identity/baseline/ACK,
 * stops at a failed data block, and refuses misleading completion receipts.
 */
#include "sonix_core.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum fault { NONE,FAMILY,REVISION,SECURITY,BASELINE,ENABLE_ACK,ENABLE_COMMAND,
             DATA_FAILURE,FINAL_COMMAND,FINAL_STATUS,FINAL_SUM,FINAL_WORD,
             POST_SECURITY,POST_SUM,SEND_FAILURE,RECEIVE_FAILURE };
typedef struct {
    const uint8_t *image;
    enum fault fault;
    unsigned sends,receives,blocks,reads,programs,last_command;
    bool awaiting_program_receipt,program_ack;
} fake;
static void w16(uint8_t *p,unsigned value) { p[0]=(uint8_t)value;p[1]=(uint8_t)(value>>8); }
static bool send_fake(void *opaque,enum k2_operation op,const uint8_t p[64]) {
    fake *f=opaque;f->sends++;
    if(f->fault==SEND_FAILURE)return false;
    if(op==K2_IMAGE_BLOCK) {
        assert(f->program_ack && f->programs==1 && f->blocks<1024);
        assert(!memcmp(p,f->image+f->blocks*64,64));
        if(f->fault==DATA_FAILURE && f->blocks==17)return false;
        f->blocks++;return true;
    }
    assert(p[1]==0xaa && p[2]==0x55 && p[3]==0);
    if(op==K2_READ_COMMAND) {
        assert(p[0]==1 || p[0]==6);
        for(unsigned i=4;i<64;i++)assert(p[i]==0);
        f->reads++;
    } else {
        assert(op==K2_PROGRAM_COMMAND && p[0]==5);
        assert(f->reads==2 && f->programs==0 && f->blocks==0);
        for(unsigned i=4;i<64;i++)assert(p[i]==(i==9?4:0));
        f->programs++;
    }
    f->last_command=p[0];return true;
}
static bool receive_fake(void *opaque,uint8_t p[64]) {
    fake *f=opaque;f->receives++;
    if(f->fault==RECEIVE_FAILURE)return false;
    memset(p,0,64);p[0]=(uint8_t)f->last_command;p[1]=0xaa;p[2]=0x55;memset(p+4,0xfa,4);
    if(f->last_command==1) {
        p[8]=(uint8_t)(f->fault==FAMILY?31:32);p[9]=3;
        p[11]=(uint8_t)(f->fault==REVISION?1:0);
        w16(p+14,((f->fault==SECURITY)||(f->fault==POST_SECURITY&&f->blocks==1024))?0:0x5a5a);
    } else if(f->last_command==6) {
        unsigned sum=f->blocks==1024?k2_word_sum(f->image,65536):0xbba4;
        if((f->fault==BASELINE&&f->blocks==0)||(f->fault==POST_SUM&&f->blocks==1024))sum^=1;
        w16(p+8,sum);
    } else {
        assert(f->last_command==5);
        if(f->blocks==0) {
            if(f->fault==ENABLE_ACK)p[4]=0;
            if(f->fault==ENABLE_COMMAND)p[0]=3;
            if(f->fault!=ENABLE_ACK && f->fault!=ENABLE_COMMAND)f->program_ack=true;
        } else {
            assert(f->blocks==1024);
            w16(p+8,k2_word_sum(f->image,65536));memcpy(p+60,f->image+65532,4);
            if(f->fault==FINAL_COMMAND)p[0]=6;
            if(f->fault==FINAL_STATUS)p[5]=0;
            if(f->fault==FINAL_SUM)p[8]^=1;
            if(f->fault==FINAL_WORD)p[60]^=1;
        }
    }
    return true;
}
static k2_result run(const uint8_t *image,enum fault fault,bool program,bool expected) {
    fake f={.image=image,.fault=fault};k2_result result;
    k2_transport t={&f,send_fake,receive_fake};
    assert(k2_run(t,image,65536,0xbba4,program,&result)==expected);
    assert(result.verified==expected);
    if(!program || fault==FAMILY || fault==REVISION || fault==SECURITY || fault==BASELINE || fault==SEND_FAILURE || fault==RECEIVE_FAILURE) {
        assert(f.programs==0 && f.blocks==0);
    }
    if(fault==ENABLE_ACK || fault==ENABLE_COMMAND)assert(f.programs==1 && f.blocks==0);
    if(fault==DATA_FAILURE)assert(f.blocks==17 && result.successful_image_blocks==17);
    if(expected && program)assert(f.blocks==1024 && f.reads==4 && f.programs==1 && f.receives==6);
    if(expected && !program)assert(f.reads==2 && f.programs==0 && f.receives==2);
    if(!expected)assert(result.error[0]);
    return result;
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *fp=fopen(argv[1],"rb");assert(fp);
    uint8_t *image=malloc(65536);assert(image);assert(fread(image,1,65536,fp)==65536);assert(fgetc(fp)==EOF);fclose(fp);
    assert(k2_word_sum(image,65536)==0x941d);
    unsigned cases=2;
    run(image,NONE,false,true);run(image,NONE,true,true);
    for(enum fault f=FAMILY;f<=RECEIVE_FAILURE;f++){run(image,f,true,false);cases++;}
    fake f={.image=image};k2_transport t={&f,send_fake,receive_fake};k2_result result;
    assert(!k2_run(t,image,65535,0xbba4,true,&result));assert(f.sends==0);
    image[65535]^=1;assert(!k2_run(t,image,65536,0xbba4,true,&result));assert(f.sends==0);
    free(image);
    cases+=2;
    printf("%u simulated transfer/validation cases passed; all1024imageblocks checked; no device access.\n",cases);
    return 0;
}
