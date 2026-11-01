"""Exact native182-byte K2 keyboard interface for read-only Feature2.

Selection reads registry properties only. The original Product/Transport filter
remains. Does not register input callbacks, seize the keyboard or permit writes.
"""
import ctypes as C
import radio_installer as r

RAW_DESCRIPTOR_SHA='5ad48fbaddbae4d5806c4dbc27c842e535e2954cd140e208494cf4f17fbc47c7'

def matches_profile(properties,*,usage=6,descriptor_bytes=182,descriptor_sha=RAW_DESCRIPTOR_SHA):
    return all(properties.get(k)==v for k,v in {
        'VendorID':76,'VendorIDSource':1,'ProductID':615,
        'PrimaryUsagePage':1,'PrimaryUsage':usage,
        'descriptor_bytes':descriptor_bytes,'descriptor_sha256':descriptor_sha}.items())

class AppleKeyboardHID(r.NativeHID):
    USAGE=6
    DESCRIPTOR_BYTES=182
    DESCRIPTOR_SHA=RAW_DESCRIPTOR_SHA
    def __init__(self,plan,write=False,lock_owner_uid=None):
        if write:raise ValueError('Keyboard configuration probe is read-only')
        super().__init__(plan,write=False,lock_owner_uid=lock_owner_uid)
    def _matches_diagnostic_device(self,device):
        get=self.hid.IOHIDDeviceGetProperty;get.argtypes=[C.c_void_p,C.c_void_p];get.restype=C.c_void_p
        gettype=self.cf.CFGetTypeID;gettype.argtypes=[C.c_void_p];gettype.restype=C.c_ulong
        numtype=self.cf.CFNumberGetTypeID;numtype.argtypes=[];numtype.restype=C.c_ulong
        datatype=self.cf.CFDataGetTypeID;datatype.argtypes=[];datatype.restype=C.c_ulong
        number=self.cf.CFNumberGetValue;number.argtypes=[C.c_void_p,C.c_int,C.c_void_p];number.restype=C.c_bool
        datalen=self.cf.CFDataGetLength;datalen.argtypes=[C.c_void_p];datalen.restype=C.c_long
        data=self.cf.CFDataGetBytePtr;data.argtypes=[C.c_void_p];data.restype=C.c_void_p
        props={}
        for name in ['VendorID','VendorIDSource','ProductID','PrimaryUsagePage','PrimaryUsage','ReportDescriptor']:
            key=self.string(None,name.encode(),0x08000100)
            if not key:return False
            try:value=get(device,key)
            finally:self.release(key)
            if not value:return False
            if name=='ReportDescriptor':
                if gettype(value)!=datatype() or datalen(value)!=self.DESCRIPTOR_BYTES:return False
                raw=C.string_at(data(value),self.DESCRIPTOR_BYTES)
                props['descriptor_bytes']=self.DESCRIPTOR_BYTES;props['descriptor_sha256']=r.digest(raw)
            else:
                if gettype(value)!=numtype():return False
                out=C.c_longlong()
                if not number(value,4,C.byref(out)):return False
                props[name]=out.value
        return matches_profile(props,usage=self.USAGE,descriptor_bytes=self.DESCRIPTOR_BYTES,descriptor_sha=self.DESCRIPTOR_SHA)

