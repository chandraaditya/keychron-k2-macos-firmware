"""Exact installed dynamic-section build, no device or flashing operations.

Writes private experimental artifacts only. No static section, pairing section,
update transactions, guessed EEPROM capacity, or ready-to-use OTA file.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from elftools.elf.elffile import ELFFile
from build_candidate import bl

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'private/bt-eeprom-active-prefix.bin'
CAPTURE_MANIFEST = ROOT / 'private/bt-eeprom-active-manifest.json'
OUT = ROOT / 'private/candidates/radio-battery-initial'
DS_START, EXTENSION = 0x3c0, 0x209014
EXPECTED_DS_SHA = '50f2e98ac2aef18e7f41425fcd1c1d4639ab834c5f1872f58f28f0fef15b36b9'
EXPECTED_ROM_SHA = '07532fa29dccc635926f3e97a8333d08b9ecb0130221078699a3e98cce5bc1bf'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def records(data):
    offset = 0
    result = []
    while offset+3 <= len(data):
        kind, size = data[offset], int.from_bytes(data[offset+1:offset+3], 'little')
        end = offset+3+size
        if end > len(data):
            raise ValueError('Truncated configuration record')
        result.append((kind, bytes(data[offset+3:end])))
        offset = end
        if kind == 0xfe:
            if size or offset != len(data):
                raise ValueError('Invalid terminator or trailing data')
            return result
    raise ValueError('Missing configuration terminator')


def encode(items):
    return b''.join(bytes([kind])+len(payload).to_bytes(2, 'little')+payload for kind, payload in items)


def assemble(path):
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / 'component.o'
        subprocess.run(['xcrun', 'clang', '--target=armv7m-none-eabi', '-mcpu=cortex-m3',
                        '-mthumb', '-c', str(path), '-o', str(obj)], check=True)
        with obj.open('rb') as stream:
            elf = ELFFile(stream)
            if any(s.num_relocations() for s in elf.iter_sections() if hasattr(s, 'num_relocations')):
                raise ValueError('Unexpected unresolved relocation')
            symbols = {s.name: s['st_value'] & ~1 for s in elf.get_section_by_name('.symtab').iter_symbols()
                       if s.name and not s.name.startswith('$')}
            return bytearray(elf.get_section_by_name('.text').data()), symbols


def build(*, boot_path=None, out=OUT, version=0x85, builddate='20261027', phase_expected=0):
    if not 0 <= version <= 255 or len(builddate) != 8 or not builddate.isdigit():
        raise ValueError('Invalid experimental identity')
    if phase_expected not in (0, 1):
        raise ValueError('Unsupported documented boot phase')
    out = Path(out)
    capture = CAPTURE.read_bytes()
    expected = json.loads(CAPTURE_MANIFEST.read_text())
    if sha(capture) != expected['sha256'] or len(capture) != 0x39f3 or expected['dynamic_offset'] != DS_START:
        raise ValueError('Installed capture/provenance mismatch')
    if sha(capture[DS_START:]) != EXPECTED_DS_SHA:
        raise ValueError('Installed dynamic firmware differs from the reviewed exact build')
    if sha((ROOT/'private/bt-rom-000000-050000.bin').read_bytes()) != EXPECTED_ROM_SHA:
        raise ValueError('Captured ROM differs from the reviewed exact build')
    original = records(capture[DS_START:])
    if original[-2:] != [(0xb, struct.pack('<I', 0x2067ed)), (0xfe, b'')]:
        raise ValueError('Unexpected final startup record')
    ram = bytearray(0x10000)
    loaded = set()
    for kind, payload in original:
        if kind == 0xa:
            address = int.from_bytes(payload[:4], 'little')
            value = payload[4:]
            if not 0x200000 <= address <= 0x210000-len(value):
                raise ValueError('Unexpected initialization range')
            ram[address-0x200000:address-0x200000+len(value)] = value
            loaded.update(range(address, address+len(value)))
    old_call = bl(0x206aa8, 0x208380)
    if ram[0x6aa8:0x6aac] != old_call or ram[0x6830:0x6834] != struct.pack('<I', EXTENSION):
        raise ValueError('Installed constructor/heap boundary mismatch')
    if ram[0x8f02:0x8f10] != bytes.fromhex('b125050ac0023230313931303235'):
        raise ValueError('Unexpected installed firmware identity')
    boot_path = Path(boot_path) if boot_path is not None else Path(__file__).with_name('radio_boot_hook.S')
    component_path = Path(__file__).with_name('radio_battery_component.S')
    boot, bs = assemble(boot_path)
    component, cs = assemble(component_path)
    component_base = EXTENSION+len(boot)
    for slot, target in [('address_getter','get_report'), ('address_notify','notify'), ('address_connect','connected')]:
        struct.pack_into('<I', component, cs[slot], (component_base+cs[target]) | 1)
    end = component_base+len(component)
    if end % 4 or end+68 >= 0x20ef00 or any(a in loaded for a in range(EXTENSION,end)):
        raise ValueError('Extension overlaps loaded application or exceeds reserve bound')
    replacement = bl(0x206aa8, EXTENSION+bs['constructor_wrapper'])
    for slot, value in [('original_call_word',int.from_bytes(old_call,'little')),
                        ('replacement_call_word',int.from_bytes(replacement,'little')),
                        ('reserved_end',end), ('component_entry',component_base+cs['battery_install'] | 1)]:
        struct.pack_into('<I', boot, bs[slot], value)
    items = list(original)
    # Mark custom application identity so old guarded readers refuse this layout.
    for index, (kind, payload) in enumerate(items):
        if kind == 0xa and int.from_bytes(payload[:4], 'little') == 0x208e80:
            payload = bytearray(payload)
            payload[4+0x84] = version  # Report record at208f02, version byte+2.
            payload[4+0x88:4+0x90] = builddate.encode('ascii')
            items[index] = (kind, bytes(payload))
    extension = bytes(boot+component)
    items[-2:] = [(0xa, struct.pack('<I',EXTENSION)+extension),
                  (0xb, struct.pack('<I',EXTENSION | 1)), (0xfe,b'')]
    dynamic = encode(items)
    if records(dynamic) != items:
        raise ValueError('Configuration serialization mismatch')
    # All original records except identity and final startup must be byte-exact.
    for old, new in zip(original[:-2],items[:-3]):
        if old != new and not (old[0] == 0xa and int.from_bytes(old[1][:4], 'little') == 0x208e80):
            raise ValueError('Unintended original record change')
    manifest = {
        'status':'experimental-dynamic-section-not-cleared-for-flashing',
        'captured_device_build':'20191025', 'candidate_version_byte':version, 'candidate_build':builddate,
        'original_dynamic_sha256':sha(capture[DS_START:]), 'candidate_dynamic_sha256':sha(dynamic),
        'original_dynamic_bytes':len(capture)-DS_START, 'candidate_dynamic_bytes':len(dynamic),
        'extension_start':EXTENSION, 'extension_bytes':len(extension), 'new_heap_stack_start':end,
        'boot_symbols':{k:EXTENSION+v for k,v in bs.items() if k in ['boot_entry','constructor_wrapper','code_end']},
        'component_base':component_base, 'component_symbols':{k:component_base+v for k,v in cs.items()
            if k in ['battery_install','get_report','notify','connected','code_end']},
        'boot_source_sha256':sha(boot_path.read_bytes()),'component_source_sha256':sha(component_path.read_bytes()),
        'constructor_hook':0x206aa8, 'original_hook_bytes':old_call.hex(), 'runtime_hook_bytes':replacement.hex(),
        'full_reset_boot_required':True, 'hot_loading_supported':False, 'phase_guard':{'address':0x201344,'expected':phase_expected},
        'original_loaded_code_and_data_preserved_except_identity':True,
        'static_section_or_pairing_records_included':False,'eeprom_capacity_supported_by_photo_and_capture':True,
        'completed_byte_write_staging_model_verified':True,'native_macos_ui_verified':False,
        'device_access':False,'flashed':False,
        'limits':['Payload is a DS record stream, not a fullEEPROM image or ready-to-use OTA HEX.',
                  'Requires full reset boot; watchdog reset follows normal startup in captured code; no hot loading.',
                  'EEPROM physical writes and independent in-circuit recovery remain untested; no automatic crash rollback.',
                  'Emulation mocks allocator/transport/hardware status; no complete chip or radio simulator.']}
    out.mkdir(parents=True,exist_ok=True);out.chmod(0o700)
    listing=[];decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS)
    for code,symbols,base in [(boot,bs,EXTENSION),(component,cs,component_base)]:
        listing.extend(f'{i.address:08x} {i.bytes.hex():10} {i.mnemonic:8} {i.op_str}'
                       for i in decoder.disasm(code[:symbols['code_end']],base))
    for name,data in [('dynamic-section.bin',dynamic),('extension.bin',extension),
                      ('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode()),
                      ('disassembly.txt',('\n'.join(listing)+'\n').encode())]:
        p=out/name;p.write_bytes(data);p.chmod(0o600)
    print(json.dumps({k:manifest[k]for k in ['status','candidate_dynamic_bytes','extension_bytes','new_heap_stack_start']}))
    return manifest


if __name__=='__main__':
    build()
