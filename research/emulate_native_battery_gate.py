"""Execute installed bluetoothd's battery-fallback gate OFFLINE.

Mocks only feature/config/log APIs and ARM64e authentication. No daemon attach,
process-memory access, preferences, device calls or executable modification.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X3,UC_ARM64_REG_X30,UC_ARM64_REG_PC,UC_ARM64_REG_SP
from apple_macho import MachO

ROOT=Path(__file__).resolve().parents[1]
EXPECTED='65dbb5f681ea7dc4e429d13a9d2a4dfd18d61afce49d7cf50717565bf241f429'
START,END=0x100520f50,0x1005210e8
DEVICE,CONFIG,VTABLE,STACK,RETURN=0x300000000,0x300001000,0x300002000,0x400000000,0x500000000


def run_gate(m,flags,feature=False,preference=False):
    cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    cpu.mem_map(0x100520000,0x2000);cpu.mem_write(START,m.read(START,END-START))
    cpu.mem_map(0x300000000,0x4000);cpu.mem_map(STACK,0x10000)
    cpu.mem_map(0x100bd9000,0x1000)
    cpu.mem_map(0x1009fc000,0x1000);cpu.mem_write(0x1009fc000,m.read(0x1009fc000,0x1000))
    cpu.mem_write(DEVICE+0x388,struct.pack('<Q',flags))
    cpu.mem_write(CONFIG,struct.pack('<Q',VTABLE));cpu.mem_write(VTABLE+0x48,struct.pack('<Q',RETURN))
    cpu.mem_write(0x100bd9f10,struct.pack('<Q',CONFIG))
    cpu.reg_write(UC_ARM64_REG_X0,DEVICE);cpu.reg_write(UC_ARM64_REG_X30,RETURN);cpu.reg_write(UC_ARM64_REG_SP,STACK+0x8000)
    trace=[]
    # Hook call SITES so unmapped imports never fetch, and leave every actual
    # flags/branch/return-value instruction executing from the captured code.
    def code(cpu,address,size,_):
        if address in (START,0x100520fe0):cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address==0x100520f78:
            cpu.reg_write(UC_ARM64_REG_X0,int(feature));cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address==0x100520f8c:
            cpu.reg_write(UC_ARM64_REG_X0,CONFIG);cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address in (0x100520f9c,0x100520fb4):
            pointer=cpu.reg_read(UC_ARM64_REG_X0);cpu.mem_write(pointer,bytes(24));cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address==0x100520ffc:
            cpu.mem_write(cpu.reg_read(UC_ARM64_REG_X3),bytes([int(preference)]));cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address==0x100521074:
            cpu.reg_write(UC_ARM64_REG_X0,0);cpu.reg_write(UC_ARM64_REG_PC,address+4)
        elif address==0x100521050:trace.append(cpu.reg_read(UC_ARM64_REG_X0));cpu.emu_stop()
    cpu.hook_add(UC_HOOK_CODE,code)
    cpu.emu_start(START,0,count=1000)
    if len(trace)!=1:raise ValueError('Gate did not reach its normal return')
    return bool(trace[0])


def main():
    m=MachO('/usr/sbin/bluetoothd')
    if hashlib.sha256(m.raw).hexdigest()!=EXPECTED:raise ValueError('Reviewed daemon binary changed')
    accepted=[bit for bit in range(64)if run_gate(m,1<<bit)]
    assert accepted==[11,13,14,15,17]
    for flags in (0,1,(1<<64)-1,0x26800,0x8000):
        for feature in (False,True):
            for preference in(False,True):
                assert run_gate(m,flags,feature,preference)==bool(feature or preference or flags&0x2e800)
    report={'binary_sha256':EXPECTED,'gate':hex(START),'default_accepted_flag_bits':accepted,
            'accepted_flag_mask':'0x2e800','formula':'feature_override OR HID_EnableGamepads OR (device_flags & 0x2e800)!=0',
            'cases':84,'actual_flag_tests_and_branches_executed':True,
            'mocked':['feature lookup','configuration lookup','log probe','string storage','ARM64e authentication'],
            'live_K2_internal_flags_known':False,'settings_or_process_or_device_changed':False}
    (ROOT/'private/apple/native-gate-emulation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
