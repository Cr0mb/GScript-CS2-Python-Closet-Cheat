from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
_CURRENT_DYNAMIC_FOV = 0.0

def set_current_dynamic_fov(value):
    global _CURRENT_DYNAMIC_FOV
    try:
        _CURRENT_DYNAMIC_FOV = float(value)
    except Exception:
        pass

def get_current_dynamic_fov(default=0.0):
    try:
        val = float(_CURRENT_DYNAMIC_FOV)
    except Exception:
        return default
    if val <= 0.0:
        return default
    return val
import ctypes, struct, time, threading, os, sys
from ctypes import wintypes, windll, byref
import win32api, win32con, win32gui, win32ui
from abc import ABC, abstractmethod

class IMemoryReader(ABC):

    @abstractmethod
    def read_bytes(self, address: int, size: int) -> bytes:
        ...

    @abstractmethod
    def write_bytes(self, address: int, data: bytes) -> bool:
        ...

    @abstractmethod
    def read_int(self, address: int) -> int:
        ...

    @abstractmethod
    def read_uint32(self, address: int) -> int:
        ...

    @abstractmethod
    def read_uint64(self, address: int) -> int:
        ...

    @abstractmethod
    def read_float(self, address: int) -> float:
        ...

    @abstractmethod
    def write_int(self, address: int, value: int) -> bool:
        ...

    @abstractmethod
    def write_uint32(self, address: int, value: int) -> bool:
        ...

    @abstractmethod
    def write_float(self, address: int, value: float) -> bool:
        ...

    def read_vec3(self, address: int) -> list:
        data = self.read_bytes(address, 12)
        return list(struct.unpack('fff', data)) if len(data) == 12 else [0.0, 0.0, 0.0]

    def read_string(self, address: int, max_length: int=256) -> str:
        data = self.read_bytes(address, max_length)
        if not data:
            return ''
        null = data.find(b'\x00')
        if null != -1:
            data = data[:null]
        return data.decode('utf-8', errors='ignore')

class UsermodeMemoryReader(IMemoryReader):

    def __init__(self, process_handle: int):
        self.process_handle = process_handle
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    def read_bytes(self, address: int, size: int) -> bytes:
        if not address or address > 140737488355327 or size <= 0:
            return b'\x00' * size
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = self.kernel32.ReadProcessMemory(self.process_handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read))
        return buf.raw if ok and read.value == size else b'\x00' * size

    def write_bytes(self, address: int, data: bytes) -> bool:
        buf = ctypes.create_string_buffer(data)
        written = ctypes.c_size_t(0)
        ok = self.kernel32.WriteProcessMemory(self.process_handle, ctypes.c_void_p(address), buf, len(data), ctypes.byref(written))
        return ok and written.value == len(data)

    def read_int(self, address: int) -> int:
        d = self.read_bytes(address, 4)
        return struct.unpack('i', d)[0] if d else 0

    def read_uint32(self, address: int) -> int:
        d = self.read_bytes(address, 4)
        return struct.unpack('I', d)[0] if d else 0

    def read_uint64(self, address: int) -> int:
        d = self.read_bytes(address, 8)
        return struct.unpack('Q', d)[0] if d else 0

    def read_float(self, address: int) -> float:
        d = self.read_bytes(address, 4)
        return struct.unpack('f', d)[0] if d else 0.0

    def write_int(self, address: int, value: int) -> bool:
        return self.write_bytes(address, struct.pack('i', value))

    def write_uint32(self, address: int, value: int) -> bool:
        return self.write_bytes(address, struct.pack('I', value))

    def write_float(self, address: int, value: float) -> bool:
        return self.write_bytes(address, struct.pack('f', value))

class MemoryInterface:

    def __init__(self, process_id: int, process_handle: int, config=None):
        self.process_id = process_id
        self.process_handle = process_handle
        self.config = config
        self.usermode_reader = None
        self._current_reader = None
        self._initialize_readers()

    def _initialize_readers(self):
        try:
            self.usermode_reader = UsermodeMemoryReader(self.process_handle)
        except Exception:
            pass
        self._current_reader = self.usermode_reader
        if not self._current_reader:
            raise Exception('Failed to initialize memory reader')

    def get_process_base_address(self) -> int:
        return 0

    def read_bytes(self, address: int, size: int) -> bytes:
        return self._current_reader.read_bytes(address, size)

    def write_bytes(self, address: int, data: bytes) -> bool:
        return self._current_reader.write_bytes(address, data)

    def read_int(self, address: int) -> int:
        return self._current_reader.read_int(address)

    def read_uint32(self, address: int) -> int:
        return self._current_reader.read_uint32(address)

    def read_uint64(self, address: int) -> int:
        return self._current_reader.read_uint64(address)

    def read_float(self, address: int) -> float:
        return self._current_reader.read_float(address)

    def read_vec3(self, address: int) -> list:
        return self._current_reader.read_vec3(address)

    def read_string(self, address: int, max_length: int=256) -> str:
        return self._current_reader.read_string(address, max_length)

    def write_int(self, address: int, value: int) -> bool:
        return self._current_reader.write_int(address, value)

    def write_uint32(self, address: int, value: int) -> bool:
        return self._current_reader.write_uint32(address, value)

    def write_float(self, address: int, value: float) -> bool:
        return self._current_reader.write_float(address, value)

def get_module_base(pid: int, name: str) -> int:
    TH32 = 8 | 16
    snap = windll.kernel32.CreateToolhelp32Snapshot(TH32, pid)
    if snap in (0, -1):
        return 0

    class ME(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD), ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)), ('modBaseSize', wintypes.DWORD), ('hModule', wintypes.HMODULE), ('szModule', ctypes.c_char * 256), ('szExePath', ctypes.c_char * 260)]
    me = ME()
    me.dwSize = ctypes.sizeof(ME)
    base = 0
    if windll.kernel32.Module32First(snap, byref(me)):
        while True:
            n = me.szModule.split(b'\x00', 1)[0].decode(errors='ignore').lower()
            if n == name.lower():
                base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value or 0
                break
            if not windll.kernel32.Module32Next(snap, byref(me)):
                break
    windll.kernel32.CloseHandle(snap)
    return base

class Vec3(ctypes.Structure):
    _fields_ = [('x', ctypes.c_float), ('y', ctypes.c_float), ('z', ctypes.c_float)]
_HANDLE_READERS = {}

def register_memory_reader(handle, reader) -> None:
    if not handle or reader is None:
        return
    try:
        _HANDLE_READERS[int(handle)] = reader
    except Exception:
        return

def unregister_memory_reader(handle) -> None:
    try:
        _HANDLE_READERS.pop(int(handle), None)
    except Exception:
        return

def _get_reader_for_handle(handle):
    try:
        return _HANDLE_READERS.get(int(handle))
    except Exception:
        return None

def read_bytes(handle, addr, size):
    if not addr or size <= 0:
        return b''
    reader = _get_reader_for_handle(handle)
    if reader is not None:
        try:
            data = reader.read_bytes(addr, size)
            if isinstance(data, (bytes, bytearray)) and len(data) >= size:
                return bytes(data[:size])
        except Exception:
            pass
    try:
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
        if read.value <= 0:
            return b''
        return buf.raw[:read.value]
    except Exception:
        return b''

def read_string(handle, addr, max_len=64):
    try:
        raw = read_bytes(handle, addr, max_len)
        if not raw:
            return ''
        return raw.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
    except Exception:
        return ''

def read_int(handle, addr):
    data = read_bytes(handle, addr, 4)
    return struct.unpack('i', data)[0] if data and len(data) >= 4 else 0

def read_u64(handle, addr):
    data = read_bytes(handle, addr, 8)
    return struct.unpack('Q', data)[0] if data and len(data) >= 8 else 0

def safe_read_uint64(handle, addr):
    if not addr or addr > 140737488355327:
        return 0
    try:
        return read_u64(handle, addr)
    except Exception:
        return 0

def read_vec3(handle, addr):
    data = read_bytes(handle, addr, 12)
    if not data or len(data) < 12:
        return Vec3(0.0, 0.0, 0.0)
    try:
        return Vec3.from_buffer_copy(data[:12])
    except Exception:
        return Vec3(0.0, 0.0, 0.0)

def read_matrix(handle, addr):
    data = read_bytes(handle, addr, 64)
    if not data or len(data) < 64:
        return (0.0,) * 16
    return struct.unpack('f' * 16, data[:64])

def w2s(m, p, w, h):
    x = m[0] * p.x + m[1] * p.y + m[2] * p.z + m[3]
    y = m[4] * p.x + m[5] * p.y + m[6] * p.z + m[7]
    z = m[12] * p.x + m[13] * p.y + m[14] * p.z + m[15]
    if z < 0.1:
        raise RuntimeError
    inv = 1 / z
    return {'x': w / 2 + x * inv * w / 2, 'y': h / 2 - y * inv * h / 2}

def wnd_proc(hwnd, msg, wp, lp):
    if msg == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
    return win32gui.DefWindowProc(hwnd, msg, wp, lp)

from Process.qt_overlay import QtOverlay as Overlay
TH32CS_SNAPPROCESS = 2
TH32CS_SNAPMODULE = 8
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)), ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_char * 260)]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD), ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)), ('modBaseSize', wintypes.DWORD), ('hModule', wintypes.HMODULE), ('szModule', ctypes.c_char * 256), ('szExePath', ctypes.c_char * 260)]
VIRTUAL_KEYS = {'mouse1': 1, 'mouse2': 2, 'mouse3': 4, 'mouse4': 5, 'mouse5': 6, 'shift': 16, 'left_shift': 160, 'right_shift': 161, 'ctrl': 17, 'left_ctrl': 162, 'right_ctrl': 163, 'alt': 18, 'left_alt': 164, 'right_alt': 165, 'tab': 9, 'enter': 13, 'space': 32, 'caps_lock': 20, 'left': 37, 'up': 38, 'right': 39, 'down': 40, 'f1': 112, 'f2': 113, 'f3': 114, 'f4': 115, 'f5': 116, 'f6': 117, 'f7': 118, 'f8': 119, 'f9': 120, 'f10': 121, 'f11': 122, 'f12': 123}
try:
    VIRTUAL_KEYS.update({'delete': 46, 'del': 46, 'page_down': 34, 'pagedown': 34, 'pgdn': 34, 'page_up': 33, 'pageup': 33, 'pgup': 33, 'home': 36, 'end': 35, 'insert': 45, 'ins': 45})
except Exception:
    pass

def get_vk_code(key_name):
    """Return a virtual-key code for a given human-readable key name.

    Supports:
    - Named keys from VIRTUAL_KEYS (e.g. 'mouse1', 'left_alt', 'space')
    - Single-character keys (e.g. 'q', 'e', '1')
    - Legacy names like 'vk_18' that may have been stored in older configs
    """
    key = str(key_name).lower()
    if key in VIRTUAL_KEYS:
        return VIRTUAL_KEYS[key]
    # Backwards compatibility: accept 'vk_###' style names and parse the numeric code.
    if key.startswith('vk_'):
        try:
            return int(key.split('_', 1)[1])
        except Exception:
            pass
    if len(key) == 1:
        return ord(key.upper())
    return None
PROCESS_QUERY_INFORMATION = 1024
PROCESS_VM_READ = 16
PROCESS_PERMISSIONS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 1
MOUSEEVENTF_LEFTDOWN = 2
MOUSEEVENTF_LEFTUP = 4

def send_mouse_flags(flags: int) -> None:
    try:
        mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)
        inp = INPUT(type=INPUT_MOUSE, ii=INPUT._INPUT(mi=mi))
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    except Exception:
        return

def mouse_left_click(hold_time: float=0.005) -> None:
    send_mouse_flags(MOUSEEVENTF_LEFTDOWN)
    if hold_time:
        time.sleep(max(0.0, float(hold_time)))
    send_mouse_flags(MOUSEEVENTF_LEFTUP)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong), ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):

    class _INPUT(ctypes.Union):
        _fields_ = [('mi', MOUSEINPUT)]
    _fields_ = [('type', ctypes.c_ulong), ('ii', _INPUT)]
SendInput = ctypes.windll.user32.SendInput

def move_mouse(dx, dy):
    mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None)
    inp = INPUT(type=INPUT_MOUSE, ii=INPUT._INPUT(mi=mi))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

class RPMReader:

    def __init__(self, process_id, process_handle, config=None):
        self.process_id = process_id
        self.process_handle = process_handle
        self.memory_interface = None
        try:
            self.memory_interface = MemoryInterface(process_id, process_handle, config)
        except Exception:
            self.memory_interface = None

    def read(self, addr, t='int'):
        try:
            if self.memory_interface:
                if t == 'int':
                    return self.memory_interface.read_int(addr)
                if t == 'long':
                    return self.memory_interface.read_uint64(addr)
                if t == 'float':
                    return self.memory_interface.read_float(addr)
                if t == 'ushort':
                    return self.memory_interface.read_uint32(addr) & 65535
            size_map = {'int': 4, 'long': 8, 'float': 4, 'ushort': 2}
            size = size_map.get(t, 4)
            buffer = (ctypes.c_ubyte * size)()
            bytes_read = ctypes.c_size_t()
            success = kernel32.ReadProcessMemory(self.process_handle, ctypes.c_void_p(addr), ctypes.byref(buffer), size, ctypes.byref(bytes_read))
            if not success or bytes_read.value != size:
                raise RuntimeError(f'RPM failed at {addr:#x}')
            raw = bytes(buffer[:size])
            if t == 'int':
                return int.from_bytes(raw, 'little', signed=True)
            if t == 'long':
                return int.from_bytes(raw, 'little', signed=False)
            if t == 'float':
                return struct.unpack('f', raw)[0]
            if t == 'ushort':
                return int.from_bytes(raw, 'little', signed=False)
        except Exception:
            return None
        return None

    def read_bytes(self, addr, size):
        try:
            if self.memory_interface:
                return self.memory_interface.read_bytes(addr, size)
            buffer = (ctypes.c_ubyte * size)()
            bytes_read = ctypes.c_size_t()
            success = kernel32.ReadProcessMemory(self.process_handle, ctypes.c_void_p(addr), ctypes.byref(buffer), size, ctypes.byref(bytes_read))
            if not success or bytes_read.value != size:
                raise RuntimeError(f'RPM bytes failed at {addr:#x}')
            return bytes(buffer[:bytes_read.value])
        except Exception:
            return None

    def read_vec3(self, address):
        raw = self.read_bytes(address, 12)
        if raw:
            return list(struct.unpack('fff', raw))
        return [0.0, 0.0, 0.0]

class CS2Process:

    def __init__(self, proc_name=None, mod_name=None, timeout=30):
        self.process_name = (proc_name or getattr(Config, 'process_name', 'cs2.exe')).encode()
        self.module_name = (mod_name or getattr(Config, 'module_name', 'client.dll')).encode()
        self.wait_timeout = timeout
        self.process_handle = None
        self.process_id = None
        self.module_base = None

    def _get_pid(self):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE:
            return None
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snap, ctypes.byref(entry)):
            kernel32.CloseHandle(snap)
            return None
        while True:
            if entry.szExeFile == self.process_name:
                pid = entry.th32ProcessID
                kernel32.CloseHandle(snap)
                return pid
            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                break
        kernel32.CloseHandle(snap)
        return None

    def _get_module_base(self):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.process_id)
        if snap == INVALID_HANDLE_VALUE:
            return None
        mod = MODULEENTRY32()
        mod.dwSize = ctypes.sizeof(MODULEENTRY32)
        if not kernel32.Module32First(snap, ctypes.byref(mod)):
            kernel32.CloseHandle(snap)
            return None
        while True:
            if mod.szModule == self.module_name:
                base = ctypes.cast(mod.modBaseAddr, ctypes.c_void_p).value
                kernel32.CloseHandle(snap)
                return base
            if not kernel32.Module32Next(snap, ctypes.byref(mod)):
                break
        kernel32.CloseHandle(snap)
        return None

    def initialize(self):
        start = time.time()
        while time.time() - start < self.wait_timeout:
            self.process_id = self._get_pid()
            if self.process_id:
                self.process_handle = kernel32.OpenProcess(PROCESS_PERMISSIONS, False, self.process_id)
                if self.process_handle:
                    self.module_base = self._get_module_base()
                    if self.module_base:
                        return
            time.sleep(0.5)
        raise TimeoutError('CS2 process or client.dll not found')

    def get_pid(self):
        return self.process_id

    def get_module_base(self):
        return self.module_base

    def __repr__(self):
        return f'<CS2Process pid={self.process_id} base=0x{self.module_base:x}>' if self.module_base else '<CS2Process not ready>'
_PROCNAME_CACHE = {}
_PROCNAME_TTL_S = 0.25

def get_process_image_name(pid: int) -> str | None:
    try:
        pid_i = int(pid)
        if pid_i <= 0:
            return None
        now = time.monotonic()
        cached = _PROCNAME_CACHE.get(pid_i)
        if cached and cached[0] > now:
            return cached[1]
        PROCESS_QUERY_LIMITED_INFORMATION = 4096
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_i)
        if not h:
            return None
        try:
            size = ctypes.wintypes.DWORD(260)
            buf = ctypes.create_unicode_buffer(260)
            q = ctypes.windll.kernel32.QueryFullProcessImageNameW
            if q(h, 0, buf, ctypes.byref(size)):
                name = buf.value.split('\\')[-1].lower() if buf.value else None
                if name:
                    _PROCNAME_CACHE[pid_i] = (now + _PROCNAME_TTL_S, name)
                return name
            return None
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return None
from types import SimpleNamespace
from typing import Dict, Any
from Process.config import Config
Offsets = None
_ClassOffsets = None

def set_global_offsets(offsets, class_offsets=None):
    global Offsets, _ClassOffsets
    Offsets = offsets
    _ClassOffsets = class_offsets

def ensure_offsets_loaded():
    global Offsets, _ClassOffsets
    if Offsets is not None:
        return (Offsets, _ClassOffsets)
    from Process.offset_manager import get_offsets as _get_offsets
    Offsets, _ClassOffsets = _get_offsets(force_update=False)
    return (Offsets, _ClassOffsets)
BONE_POSITIONS = {'head': 6, 'chest': 15, 'left_hand': 10, 'right_hand': 2, 'left_leg': 23, 'right_leg': 26}
BONE_CONNECTIONS = [(0, 2), (2, 4), (4, 5), (5, 6), (4, 8), (8, 9), (9, 10), (4, 13), (13, 14), (14, 15), (0, 22), (22, 23), (23, 24), (0, 25), (25, 26), (26, 27)]

class _ConfigFlagsProxy:

    @staticmethod
    def _snapshot() -> Dict[str, Any]:
        return {'box_esp_enabled': getattr(Config, 'box_esp_enabled', True), 'hp_bar_enabled': getattr(Config, 'hp_bar_enabled', True), 'skeleton_esp_enabled': getattr(Config, 'skeleton_esp_enabled', True), 'name_esp_enabled': getattr(Config, 'name_esp_enabled', True), 'color_bone': getattr(Config, 'color_bone', (255, 255, 255)), 'color_t': getattr(Config, 'color_t', (255, 0, 0)), 'color_ct': getattr(Config, 'color_ct', (0, 128, 255)), 'color_vis_t_visible': getattr(Config, 'color_vis_t_visible', (255, 165, 0)), 'color_vis_t_invisible': getattr(Config, 'color_vis_t_invisible', (255, 0, 0)), 'color_vis_ct_visible': getattr(Config, 'color_vis_ct_visible', (0, 191, 255)), 'color_vis_ct_invisible': getattr(Config, 'color_vis_ct_invisible', (0, 0, 139)), 'color_skeleton_t': getattr(Config, 'color_skeleton_t', getattr(Config, 'color_t', (255, 0, 0))), 'color_skeleton_ct': getattr(Config, 'color_skeleton_ct', getattr(Config, 'color_ct', (0, 128, 255))), 'color_skeleton_t_visible': getattr(Config, 'color_skeleton_t_visible', getattr(Config, 'color_vis_t_visible', (255, 165, 0))), 'color_skeleton_t_invisible': getattr(Config, 'color_skeleton_t_invisible', getattr(Config, 'color_vis_t_invisible', (255, 0, 0))), 'color_skeleton_ct_visible': getattr(Config, 'color_skeleton_ct_visible', getattr(Config, 'color_vis_ct_visible', (0, 191, 255))), 'color_skeleton_ct_invisible': getattr(Config, 'color_skeleton_ct_invisible', getattr(Config, 'color_vis_ct_invisible', (0, 0, 139))), 'color_name_t': getattr(Config, 'color_name_t', getattr(Config, 'color_t', (255, 0, 0))), 'color_name_ct': getattr(Config, 'color_name_ct', getattr(Config, 'color_ct', (0, 128, 255))), 'color_name_other': getattr(Config, 'color_name_other', (255, 255, 255))}

    def get(self, key, default=None):
        return self._snapshot().get(key, default)

    def __getitem__(self, key):
        return self._snapshot()[key]
FLAGS = _ConfigFlagsProxy()

class Entity:
    _NAME_TTL = 2.5
    _TEAM_TTL = 1.0
    _MONEY_TTL = 0.25
    _BONEBUF_TTL = 0.02
    _BONE_STRIDE = 32

    def __init__(self, controller, pawn, handle):
        self.handle = handle
        self.controller = controller
        self.pawn = pawn
        self.cached_frame = -1
        self.last_seen_frame = -1
        self.bone_base = None
        self._h = Offsets.m_iHealth
        self._t = Offsets.m_iTeamNum
        self._p = Offsets.m_vOldOrigin
        self._scene_node_off = Offsets.m_pGameSceneNode
        self._bone_array_off = Offsets.m_pBoneArray
        self._player_name_off = getattr(Offsets, 'm_iszPlayerName', 0)
        self._money_services_off = getattr(Offsets, 'm_pInGameMoneyServices', 0)
        self._money_acc_off = getattr(Offsets, 'm_iAccount', 0)
        self.hp = 0
        self.team = 0
        self.pos = Vec3(0.0, 0.0, 0.0)
        self.head = None
        self.money = 0
        self.name = 'Unknown'
        now = time.perf_counter()
        self._next_name_refresh = now
        self._next_team_refresh = now
        self._next_money_refresh = now
        self._bone_buf = None
        self._bone_buf_min = 0
        self._bone_buf_max = -1
        self._bone_buf_expiry = 0.0

    def touch(self, frame_id: int):
        self.last_seen_frame = frame_id

    def update_refs(self, controller: int, pawn: int, handle):
        self.handle = handle
        self.controller = controller
        self.pawn = pawn

    def update(self, current_frame: int, now=None):
        if self.cached_frame == current_frame:
            return
        self.cached_frame = current_frame
        self.read_data(now=now)

    def _refresh_bone_base(self):
        scene_node = safe_read_uint64(self.handle, self.pawn + self._scene_node_off)
        if not scene_node:
            self.bone_base = None
            return None
        self.bone_base = safe_read_uint64(self.handle, scene_node + self._bone_array_off)
        return self.bone_base

    def read_data(self, now=None):
        if now is None:
            now = time.perf_counter()
        try:
            self.hp = read_int(self.handle, self.pawn + self._h)
        except Exception:
            self.hp = 0
        if self.hp <= 0:
            return
        try:
            self.pos = read_vec3(self.handle, self.pawn + self._p)
        except Exception:
            self.pos = Vec3(0.0, 0.0, 0.0)
        bone_base = self._refresh_bone_base()
        if bone_base:
            head = self.get_bone_positions((BONE_POSITIONS['head'],), now=now).get(BONE_POSITIONS['head'])
            self.head = head
        else:
            self.head = None
        if now >= self._next_team_refresh:
            try:
                self.team = read_int(self.handle, self.pawn + self._t)
            except Exception:
                self.team = 0
            self._next_team_refresh = now + self._TEAM_TTL
        if self._player_name_off and now >= self._next_name_refresh:
            self.name = self.read_name() or 'Unknown'
            self._next_name_refresh = now + self._NAME_TTL
        if self._money_services_off and self._money_acc_off and (now >= self._next_money_refresh):
            try:
                money_services = safe_read_uint64(self.handle, self.controller + self._money_services_off)
                if money_services:
                    self.money = read_int(self.handle, money_services + self._money_acc_off)
            except Exception:
                self.money = 0
            self._next_money_refresh = now + self._MONEY_TTL

    def read_name(self) -> str:
        if not self._player_name_off:
            return 'Unknown'
        try:
            raw = read_bytes(self.handle, self.controller + self._player_name_off, 32)
            if raw:
                s = raw.split(b'\x00')[0].decode(errors='ignore')
                return s.strip() if s else 'Unknown'
        except Exception:
            pass
        return 'Unknown'

    def get_bone_positions(self, indices, now=None):
        if now is None:
            now = time.perf_counter()
        out = {int(i): None for i in indices}
        if not out:
            return out
        if not self.bone_base and (not self._refresh_bone_base()):
            return out
        idxs = [int(i) for i in out.keys() if int(i) >= 0]
        if not idxs:
            return out
        bmin = min(idxs)
        bmax = max(idxs)
        need_new = self._bone_buf is None or now >= self._bone_buf_expiry or bmin < self._bone_buf_min or (bmax > self._bone_buf_max)
        if need_new:
            size = (bmax - bmin + 1) * self._BONE_STRIDE
            base_addr = self.bone_base + bmin * self._BONE_STRIDE
            buf = read_bytes(self.handle, base_addr, size)
            if not buf or len(buf) != size:
                return out
            self._bone_buf = buf
            self._bone_buf_min = bmin
            self._bone_buf_max = bmax
            self._bone_buf_expiry = now + self._BONEBUF_TTL
        buf = self._bone_buf
        stride = self._BONE_STRIDE
        base_min = self._bone_buf_min
        for i in out.keys():
            if i < base_min or i > self._bone_buf_max:
                continue
            off = (i - base_min) * stride
            try:
                x, y, z = struct.unpack_from('fff', buf, off)
                out[i] = Vec3(float(x), float(y), float(z))
            except Exception:
                out[i] = None
        return out
_ENTITY_CACHE: dict[int, Entity] = {}
_ENTITY_FRAME = 0

def get_entities(handle, base):
    global _ENTITY_CACHE, _ENTITY_FRAME
    _ENTITY_FRAME += 1
    frame_id = _ENTITY_FRAME
    now = time.perf_counter()
    try:
        local = safe_read_uint64(handle, base + Offsets.dwLocalPlayerController)
        entity_list = safe_read_uint64(handle, base + Offsets.dwEntityList)
    except Exception:
        return []
    result = []
    for i in range(1, 65):
        try:
            list_entry = safe_read_uint64(handle, entity_list + (8 * ((i & 32767) >> 9) + 16))
            if not list_entry:
                continue
            ctrl = safe_read_uint64(handle, list_entry + 112 * (i & 511))
            if not ctrl or ctrl == local:
                continue
            hPawn = safe_read_uint64(handle, ctrl + Offsets.m_hPlayerPawn)
            if not hPawn:
                continue
            pawn_entry = safe_read_uint64(handle, entity_list + (8 * ((hPawn & 32767) >> 9) + 16))
            if not pawn_entry:
                continue
            pawn = safe_read_uint64(handle, pawn_entry + 112 * (hPawn & 511))
            if not pawn:
                continue
            ent = _ENTITY_CACHE.get(pawn)
            if ent is None:
                ent = Entity(ctrl, pawn, handle)
                _ENTITY_CACHE[pawn] = ent
            else:
                ent.update_refs(ctrl, pawn, handle)
            ent.touch(frame_id)
            ent.update(frame_id, now=now)
            if ent.hp <= 0 or not ent.pawn:
                continue
            result.append(ent)
        except Exception:
            continue
    if frame_id % 60 == 0:
        stale_before = frame_id - 300
        for pawn_addr, ent in list(_ENTITY_CACHE.items()):
            if getattr(ent, 'last_seen_frame', -1) < stale_before:
                _ENTITY_CACHE.pop(pawn_addr, None)
    return result