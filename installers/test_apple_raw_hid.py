"""Offline exact raw-interface selection and unchanged B2 selector checks."""
import unittest
import radio_installer as r
from apple_raw_hid import matches_profile,RAW_DESCRIPTOR_SHA

class Tests(unittest.TestCase):
    def profile(self):return {'VendorID':76,'VendorIDSource':1,'ProductID':615,
           'PrimaryUsagePage':0xff00,'PrimaryUsage':0x12,
           'descriptor_bytes':22,'descriptor_sha256':RAW_DESCRIPTOR_SHA}
    def test_only_exact_keyboard_raw_profile_matches(self):
        p=self.profile();self.assertTrue(matches_profile(p))
        for key,value in [('VendorID',1452),('VendorIDSource',2),('ProductID',613),
                          ('PrimaryUsage',0xb),('PrimaryUsagePage',1),
                          ('descriptor_bytes',83),('descriptor_sha256','bad')]:
            q=dict(p);q[key]=value;self.assertFalse(matches_profile(q))
    def test_original_selector_still_requires_B2_output_and_releases_elements(self):
        io=object.__new__(r.NativeHID);released=[]
        io.array_count=len;io.array_value=lambda xs,i:xs[i]
        io.element_id=lambda x:x[0];io.element_type=lambda x:x[1];io.release=released.append
        for elements,expected in [([(0xb2,129)],True),([(0xb2,2)],False),([(1,129)],False)]:
            io.elements=lambda *args:elements
            self.assertEqual(io._matches_diagnostic_device(None),expected)
            self.assertIs(released[-1],elements)
    def test_raw_class_inherits_disabled_mutation_gate(self):
        from apple_raw_hid import AppleRawHID
        self.assertFalse(r.ALLOW_HARDWARE_UPDATES)
        with self.assertRaises(ValueError):AppleRawHID(object(),write=True)
    def test_management_selector_is_separate_and_never_write_enabled(self):
        from apple_raw_hid import AppleManagementHID
        p=self.profile();p.update(PrimaryUsage=0xb,descriptor_bytes=83,descriptor_sha256=AppleManagementHID.DESCRIPTOR_SHA)
        self.assertFalse(matches_profile(p))
        self.assertTrue(matches_profile(p,usage=0xb,descriptor_bytes=83,descriptor_sha=AppleManagementHID.DESCRIPTOR_SHA))
        with self.assertRaises(ValueError):AppleManagementHID(object(),write=True)

if __name__=='__main__':unittest.main()
