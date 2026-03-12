from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

import ctypes
from ctypes import wintypes
import struct
import re
import logging
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Windows API constants
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(wintypes.BYTE)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


class ModuleInfo:
    def __init__(self, name: str, base: int, size: int):
        self.name = name
        self.base = base
        self.size = size


class ProcessReader:
    """Handles reading memory from cs2.exe"""

    def __init__(self, process_name: str = "cs2.exe"):
        self.process_name = process_name
        self.handle = None
        self.process_id = None
        self.modules: Dict[str, ModuleInfo] = {}
        self.kernel32 = ctypes.windll.kernel32

    def open(self) -> bool:
        self.process_id = self._find_process(self.process_name)
        if not self.process_id:
            return False
        self.handle = self.kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
            False,
            self.process_id
        )
        return bool(self.handle)

    def close(self):
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def _find_process(self, name: str) -> Optional[int]:
        h_snapshot = self.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snapshot == -1:
            return None
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if self.kernel32.Process32First(h_snapshot, ctypes.byref(entry)):
                while True:
                    if entry.szExeFile.decode('utf-8', errors='ignore').lower() == name.lower():
                        return entry.th32ProcessID
                    if not self.kernel32.Process32Next(h_snapshot, ctypes.byref(entry)):
                        break
        finally:
            self.kernel32.CloseHandle(h_snapshot)
        return None

    def enumerate_modules(self) -> Dict[str, ModuleInfo]:
        if not self.handle:
            return {}
        h_snapshot = self.kernel32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
            self.process_id
        )
        if h_snapshot == -1:
            return {}
        try:
            entry = MODULEENTRY32()
            entry.dwSize = ctypes.sizeof(MODULEENTRY32)
            if self.kernel32.Module32First(h_snapshot, ctypes.byref(entry)):
                while True:
                    name = entry.szModule.decode('utf-8', errors='ignore')
                    base = ctypes.addressof(entry.modBaseAddr.contents) if entry.modBaseAddr else 0
                    self.modules[name] = ModuleInfo(name=name, base=base, size=entry.modBaseSize)
                    if not self.kernel32.Module32Next(h_snapshot, ctypes.byref(entry)):
                        break
        finally:
            self.kernel32.CloseHandle(h_snapshot)
        return self.modules

    def read_memory(self, address: int, size: int) -> Optional[bytes]:
        if not self.handle:
            return None
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        result = self.kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read)
        )
        if result and bytes_read.value == size:
            return bytes(buffer.raw)
        return None

    def read_i32(self, address: int) -> Optional[int]:
        data = self.read_memory(address, 4)
        return struct.unpack('<i', data)[0] if data else None

    def read_u64(self, address: int) -> Optional[int]:
        data = self.read_memory(address, 8)
        return struct.unpack('<Q', data)[0] if data else None

    def read_ptr(self, address: int) -> Optional[int]:
        return self.read_u64(address)

    def read_string(self, address: int, max_length: int = 256) -> Optional[str]:
        data = self.read_memory(address, max_length)
        if not data:
            return None
        try:
            null_idx = data.index(0)
            return data[:null_idx].decode('utf-8', errors='ignore')
        except ValueError:
            return data.decode('utf-8', errors='ignore')


class SignatureScanner:
    """Signature scanning for CS2 offsets"""

    # Offset patterns from a2x/cs2-dumper
    OFFSET_PATTERNS = {
        'client.dll': {
            'dwCSGOInput': '488905${\'} 0f57c0 0f1105',
            'dwEntityList': '48890d${\'} e9${} cc',
            'dwGameEntitySystem': '488b1d${\'} 48891d[4] 4c63b3',
            'dwGameEntitySystem_highestEntityIndex': 'ff81u4 4885d2',
            'dwGameRules': '48891d${\'} ff15${} 84c0',
            'dwGlobalVars': '488915${\'} 488942',
            'dwGlowManager': '488b05${\'} c3 cccccccccccccccc 8b41',
            'dwLocalPlayerController': '488b05${\'} 4189be',
            'dwPlantedC4': '488b15${\'} 41ffc0 488d4c24? 448905[4]',
            'dwPrediction': '488d05${\'} c3 cccccccccccccccc 405356 4154',
            'dwSensitivity': '488d0d${[8]\'} 660f6ecd',
            'dwSensitivity_sensitivity': '488d7eu1 480fbae0? 72? 85d2 490f4fff',
            'dwViewMatrix': '488d0d${\'} 48c1e006',
            'dwViewRender': '488905${\'} 488bc8 4885c0',
            'dwWeaponC4': '488b15${\'} 488b5c24? ffc0 8905${} 488bc6 488934ea 80be',
        },
        'engine2.dll': {
            'dwBuildNumber': '8905${\'} 488d0d${} ff15${} 488b0d',
            'dwNetworkGameClient': '48893d${\'} ff87',
            'dwNetworkGameClient_clientTickCount': '8b81u4 c3 cccccccccccccccccc 8b81${} c3 cccccccccccccccc 83b9',
            'dwNetworkGameClient_deltaTick': '4c8db7u4 4c897c24',
            'dwNetworkGameClient_isBackgroundMap': '0fb681u4 c3 cccccccccccccccc 0fb681${} c3 cccccccccccccccc 4053',
            'dwNetworkGameClient_localPlayer': '428b94d3u4 5b 49ffe3 32c0 5b c3 cccccccccccccccc 4053',
            'dwNetworkGameClient_maxClients': '8b81u4 c3????????? 8b81[4] c3????????? 8b81',
            'dwNetworkGameClient_serverTickCount': '8b81u4 c3 cccccccccccccccccc 83b9',
            'dwNetworkGameClient_signOnState': '448b81u4 488d0d',
            'dwWindowHeight': '8b05${\'} 8903',
            'dwWindowWidth': '8b05${\'} 8907',
        },
        'inputsystem.dll': {
            'dwInputSystem': '488905${\'} 33c0',
        },
        'matchmaking.dll': {
            'dwGameTypes': '488d0d${\'} ff90',
        },
    }

    @staticmethod
    def parse_pattern(pattern: str) -> List[Optional[int]]:
        """Parse pattern string into bytes list (None = wildcard)"""
        pattern = pattern.replace(' ', '')
        pattern = re.sub(r'\$\{[^\}]*\}', '????', pattern)
        pattern = re.sub(r'\[[0-9]+\]', lambda m: '?' * int(m.group()[1:-1]), pattern)
        pattern = re.sub(r'u[0-9]+', lambda m: '?' * int(m.group()[1:]), pattern)

        bytes_list = []
        i = 0
        while i < len(pattern):
            if pattern[i] == '?':
                bytes_list.append(None)
                i += 1
            elif i + 1 < len(pattern) and all(c in '0123456789ABCDEFabcdef' for c in pattern[i:i+2]):
                bytes_list.append(int(pattern[i:i+2], 16))
                i += 2
            else:
                i += 1
        return bytes_list

    @staticmethod
    def find_pattern(data: bytes, pattern_bytes: List[Optional[int]]) -> List[int]:
        """Find pattern in data, return list of offsets"""
        results = []
        pattern_len = len(pattern_bytes)
        if pattern_len == 0 or pattern_len > len(data):
            return results

        exact_positions = [(i, b) for i, b in enumerate(pattern_bytes) if b is not None]
        if not exact_positions:
            return results

        last_exact_pos, last_exact_byte = exact_positions[-1]
        pos = 0

        while pos <= len(data) - pattern_len:
            try:
                found = data.index(bytes([last_exact_byte]), pos + last_exact_pos, len(data) - pattern_len + 1)
            except ValueError:
                break
            pos = found - last_exact_pos

            match = True
            for i, pb in enumerate(pattern_bytes):
                if pb is not None and data[pos + i] != pb:
                    match = False
                    break
            if match:
                results.append(pos)
                return results[:1]  # Return first match only
            pos += 1
        return results

    @staticmethod
    def extract_rip_offset(data: bytes, match_offset: int, base: int) -> Optional[int]:
        """Extract RIP-relative offset from instruction at match"""
        pos = match_offset
        if pos + 7 >= len(data):
            return None

        # 3-byte opcodes with REX prefix
        opcodes_3byte = [
            b'\x48\x89\x05', b'\x48\x8B\x05', b'\x48\x8D\x05',
            b'\x48\x8B\x1D', b'\x48\x89\x1D', b'\x48\x89\x15',
            b'\x48\x8D\x0D', b'\x48\x8B\x15', b'\x48\x8B\x0D',
            b'\x48\x89\x0D', b'\x48\x89\x3D', b'\x48\x8B\x3D',
        ]

        for opcode in opcodes_3byte:
            if data[pos:pos+3] == opcode:
                rel_offset = struct.unpack('<i', data[pos+3:pos+7])[0]
                target = base + pos + 7 + rel_offset
                return target - base

        # 2-byte opcodes (no REX)
        opcodes_2byte = [
            b'\x89\x05', b'\x8B\x05', b'\x8D\x05',
            b'\x8D\x15', b'\x8B\x15', b'\x8B\x1D',
            b'\x89\x15', b'\x89\x0D', b'\x8D\x0D',
        ]

        for opcode in opcodes_2byte:
            if data[pos:pos+2] == opcode:
                rel_offset = struct.unpack('<i', data[pos+2:pos+6])[0]
                target = base + pos + 6 + rel_offset
                return target - base

        # Single byte offset patterns
        if data[pos:pos+3] == b'\x48\x8D\x7E':
            return data[pos+3]
        if len(data) > pos + 4 and data[pos:pos+2] == b'\xff\x81':
            return struct.unpack('<I', data[pos+2:pos+6])[0]
        if len(data) > pos + 4 and data[pos:pos+3] == b'\x4c\x8d\xb7':
            return struct.unpack('<I', data[pos+3:pos+7])[0]
        if len(data) > pos + 4 and data[pos:pos+3] == b'\x0f\xb6\x81':
            return struct.unpack('<I', data[pos+3:pos+7])[0]
        if len(data) > pos + 4 and data[pos:pos+3] == b'\x42\x8b\x94':
            return struct.unpack('<I', data[pos+4:pos+8])[0]
        if len(data) > pos + 4 and data[pos:pos+2] == b'\x8b\x81':
            return struct.unpack('<I', data[pos+2:pos+6])[0]
        if len(data) > pos + 4 and data[pos:pos+3] == b'\x44\x8b\x81':
            return struct.unpack('<I', data[pos+3:pos+7])[0]

        return None


class SchemaScanner:
    """Scans for schema/class field offsets"""

    def __init__(self, process: ProcessReader):
        self.process = process

    def scan_schemas(self) -> Dict[str, Dict[str, int]]:
        """Scan schemasystem.dll for class field offsets"""
        if 'schemasystem.dll' not in self.process.modules:
            return {}

        module = self.process.modules['schemasystem.dll']
        module_data = self.process.read_memory(module.base, min(module.size, 20 * 1024 * 1024))
        if not module_data:
            return {}

        # Find SchemaSystem pointer
        pattern = b'\x4c\x8d\x35'
        schema_system_addr = None

        for match in re.finditer(pattern, module_data):
            offset = match.start()
            if offset + 10 >= len(module_data):
                continue
            if module_data[offset + 7:offset + 10] == b'\x0f\x28\x45':
                rel_offset = struct.unpack('<i', module_data[offset + 3:offset + 7])[0]
                schema_system_addr = module.base + offset + 7 + rel_offset
                break

        if not schema_system_addr:
            return {}

        return self._read_all_classes(schema_system_addr)

    def _read_all_classes(self, schema_system_addr: int) -> Dict[str, Dict[str, int]]:
        """Read all class fields from schema system"""
        classes = {}

        type_scopes_ptr = self.process.read_ptr(schema_system_addr + 0x190 + 8)
        type_scopes_count = self.process.read_i32(schema_system_addr + 0x190)

        if not type_scopes_ptr or not type_scopes_count:
            return classes

        for i in range(min(type_scopes_count, 100)):
            scope_ptr = self.process.read_ptr(type_scopes_ptr + (i * 8))
            if not scope_ptr:
                continue

            scope_classes = self._read_type_scope(scope_ptr)
            classes.update(scope_classes)

        return classes

    def _read_type_scope(self, scope_ptr: int) -> Dict[str, Dict[str, int]]:
        """Read classes from a type scope"""
        classes = {}

        # UtlTsHash structure at offset 0x560:
        # - entry_mem: UtlMemoryPool (0x60 bytes)
        # - buckets[256]: array of bucket pointers (0x1800 bytes = 256 * 24)
        hash_base = scope_ptr + 0x560
        buckets_base = hash_base + 0x60

        visited = set()

        # Iterate through all 256 buckets
        for bucket_idx in range(256):
            # Each bucket entry is 24 bytes (3 pointers): pad, first, pad
            bucket_addr = buckets_base + (bucket_idx * 24)
            bucket_first = self.process.read_ptr(bucket_addr + 8)  # first pointer at +8

            if not bucket_first:
                continue

            current = bucket_first
            iterations = 0

            while current and iterations < 5000:
                if current in visited:
                    break
                visited.add(current)

                data_ptr = self.process.read_ptr(current + 16)
                next_ptr = self.process.read_ptr(current + 8)

                if data_ptr:
                    class_info = self._read_class_info(data_ptr)
                    if class_info:
                        name, fields = class_info
                        classes[name] = fields

                current = next_ptr
                iterations += 1

        return classes

    def _read_class_info(self, class_ptr: int) -> Optional[Tuple[str, Dict[str, int]]]:
        """Read class name and fields"""
        name_ptr = self.process.read_ptr(class_ptr + 8)
        field_count_data = self.process.read_memory(class_ptr + 28, 2)
        field_count = struct.unpack('<H', field_count_data)[0] if field_count_data else 0
        fields_ptr = self.process.read_ptr(class_ptr + 40)

        if not name_ptr:
            return None

        name = self.process.read_string(name_ptr, 128)
        if not name:
            return None

        fields = {}
        if fields_ptr and field_count > 0:
            for i in range(min(field_count, 200)):
                field_addr = fields_ptr + (i * 32)
                field_name_ptr = self.process.read_ptr(field_addr)
                offset_data = self.process.read_memory(field_addr + 16, 4)
                offset = struct.unpack('<i', offset_data)[0] if offset_data else 0

                if field_name_ptr:
                    field_name = self.process.read_string(field_name_ptr, 128)
                    if field_name:
                        # Handle special case for m_modelState -> m_pBoneArray
                        if field_name == 'm_modelState' and name == 'CSkeletonInstance':
                            fields['m_pBoneArray'] = offset + 128
                        else:
                            fields[field_name] = offset

        return (name, fields)


_offsets_cache: SimpleNamespace = None
_class_offsets_cache: SimpleNamespace = None


def get_offsets(force_update: bool = False) -> Tuple[SimpleNamespace, SimpleNamespace]:
    """Get offsets via signature scanning from cs2.exe memory"""
    global _offsets_cache, _class_offsets_cache

    if _offsets_cache and _class_offsets_cache and not force_update:
        return (_offsets_cache, _class_offsets_cache)

    process = ProcessReader("cs2.exe")
    if not process.open():
        raise RuntimeError("Failed to open cs2.exe - make sure the game is running")

    try:
        process.enumerate_modules()

        # Scan for offsets
        flat: Dict[str, int] = {}

        for module_name, patterns in SignatureScanner.OFFSET_PATTERNS.items():
            if module_name not in process.modules:
                continue

            module = process.modules[module_name]
            read_size = min(module.size, 100 * 1024 * 1024)
            module_data = process.read_memory(module.base, read_size)
            if not module_data:
                continue

            for offset_name, pattern in patterns.items():
                pattern_bytes = SignatureScanner.parse_pattern(pattern)
                matches = SignatureScanner.find_pattern(module_data, pattern_bytes)

                if matches:
                    rva = SignatureScanner.extract_rip_offset(module_data, matches[0], module.base)
                    if rva is not None:
                        flat[offset_name] = rva

        # Secondary pattern searches (like a2x/cs2-dumper)
        # These patterns extract u4 values that are added to parent RVA
        if 'client.dll' in process.modules:
            module = process.modules['client.dll']
            read_size = min(module.size, 100 * 1024 * 1024)
            client_data = process.read_memory(module.base, read_size)
            if client_data:
                # dwViewAngles: pattern "f2420f108428u4"
                # Result = dwCSGOInput_rva + extracted_u4_value
                if 'dwCSGOInput' in flat:
                    view_angles_pattern = SignatureScanner.parse_pattern('f2420f108428????')
                    va_matches = SignatureScanner.find_pattern(client_data, view_angles_pattern)
                    if va_matches:
                        pos = va_matches[0] + 6  # after f2 42 0f 10 84 28
                        if pos + 4 <= len(client_data):
                            offset_val = struct.unpack('<I', client_data[pos:pos+4])[0]
                            flat['dwViewAngles'] = flat['dwCSGOInput'] + offset_val

                # dwLocalPlayerPawn: pattern "4c39b6u4 74? 4488be"
                # Result = dwPrediction_rva + extracted_u4_value
                if 'dwPrediction' in flat:
                    pawn_pattern = SignatureScanner.parse_pattern('4c39b6???? 74? 4488be')
                    pawn_matches = SignatureScanner.find_pattern(client_data, pawn_pattern)
                    if pawn_matches:
                        pos = pawn_matches[0] + 3  # after 4c 39 b6
                        if pos + 4 <= len(client_data):
                            offset_val = struct.unpack('<I', client_data[pos:pos+4])[0]
                            flat['dwLocalPlayerPawn'] = flat['dwPrediction'] + offset_val

        # Ensure both dwLocalPlayerController and dwLocalPlayerPawn exist
        if 'dwLocalPlayerController' not in flat and 'dwLocalPlayerPawn' in flat:
            flat['dwLocalPlayerController'] = flat['dwLocalPlayerPawn']
        if 'dwLocalPlayerPawn' not in flat and 'dwLocalPlayerController' in flat:
            flat['dwLocalPlayerPawn'] = flat['dwLocalPlayerController']

        # Scan for schema/class offsets
        schema_scanner = SchemaScanner(process)
        classes = schema_scanner.scan_schemas()

        # Build class offsets namespace
        class_ns = {}
        for cls_name, fields in classes.items():
            class_ns[cls_name] = SimpleNamespace(**fields)
            # Also add fields to flat namespace for direct access
            for field_name, offset in fields.items():
                flat[field_name] = offset

        _offsets_cache = SimpleNamespace(**flat)
        _class_offsets_cache = SimpleNamespace(**class_ns)

        return (_offsets_cache, _class_offsets_cache)

    finally:
        process.close()
