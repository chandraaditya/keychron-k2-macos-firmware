"""Actual ROM scatter/DS/async-I2C execution with a modeled EEPROM controller.

No device access. Bus completion/NACK/pending states are modeled. The fallback
EEPROM reader is modeled readable, including after a controller timeout: this
does NOT demonstrate physical recovery from a stuck bus or failed EEPROM.
"""
from pathlib import Path
import sys
import unittest
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'firmware'))
from build_radio_one_boot_trial import guarded

def put(u,a,v):u.mem_write(a,v.to_bytes(4,'little'))
def word(u,a):return int.from_bytes(u.mem_read(a,4),'little')

class OneBootGuardTests(unittest.TestCase):
    def run_case(self,mode='ok',*,apple=True,budget=32):
        u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        for a,n in [(0,0x80000),(0x200000,0x10000),(0x300000,0x100000),(0x600000,0x10000)]:u.mem_map(a,n)
        u.mem_write(0,(ROOT/'private/bt-rom-000000-050000.bin').read_bytes())
        u.mem_write(0x200000,(ROOT/'private/ram-200000.bin').read_bytes())
        u.mem_write(0x201344,b'\0');u.reg_write(r.UC_ARM_REG_SP,0x200400)
        u.emu_start(0x2f1,0x454,count=1000000)
        self.assertEqual(word(u,0x201344),0x301)
        # Normal pre-DS startup initializes this controller before callbacks.
        u.reg_write(r.UC_ARM_REG_LR,0x70001)
        u.emu_start(0x2c6b7,0x70000,count=100000)
        self.assertEqual(u.reg_read(r.UC_ARM_REG_PC),0x70000)
        # 2C6B6 seeds10, then its2C6B0→2C67A helper clears maskB0.
        self.assertEqual(bytes(u.mem_read(0x201021,1)),b'\x00')
        u.mem_write(0x205e10,b'\x10');put(u,0x205e1c,0x4000);put(u,0x200c80,0)
        fallback=(ROOT/'private/candidates/radio-battery-phase1/dynamic-section.bin').read_bytes()
        source=(ROOT/'private/candidates/radio-apple-profile/dynamic-section.bin').read_bytes() if apple else fallback
        trial,meta=guarded(source,budget=budget)
        eeprom=bytearray(65536);eeprom[0]=1
        eeprom[0x4000:0x4000+len(trial)]=trial;eeprom[0x8000:0x8000+len(fallback)]=fallback
        transactions=[];polls=[];recent=[];guard_watchdogs=[]
        def mmio(cpu,access,address,size,value,data):
            if address!=0x36054c or value!=1:return
            length=word(cpu,0x360544);control=word(cpu,0x360548)
            self.assertEqual(control&~3,0)
            control&=3
            fifo=bytes(cpu.mem_read(0x360504+4*i,1)[0] for i in range(3))
            self.assertEqual(word(cpu,0x360500),0xa0)
            if length==3 and control==0:
                event='write';self.assertEqual(fifo,b'\0\0\0')
                if mode not in ('write_error','write_timeout'):eeprom[0]=0
            elif length==2 and control==0:
                event='ack';self.assertEqual(fifo[:2],b'\0\0')
            elif length==34 and control==3:
                event='read';self.assertEqual(fifo[:2],b'\0\0')
                put(cpu,0x360550,255 if mode=='wrong_readback' else eeprom[0])
            else:self.fail(f'Unexpected I2C transaction {length}/{control}')
            transactions.append(event)
            status=6 if ((mode=='write_error' and event=='write') or
                         (mode=='read_error' and event=='read') or
                         (mode=='ack_forever' and event=='ack') or
                         (mode=='ack_once' and event=='ack' and transactions.count('ack')==1)) else 2
            if mode==event+'_timeout':status=0
            put(cpu,0x36054c,status)
        def hook(cpu,address,size,data):
            recent.append((hex(address),hex(cpu.reg_read(r.UC_ARM_REG_SP)),hex(cpu.reg_read(r.UC_ARM_REG_LR))))
            if len(recent)>15:recent.pop(0)
            if address==0x2c7d8:
                mmio(cpu,None,0x36054c,4,1,None)
            elif address==0x1cb34:
                start=cpu.reg_read(r.UC_ARM_REG_R0);dst=cpu.reg_read(r.UC_ARM_REG_R1);n=cpu.reg_read(r.UC_ARM_REG_R2)
                self.assertLessEqual(start+n,len(eeprom));cpu.mem_write(dst,bytes(eeprom[start:start+n]))
                # Prefix and final extension intentionally reuse the same RAM.
                # Flush Unicorn's translated blocks after the modeled code
                # load; Cortex-M3 has no instruction cache to retain old code.
                if dst<=0x209014<dst+n or 0x209014<=dst<0x209300:
                    cpu.ctl_remove_cache(dst,dst+n)
                cpu.reg_write(r.UC_ARM_REG_R0,1)
                cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address in (0x40acc,0x2c428,0x40e86):
                if address==0x2c428 and 0x209014<=cpu.reg_read(r.UC_ARM_REG_LR)<0x209100:
                    guard_watchdogs.append(1)
                cpu.reg_write(r.UC_ARM_REG_R0,0);cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
            elif address==0x2c6fe:polls.append(1)
        u.hook_add(UC_HOOK_CODE,hook)
        u.reg_write(r.UC_ARM_REG_SP,0x2003f8);u.reg_write(r.UC_ARM_REG_LR,0x70001)
        u.reg_write(r.UC_ARM_REG_R0,0x4000)
        try:u.emu_start(0x1d15d,0x70000,count=2000000)
        except Exception as error:
            raise RuntimeError(f'PC={u.reg_read(r.UC_ARM_REG_PC):x}, SP={u.reg_read(r.UC_ARM_REG_SP):x}, transactions={transactions}, recent={recent}') from error
        self.assertEqual(u.reg_read(r.UC_ARM_REG_PC),0x70000)
        self.assertEqual(u.reg_read(r.UC_ARM_REG_SP),0x2003f8)
        self.assertLessEqual(len(polls),budget)
        self.last_guard_watchdogs=len(guard_watchdogs)
        self.assertEqual(word(u,0x200c80),0)
        return u,eeprom,transactions

    def test_success_invalidates_header_before_applying_apple_profile(self):
        u,eeprom,events=self.run_case()
        self.assertEqual(events,['write','ack','read']);self.assertEqual(eeprom[0],0)
        self.assertEqual(bytes(u.mem_read(0x208f04,1)),b'\x87')
        self.assertEqual(word(u,0x202c70),1053)

    def test_one_busy_ack_is_retried_within_shared_bound(self):
        u,eeprom,events=self.run_case('ack_once')
        self.assertEqual(events,['write','ack','ack','read'])
        self.assertEqual(bytes(u.mem_read(0x208f04,1)),b'\x87')

    def test_failures_redirect_before_profile_and_restore_base(self):
        for mode in ['write_error','write_timeout','ack_timeout','ack_forever',
                     'read_error','read_timeout','wrong_readback']:
            with self.subTest(mode=mode):
                u,eeprom,events=self.run_case(mode)
                self.assertEqual(bytes(u.mem_read(0x208f04,1)),b'\x86')
                self.assertEqual(word(u,0x205e1c),0x8000)
                self.assertEqual(word(u,0x202c70),0)
                self.assertEqual(bytes(u.mem_read(0x209014,440)),
                                 (ROOT/'private/candidates/radio-battery-phase1/extension.bin').read_bytes())

    def test_preflight_uses_same_guard_without_apple_profile(self):
        u,eeprom,events=self.run_case(apple=False)
        self.assertEqual(eeprom[0],0)
        self.assertEqual(bytes(u.mem_read(0x208f04,1)),b'\x86')
        self.assertEqual(word(u,0x205e1c),0x4000)

    def test_long_error_path_services_watchdog_within_finite_budget(self):
        u,_,_=self.run_case('ack_forever',budget=2049)
        self.assertGreaterEqual(self.last_guard_watchdogs,2)
        self.assertEqual(bytes(u.mem_read(0x208f04,1)),b'\x86')

if __name__=='__main__':unittest.main()
