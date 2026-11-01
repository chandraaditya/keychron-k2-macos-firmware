"""File-only execution of bluetoothd DeviceID classifier; no host/device APIs.
The C++ map lookup is modeled from the daemon's literal initializer tables.
Only the keyboard-specific table entry is supplied; unrelated flags are omitted.
"""
import sys, struct, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_apple_keyhole_host import machine, read_address, DATA, qput
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import *

PRODUCT_MAP=dict(struct.iter_unpack('<II',read_address(0x10095b660,336)))
VENDOR_MAP=dict(struct.iter_unpack('<II',read_address(0x10095b638,32)))
PRODUCT_ENUMS=struct.unpack('<8I',read_address(0x10095b818,32))

class ClassifierTests(unittest.TestCase):
 def classify(self,source,vendor,product):
  u=machine(0x10052092c,0xb8)
  u.mem_map(0x1002a6000,4096)
  u.mem_map(0x100bd9000,4096)
  obj,entry,products,result=DATA,DATA+0x1000,DATA+0x2000,DATA+0x3000
  qput(u,0x100bd9d18,entry,entry+40)
  u.mem_write(entry,struct.pack('<IIQQQI',0,0,products,products+32,products+32,4))
  u.mem_write(products,struct.pack('<8I',*PRODUCT_ENUMS))
  for reg,val in [(UC_ARM64_REG_X19,obj),(UC_ARM64_REG_X21,0x100bd9cd0),(UC_ARM64_REG_X23,0x100bd9d00),(UC_ARM64_REG_X25,source),(UC_ARM64_REG_X26,vendor),(UC_ARM64_REG_X27,product)]:u.reg_write(reg,val)
  maps={0x100bd9cd0:{0:1,1:2},0x100bd9ce8:VENDOR_MAP,0x100bd9d00:PRODUCT_MAP}
  def hook(u,a,size,unused):
   if a==0x1002a6368:
    table=u.reg_read(UC_ARM64_REG_X0);key=struct.unpack('<I',u.mem_read(u.reg_read(UC_ARM64_REG_X1),4))[0]
    u.mem_write(result,struct.pack('<H',maps[table][key]));u.reg_write(UC_ARM64_REG_X0,result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
  u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x10052092c,0x1005209e4,count=1000)
  return struct.unpack('<Q',u.mem_read(obj+0x388,8))[0]
 def test_keyboard_device_id_sets_flag4(self):
  self.assertEqual(PRODUCT_MAP[12],0x267);self.assertEqual(VENDOR_MAP[0],0x4c)
  self.assertEqual(self.classify(1,0x4c,0x267),1<<4)
 def test_mismatched_device_id_does_not_set_flag4(self):
  for did in [(2,0x4c,0x267),(1,0x5ac,0x267),(1,0x4c,0x265),(2,0x5ac,0x24f)]:
   with self.subTest(did=did):self.assertEqual(self.classify(*did),0)
 def test_all_literal_keyboard_products_select_same_flag(self):
  for enum in PRODUCT_ENUMS:self.assertEqual(self.classify(1,0x4c,PRODUCT_MAP[enum]),16)

if __name__=='__main__':unittest.main()
