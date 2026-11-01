"""Exact Apple-translated K2 raw interface. Transport/write gates inherited.

Selection reads registry properties only. Original manager Product/Transport
filter remains. Never select the battery keyhole interface for diagnostics.
"""
import ctypes as C
import radio_installer as r

RAW_DESCRIPTOR_SHA='72b22e181a2666679b2de4fabc93185f5149274fa1af75fd1842daed12bfe5da'

def matches_profile(properties,*,usage=0x12,descriptor_bytes=22,descriptor_sha=RAW_DESCRIPTOR_SHA):
    return all(properties.get(k)==v for k,v in {
        'VendorID':76,'VendorIDSource':1,'ProductID':615,
        'PrimaryUsagePage':0xff00,'PrimaryUsage':usage,
        'descriptor_bytes':descriptor_bytes,'descriptor_sha256':descriptor_sha}.items())

class AppleRawHID(r.NativeHID):
    USAGE=0x12
    DESCRIPTOR_BYTES=22
    DESCRIPTOR_SHA=RAW_DESCRIPTOR_SHA
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

class AppleManagementHID(AppleRawHID):
    """Read-only management queries use macOS's native FF/F0 translator."""
    USAGE=0x0b
    DESCRIPTOR_BYTES=83
    DESCRIPTOR_SHA='7e61a92d4e39af689084e6453fbbf2f4183ffa56eda8c4f0c954b96fa0f0752a'
    def __init__(self,plan,write=False,lock_owner_uid=None):
        if write:raise ValueError('Management interface is read-only in this experiment')
        super().__init__(plan,write=False,lock_owner_uid=lock_owner_uid)
