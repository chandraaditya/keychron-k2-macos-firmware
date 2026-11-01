"""A93: macOS SET_CONNECTION_INTERVAL_CONTROL (feature C6) through the full HIDP
path gets a success handshake, and the F1 keyboard configuration still follows.
Run with K2_COMPONENT=firmware/radio_keyboard_c6_component.S (and A91's
K2_FEATURE2). With A92's component the C6 handshake is non-zero (the rejection
macOS retries for ~9 s).
"""
import os,unittest
from research.test_radio_keyboard_full_hidp import FullHIDPTests

class ConnectionIntervalTests(FullHIDPTests):
 def test_C6_then_keyboard_configuration(self):
  logical=bytes.fromhex(os.environ.get('K2_FEATURE2','02 01 01 00 00 0a 0d 0b 0e 0c 0f'))
  expect=int(os.environ.get('K2_C6_HANDSHAKE','0'))
  self.packet(bytes.fromhex('53 c6 01 18 01 20'))
  self.assertEqual(self.handshakes,[expect]);self.assertEqual(self.sent,[])
  self.packet(bytes.fromhex('53 c6 01 18 01 20'))
  self.assertEqual(self.handshakes,[expect,expect])
  self.packet(bytes.fromhex('53 ff 02'));self.assertEqual(self.handshakes[-1],0)
  self.packet(bytes.fromhex('4b f1 00 02'))
  self.assertEqual(self.sent,[b'\xa3\xf1'+logical])
 def test_other_feature_sets_still_reach_original_setter(self):
  self.packet(bytes.fromhex('53 c5 01'))
  self.assertNotEqual(self.handshakes,[0])

if __name__=='__main__':unittest.main()
