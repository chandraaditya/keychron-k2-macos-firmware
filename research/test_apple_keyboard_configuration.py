"""Offline execution of native Apple keyboard configuration/F-key parsing.
Apple instructions run in Unicorn with PAC removed. OS allocation, string
creation/formatting and virtual property publication are modeled. No HID APIs.
"""
import sys,struct,runpy,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN
ROOT=Path(__file__).resolve().parents[1]
x=runpy.run_path(str(ROOT/'private/apple-profile/inspect_keyboard_driver.py'))
READ=x['read'];SEGS=x['segments'];MD=Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN)
D=0xfffffe0007000000-0x100000000
OBJ,VT,BUF,BVT,PAY,STACK,STOP,STUB,OSOBJ,OSVT=0x20000000,0x20001000,0x20002000,0x20003000,0x20004000,0x21000000,0x22000000,0x22001000,0x20005000,0x20006000
CONFIG=bytes.fromhex('02 01 01 00 00 0A 0D 0B 0E 0C 0F')
def a(v):return v-D

def machine():
 u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
 for vm,n,off in SEGS:
  if vm==0xfffffe000ce60000:continue
  start=a(vm)&~4095;end=(a(vm)+n+4095)&~4095
  u.mem_map(start,end-start);data=bytearray(READ(vm,n))
  if vm==0xfffffe0009712190:
   for ins in MD.disasm(bytes(data),a(vm)):
    op=None
    if ins.mnemonic in ['pacibsp','autibsp','autda','xpacd','bti']:op=0xd503201f
    elif ins.mnemonic=='retab':op=0xd65f03c0
    elif ins.mnemonic in ['blraa','braa']:
     reg=int(ins.op_str.split(',')[0].strip()[1:]);op=(0xd63f0000 if ins.mnemonic=='blraa' else 0xd61f0000)|(reg<<5)
    if op is not None:struct.pack_into('<I',data,ins.address-a(vm),op)
  u.mem_write(a(vm),bytes(data))
 for addr in [OBJ,STACK,STOP]:u.mem_map(addr,0x10000)
 def q(addr,value):u.mem_write(addr,struct.pack('<Q',value))
 q(OBJ,VT);q(BUF,BVT);q(OSOBJ,OSVT)
 q(a(0xfffffe00081ad708),OBJ+0x8000);q(OBJ+0x8000,0x12345678)
 q(VT+0xb88,a(0xfffffe0009715b94));q(VT+0xb90,a(0xfffffe0009715bd4))
 # Parser's model-only object services; actual createFKeyMapping is used.
 q(VT+0xb70,STUB);q(VT+0xb78,STUB+4);q(VT+0xb80,STUB+8)
 q(VT+0xb68,a(0xfffffe0009715724));q(VT+0xb60,STUB+12)
 q(VT+0x288,STUB+16);q(BVT+0x1f0,STUB+20);q(BVT+0x308,STUB+24);q(OSVT+0x28,STUB+28)
 u.mem_write(PAY,CONFIG);u.reg_write(UC_ARM64_REG_SP,STACK+0x8000);u.reg_write(UC_ARM64_REG_X30,STOP)
 records=[];strings=[]
 def string(addr):
  out=bytearray()
  while (c:=u.mem_read(addr+len(out),1)[0]):out.append(c)
  return out.decode()
 def hook(u,pc,size,user):
  r=[u.reg_read(UC_ARM64_REG_X0+i) for i in range(6)] # X registers contiguous
  result=None
  if pc==a(0xfffffe0009718078): # snprintf, Apple variadic args on stack
   sp=u.reg_read(UC_ARM64_REG_SP);src,dst=struct.unpack('<QQ',u.mem_read(sp,16));s=f'0x{src:08x},0x{dst:08x},'.encode()
   u.mem_write(r[0],s[:max(0,r[1]-1)]+b'\0');result=len(s)
  elif pc==a(0xfffffe0009717fa8):strings.append(string(r[0]));result=OSOBJ
  elif pc in [STUB,STUB+4,STUB+8]:result=0 # metadata factories intentionally omitted
  elif pc==STUB+12:result=0 # CapsLock-language switch independent from Fn map
  elif pc==STUB+16:records.append((string(r[1]),r[2]));result=1
  elif pc==STUB+20:result=len(CONFIG)
  elif pc==STUB+24:result=PAY
  elif pc==STUB+28:result=0
  if result is not None:u.reg_write(UC_ARM64_REG_X0,result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
 u.hook_add(UC_HOOK_CODE,hook)
 return u,strings,records
class KeyboardConfigurationTests(unittest.TestCase):
 def test_native_parser_publishes_exact_volume_mapping(self):
  u,strings,records=machine();u.reg_write(UC_ARM64_REG_X0,OBJ);u.reg_write(UC_ARM64_REG_X1,BUF);u.reg_write(UC_ARM64_REG_X2,1)
  u.emu_start(a(0xfffffe00097164cc),STOP,count=10000)
  self.assertEqual(strings,['0x00070043,0x000c00e2,0x00070044,0x000c00ea,0x00070045,0x000c00e9'])
  self.assertIn(('FnFunctionUsageMap',OSOBJ),records)
 def test_A91_full_frow_mapping(self):
  global CONFIG
  old,CONFIG=CONFIG,bytes.fromhex('02 01 01 00 00 01 06 02 07 03 11 04 10 07 0A 08 0C 09 0B 0A 0D 0B 0E 0C 0F')
  try:
   u,strings,records=machine();u.reg_write(UC_ARM64_REG_X0,OBJ);u.reg_write(UC_ARM64_REG_X1,BUF);u.reg_write(UC_ARM64_REG_X2,1)
   u.emu_start(a(0xfffffe00097164cc),STOP,count=40000)
  finally:CONFIG=old
  self.assertEqual(strings,['0x0007003a,0xff010021,0x0007003b,0xff010020,0x0007003c,0xff010010,0x0007003d,0xff010004,'
   '0x00070040,0x000c00b4,0x00070041,0x000c00cd,0x00070042,0x000c00b3,'
   '0x00070043,0x000c00e2,0x00070044,0x000c00ea,0x00070045,0x000c00e9'])
  self.assertIn(('FnFunctionUsageMap',OSOBJ),records)
 def test_invalid_config_version_publishes_no_mapping(self):
  u,strings,records=machine();u.mem_write(PAY+1,b'\x02');u.reg_write(UC_ARM64_REG_X0,OBJ);u.reg_write(UC_ARM64_REG_X1,BUF);u.reg_write(UC_ARM64_REG_X2,1)
  # Invalid-version diagnostic call is not necessary to execute for this test.
  u.hook_add(UC_HOOK_CODE,lambda u,p,s,d:u.emu_stop() if p==a(0xfffffe000971683c) else None)
  u.emu_start(a(0xfffffe00097164cc),STOP,count=10000);self.assertEqual(strings,[]);self.assertEqual(records,[])
 def test_keyboard_callback_preserves_arguments_and_sets_f1(self):
  sys.path.insert(0,str(ROOT/'research'))
  from test_apple_keyhole_host import machine as bridge_machine, qput, DATA, TARGET, STOP as BRIDGE_STOP
  u=bridge_machine(0x1002a6810,0x28)
  context,obj,table=DATA,DATA+0x100,DATA+0x200
  qput(u,context,obj);u.mem_write(context+8,b'\xf1');qput(u,obj,table);qput(u,table+0x70,TARGET)
  vals=[context,2,2,DATA+0x300,DATA+0x400]
  for i,v in enumerate(vals):u.reg_write(UC_ARM64_REG_X0+i,v)
  seen=[]
  def target(u,p,s,d):
   if p==TARGET:seen.append([u.reg_read(UC_ARM64_REG_X0+i) for i in range(6)]);u.emu_stop()
  u.hook_add(UC_HOOK_CODE,target);u.emu_start(0x1002a6810,BRIDGE_STOP,count=100)
  self.assertEqual(seen,[[obj,2,2,DATA+0x300,DATA+0x400,0xf1]])
if __name__=='__main__':unittest.main()
