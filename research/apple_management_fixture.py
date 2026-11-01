"""Data-only Apple management fixtures. No device APIs, transport, or host actions.

DESCRIPTOR is the parent's saved 83-byte management descriptor. Feature34 is
not declared in that descriptor; its framing was independently read by parent.
Addresses here are explicit arguments, never discovered from the host.
"""
DESCRIPTOR = bytes.fromhex(
    '0600ff090ba1010600ff090b150026ff00750896040085e08122'
    '090b960100859a8122c00600ff0914a10185900584750195031500'
    '2501096105850944094681029505810175089501150026ff0009658102c0')


def byte(value, name):
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError(name + ' must be an integer byte')
    return value


def encode_battery(percent, status=0):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('percentage must be 0..100')
    byte(status, 'status')
    if status & 0xf8:
        raise ValueError('observed descriptor reserves upper five status bits')
    return bytes((0x90, status, percent))


def decode_battery(report):
    if not isinstance(report, bytes) or len(report) != 3 or report[0] != 0x90:
        raise ValueError('expected complete three-byte Input90 report')
    encode_battery(report[2], report[1])
    return {'percent': report[2], 'status': report[1]}


def encode_bluetooth_info(address, firmware_version=0, *, version=3, tail=bytes(67)):
    if not isinstance(address, bytes) or len(address) != 6:
        raise ValueError('address must be six bytes in displayed forward order')
    if type(firmware_version) is not int or not 0 <= firmware_version <= 65535:
        raise ValueError('firmware version must be a uint16')
    if type(version) is not int or version != 3:
        raise ValueError('reviewed host parser requires structure version3')
    if not isinstance(tail, bytes) or len(tail) != 67:
        raise ValueError('remaining structure must contain 67 bytes')
    return bytes((0x34, version)) + firmware_version.to_bytes(2, 'little') + address + tail


def decode_bluetooth_info(report):
    if not isinstance(report, bytes) or len(report) != 77 or report[:2] != b'\x34\x03':
        raise ValueError('expected complete 77-byte Feature34/version3 report')
    return {'address': report[4:10], 'firmware_version': int.from_bytes(report[2:4], 'little'),
            'version': report[1], 'tail': report[10:]}
