"""A89 complete HIDP request -> ROM root -> copy/send -> L2CAP MTU path.
Only GKI pool allocation/free, activity notifications and final L2CAP queue are
modeled. No radio or device API. Does not simulate over-air scheduling.
"""
import os,unittest,struct
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from research.test_radio_keyboard_config_component import KeyboardConfigurationTests
from research.test_radio_apple_component import APP,TRANS,TABLE,put,word

class FullHIDPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):KeyboardConfigurationTests.setUpClass()
 def setUp(self):
  self.f=KeyboardConfigurationTests('test_direct_configuration_and_actual_Apple_keyhole_framing');self.f.setUp();u=self.f.u
  # Use the original real transport methods instead of the lower-level fixture's
  # fake allocation/send slots. Keep its relocatable connection object.
  u.mem_write(TABLE,bytes(u.mem_read(0x2089a0,0x200)))
  put(u,APP,0x208d04);put(u,TRANS+8,APP);put(u,TRANS+0x1c,0x20c24c)
  put(u,TABLE+0x68,0x70301)
  self.sent=[];self.handshakes=[];self.nextbuf=0x20e100;self.path=[]
  def hook(cpu,a,n,d):
   if a in [0x14482,0x1602e,0x161e,0xd3e,0x142a8,0x1050e,0x143ba,0x155e8,0x1559a,0x129e6,0xe172]:self.path.append(a)
   if a==0x70b6:
    q=self.nextbuf;self.nextbuf+=0x100;cpu.mem_write(q,bytes(256));cpu.reg_write(r.UC_ARM_REG_R0,q)
   elif a==0xd032:
    p=cpu.reg_read(r.UC_ARM_REG_R2);length,offset=struct.unpack('<HH',cpu.mem_read(p+2,4));self.sent.append(bytes(cpu.mem_read(p+8+offset,length)));cpu.reg_write(r.UC_ARM_REG_R0,1)
   elif a==0x14446:self.handshakes.append(cpu.reg_read(r.UC_ARM_REG_R2))
   elif a not in [0x70300,0x71fc]:return
   cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
 def packet(self,data):
  p=0x20df00;self.f.u.mem_write(p,struct.pack('<HHHH',0,len(data),0,0)+data)
  return self.f.call(0x14482,(TRANS,p,0,0))
 def test_direct_and_keyhole_feature2_full_send(self):
  logical=bytes.fromhex(os.environ.get('K2_FEATURE2','02 01 01 00 00 0a 0d 0b 0e 0c 0f'))
  self.packet(bytes.fromhex('43 02'))
  self.assertEqual(self.sent,[b'\xa3'+logical])
  self.sent.clear();self.packet(bytes.fromhex('53 ff 02'));self.assertEqual(self.handshakes, [0])
  self.packet(bytes.fromhex('4b f1 00 02'))
  self.assertEqual(self.sent,[b'\xa3\xf1'+logical])
  for a in [0x1602e,0x161e,0xd3e,0x142a8,0x1050e,0x1559a,0xe172]:self.assertIn(a,self.path)
 def test_management_battery_request_still_sends_after_keyboard_config(self):
  self.packet(bytes.fromhex('53 ff 02'));self.packet(bytes.fromhex('43 f1'))
  self.packet(bytes.fromhex('53 ff 90'));self.packet(bytes.fromhex('41 f0'))
  self.assertEqual(self.sent[-1],bytes.fromhex('a1 f0 90 00 3a'))
if __name__=='__main__':unittest.main()
