"""Small file-only ARM64 Mach-O reader for installed Apple binary inspection."""
import bisect
from pathlib import Path
import struct


class MachO:
    def __init__(self,path):
        self.path=Path(path);self.raw=self.path.read_bytes();self.image=self.raw
        if self.raw[:4]==bytes.fromhex('cafebabe'):
            n=struct.unpack_from('>I',self.raw,4)[0]
            arches=[struct.unpack_from('>IIIII',self.raw,8+i*20)for i in range(n)]
            a=next(a for a in arches if a[0]==0x100000c);self.image=self.raw[a[2]:a[2]+a[3]]
        if self.image[:4]!=bytes.fromhex('cffaedfe'):raise ValueError('Expected ARM64 Mach-O')
        self.sections=[];self.segments=[];self.functions=[];self.stubs={};self.symbols={}
        commands=struct.unpack_from('<I',self.image,16)[0];pos=32;symtab=dysymtab=None;encoded=b''
        for _ in range(commands):
            cmd,size=struct.unpack_from('<II',self.image,pos)
            if cmd==0x19:
                name=self.image[pos+8:pos+24].rstrip(b'\0').decode();vm,vmsize,off,filesize=struct.unpack_from('<QQQQ',self.image,pos+24)
                self.segments.append((name,vm,off,filesize))
                for i in range(struct.unpack_from('<I',self.image,pos+64)[0]):
                    p=pos+72+i*80;section=self.image[p:p+16].rstrip(b'\0').decode();address,length,offset=struct.unpack_from('<QQI',self.image,p+32)
                    flags,res1,res2=struct.unpack_from('<III',self.image,p+64)
                    self.sections.append((section,address,length,offset,flags,res1,res2))
            elif cmd==0x26:
                off,n=struct.unpack_from('<II',self.image,pos+8);encoded=self.image[off:off+n]
            elif cmd==2:symtab=struct.unpack_from('<IIII',self.image,pos+8)
            elif cmd==0xb:dysymtab=struct.unpack_from('<18I',self.image,pos+8)
            pos+=size
        self.base=next(v for n,v,_,_ in self.segments if n=='__TEXT')
        at=self.base;value=shift=0
        for b in encoded:
            value|=(b&127)<<shift
            if b&128:shift+=7
            else:
                if not value:break
                at+=value;self.functions.append(at);value=shift=0
        if symtab:
            symoff,n,stroff,strlen=symtab;names=[]
            for i in range(n):
                sx,kind,sect,desc,value=struct.unpack_from('<IBBHQ',self.image,symoff+i*16)
                stop=self.image.find(b'\0',stroff+sx);name=self.image[stroff+sx:stop].decode(errors='replace');names.append(name)
                if value:self.symbols[value]=name
            if dysymtab:
                off,nind=dysymtab[12:14];indices=struct.unpack_from('<'+'I'*nind,self.image,off)
                for section,addr,n,offset,flags,start,size in self.sections:
                    if flags&255==8 and size:
                        for i in range(n//size):
                            symbol=indices[start+i]
                            if symbol<len(names):self.stubs[addr+i*size]=names[symbol]
    def read(self,address,size):
        for _,vm,off,n in self.segments:
            if vm<=address and address+size<=vm+n:return self.image[off+address-vm:off+address-vm+size]
        raise ValueError(f'Address outside file mapping:{address:x}+{size:x}')
    def function(self,address):
        index=bisect.bisect_right(self.functions,address)-1
        return self.functions[index],self.functions[index+1]
    def cstring(self,address):
        for _,vm,off,n in self.segments:
            if vm<=address<vm+n:
                index=off+address-vm;return self.image[index:self.image.find(b'\0',index)].decode(errors='replace')
        return ''
    def cfstring(self,address):
        pointer,size=struct.unpack_from('<QQ',self.read(address+16,16));return self.read(self.base+(pointer&0xffffffff),size).decode()
    def named(self,address):return self.stubs.get(address,self.symbols.get(address,''))
