from __future__ import annotations
import ctypes
import math
import threading
import time
from ctypes import wintypes as wt

# Fallback aliases: some Python builds don't expose HCURSOR/HICON/HBRUSH in wintypes
for _name in ("HCURSOR", "HICON", "HBRUSH"):
    if not hasattr(wt, _name):
        # These are all HANDLE-sized on Windows, so HANDLE is a safe stand-in
        setattr(wt, _name, wt.HANDLE)


from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    from Process.offsets import Offsets
except Exception:
    from offsets import Offsets

try:
    from Process.config import Config
except Exception:
    try:
        from config import Config
    except Exception:

        class Config:
            pass


try:
    from Process.helpers import CS2Process, RPMReader, ensure_offsets_loaded, register_memory_reader, get_entities
except Exception:
    CS2Process = None
    RPMReader = None
    ensure_offsets_loaded = None

    def register_memory_reader(*_args, **_kwargs):
        return None


try:
    _user32_capture = ctypes.windll.user32
    _WDA_NONE = 0
    _WDA_EXCLUDEFROMCAPTURE = 17
except Exception:
    _user32_capture = None
    _WDA_NONE = 0
    _WDA_EXCLUDEFROMCAPTURE = 17


def _set_radar_capture_excluded(hwnd, excluded: bool) -> None:
    if _user32_capture is None or not hwnd:
        return
    try:
        current = getattr(_set_radar_capture_excluded, '_state', None)
        if current is not None and bool(current) == bool(excluded):
            return
        mode = _WDA_EXCLUDEFROMCAPTURE if excluded else _WDA_NONE
        _user32_capture.SetWindowDisplayAffinity(hwnd, mode)
        setattr(_set_radar_capture_excluded, '_state', bool(excluded))
    except Exception:
        pass


user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
user32.RegisterClassExW.restype = wt.ATOM

user32.CreateWindowExW.argtypes = [
    wt.DWORD,
    wt.LPCWSTR,
    wt.LPCWSTR,
    wt.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wt.HWND,
    wt.HMENU,
    wt.HINSTANCE,
    wt.LPVOID,
]
user32.CreateWindowExW.restype = wt.HWND

user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL

user32.UpdateWindow.argtypes = [wt.HWND]
user32.UpdateWindow.restype = wt.BOOL

user32.GetMessageW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int

user32.PeekMessageW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PeekMessageW.restype = wt.BOOL

user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.TranslateMessage.restype = wt.BOOL

user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.restype = LRESULT

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC

user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int

user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL

user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, wt.BYTE, wt.DWORD]
user32.SetLayeredWindowAttributes.restype = wt.BOOL

user32.GetCursorPos.argtypes = [ctypes.c_void_p]
user32.GetCursorPos.restype = wt.BOOL

user32.ScreenToClient.argtypes = [wt.HWND, ctypes.c_void_p]
user32.ScreenToClient.restype = wt.BOOL

user32.ClientToScreen.argtypes = [wt.HWND, ctypes.c_void_p]
user32.ClientToScreen.restype = wt.BOOL

user32.GetWindowRect.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetWindowRect.restype = wt.BOOL

user32.SetCapture.argtypes = [wt.HWND]
user32.SetCapture.restype = wt.HWND

user32.ReleaseCapture.argtypes = []
user32.ReleaseCapture.restype = wt.BOOL

user32.FillRect.argtypes = [wt.HDC, ctypes.c_void_p, wt.HBRUSH]
user32.FillRect.restype = ctypes.c_int

user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wt.UINT]
user32.DrawTextW.restype = ctypes.c_int

gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetTextColor.restype = wt.COLORREF

gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC

gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL

gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP

gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ

gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL

gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.BitBlt.restype = wt.BOOL

gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]
gdi32.CreateSolidBrush.restype = wt.HBRUSH

gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.COLORREF]
gdi32.CreatePen.restype = wt.HPEN

gdi32.Rectangle.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.Rectangle.restype = wt.BOOL

gdi32.Ellipse.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.Ellipse.restype = wt.BOOL

gdi32.MoveToEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
gdi32.MoveToEx.restype = wt.BOOL

gdi32.LineTo.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.LineTo.restype = wt.BOOL

gdi32.SetDCBrushColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetDCBrushColor.restype = wt.COLORREF

gdi32.SetDCPenColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetDCPenColor.restype = wt.COLORREF

gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wt.HGDIOBJ

gdi32.SetBkColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkColor.restype = wt.COLORREF

gdi32.SetTextAlign.argtypes = [wt.HDC, wt.UINT]
gdi32.SetTextAlign.restype = wt.UINT

gdi32.SetMapMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.SetMapMode.restype = ctypes.c_int

gdi32.SetStretchBltMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.SetStretchBltMode.restype = ctypes.c_int

SW_HIDE = 0
SW_SHOW = 5

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000

LWA_ALPHA = 0x2

HWND_TOPMOST = wt.HWND(-1)
HWND_NOTOPMOST = wt.HWND(-2)

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200

PM_REMOVE = 0x0001
SRCCOPY = 0x00CC0020

TRANSPARENT = 1

DT_LEFT = 0x0000
DT_TOP = 0x0000
DT_SINGLELINE = 0x0020
DT_VCENTER = 0x0004
DT_NOPREFIX = 0x0800

DC_BRUSH = 18
DC_PEN = 19
NULL_BRUSH = 5


def _rgb(r: int, g: int, b: int) -> int:
    return (b << 16) | (g << 8) | r


def _lo_word(dword: int) -> int:
    return dword & 0xFFFF


def _hi_word(dword: int) -> int:
    return (dword >> 16) & 0xFFFF


def _sign16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


@dataclass
class RadarBlip:
    x: float
    y: float
    yaw: float
    team: int


@dataclass
class RadarSnapshot:
    local_x: float = 0.0
    local_y: float = 0.0
    local_yaw: float = 0.0
    local_team: int = 0
    blips: List[RadarBlip] = None
    last_ok: float = 0.0
    connected: bool = False

    def __post_init__(self):
        if self.blips is None:
            self.blips = []


class RadarReader(threading.Thread):
    def __init__(self, snapshot: RadarSnapshot, lock: threading.Lock, cfg_ref=None, fps: float = 60.0):
        super().__init__(daemon=True)
        self.snapshot = snapshot
        self.lock = lock
        self.cfg_ref = cfg_ref if cfg_ref is not None else Config
        self.fps = max(10.0, float(fps))
        self._stop = threading.Event()
        self._cs2: Optional['CS2Process'] = None
        self._reader: Optional['RPMReader'] = None
        self._base: int = 0
        try:
            if ensure_offsets_loaded is not None:
                self._o, _ = ensure_offsets_loaded()
            else:
                self._o = Offsets() if callable(getattr(Offsets, '__call__', None)) else Offsets
        except Exception:
            self._o = Offsets() if callable(getattr(Offsets, '__call__', None)) else Offsets

    def stop(self) -> None:
        self._stop.set()

    def _set_disconnected(self) -> None:
        with self.lock:
            self.snapshot.connected = False
            self.snapshot.blips = []
        self._cs2 = None
        self._reader = None
        self._base = 0

    def _ensure_connected(self) -> bool:
        if self._reader is not None and self._base:
            return True
        self._set_disconnected()
        if CS2Process is None or RPMReader is None:
            return False
        try:
            cs2 = CS2Process()
            cs2.initialize()
            reader = RPMReader(cs2.process_id, cs2.process_handle, self.cfg_ref)
            try:
                register_memory_reader(cs2.process_handle, reader)
            except Exception:
                pass
            self._cs2 = cs2
            self._reader = reader
            self._base = int(cs2.module_base or 0)
            with self.lock:
                self.snapshot.connected = True
            return True
        except Exception:
            self._cs2 = None
            self._reader = None
            self._base = 0
            return False

    def run(self) -> None:
        while not self._stop.is_set() and (not bool(getattr(self.cfg_ref, 'radar_stop', False))):
            t0 = time.perf_counter()

            if not bool(getattr(self.cfg_ref, 'radar_enabled', False)):
                with self.lock:
                    self.snapshot.blips = []
                    self.snapshot.connected = False
                    self.snapshot.last_ok = time.time()
                time.sleep(0.1)
                continue

            try:
                if not self._ensure_connected():
                    time.sleep(0.5)
                    continue

                if self._reader is None or not self._base:
                    self._set_disconnected()
                    time.sleep(0.2)
                    continue

                rpm = self._reader
                o = self._o
                base = self._base

                local_pawn = rpm.read(base + o.dwLocalPlayerPawn, 'long') or 0
                if not local_pawn:
                    with self.lock:
                        self.snapshot.blips = []
                        self.snapshot.last_ok = time.time()
                    time.sleep(0.05)
                    continue

                local_team = rpm.read(local_pawn + o.m_iTeamNum, 'int') or 0
                lx, ly, _lz = rpm.read_vec3(local_pawn + o.m_vOldOrigin)
                local_yaw = rpm.read(base + o.dwViewAngles + 4, 'float') or 0.0

                handle = getattr(self._cs2, 'process_handle', None)
                blips: List[RadarBlip] = []
                entities = []

                if handle:
                    try:
                        entities = get_entities(handle, base)
                    except Exception:
                        entities = []

                for ent in entities:
                    pawn = getattr(ent, 'pawn', 0)
                    if not pawn or pawn == local_pawn:
                        continue

                    hp = getattr(ent, 'hp', None)
                    if hp is None:
                        hp = rpm.read(pawn + o.m_iHealth, 'int') or 0
                    if hp <= 0:
                        continue

                    dormant = rpm.read(pawn + o.m_bDormant, 'int') or 0
                    if dormant:
                        continue

                    team = getattr(ent, 'team', None)
                    if team is None:
                        team = rpm.read(pawn + o.m_iTeamNum, 'int') or 0

                    pos = getattr(ent, 'pos', None)
                    if pos is not None:
                        try:
                            ex, ey, _ez = (pos.x, pos.y, pos.z)
                        except Exception:
                            try:
                                ex, ey, _ez = pos
                            except Exception:
                                ex, ey, _ez = rpm.read_vec3(pawn + o.m_vOldOrigin)
                    else:
                        ex, ey, _ez = rpm.read_vec3(pawn + o.m_vOldOrigin)

                    eyaw = rpm.read(pawn + o.m_angEyeAngles + 4, 'float') or 0.0
                    blips.append(RadarBlip(x=ex, y=ey, yaw=eyaw, team=team))

                with self.lock:
                    self.snapshot.local_x = lx
                    self.snapshot.local_y = ly
                    self.snapshot.local_yaw = local_yaw
                    self.snapshot.local_team = local_team
                    self.snapshot.blips = blips
                    self.snapshot.last_ok = time.time()
                    self.snapshot.connected = True
            except Exception:
                self._set_disconnected()

            dt = time.perf_counter() - t0
            try:
                desired = float(getattr(self.cfg_ref, 'radar_reader_fps', self.fps))
            except Exception:
                desired = self.fps
            desired = max(5.0, min(240.0, desired))
            tick = 1.0 / desired
            if dt < tick:
                time.sleep(tick - dt)


class RadarStyle:
    width: int = 280
    height: int = 280
    header_h: int = 22
    padding: int = 10

    bg: int = _rgb(20, 20, 32)
    border: int = _rgb(255, 255, 255)
    border_shadow: int = _rgb(64, 64, 64)

    title_text: int = _rgb(245, 245, 247)
    sub_text: int = _rgb(200, 200, 210)

    me_dot: int = _rgb(255, 255, 255)
    me_dir: int = _rgb(0, 255, 0)

    enemy_dot: int = _rgb(255, 0, 0)
    team_dot: int = _rgb(0, 128, 255)
    enemy_dir: int = _rgb(255, 255, 0)


class RadarOverlay:
    def __init__(self, snapshot: RadarSnapshot, lock: threading.Lock, cfg_ref=None, title: str = '', fps: float = 60.0):
        self.snapshot = snapshot
        self.lock = lock
        self.title = title
        self.fps = max(20.0, float(fps))
        self.style = RadarStyle()
        self.cfg_ref = cfg_ref if cfg_ref is not None else Config

        try:
            self.style.width = int(getattr(self.cfg_ref, 'radar_width', self.style.width))
            self.style.height = int(getattr(self.cfg_ref, 'radar_height', self.style.height))
        except Exception:
            pass

        try:
            self.fps = max(20.0, float(getattr(self.cfg_ref, 'radar_fps', fps)))
        except Exception:
            self.fps = max(20.0, float(fps))

        self.hwnd: wt.HWND = wt.HWND(0)
        self._running = False

        self._dragging = False
        self._drag_dx = 0
        self._drag_dy = 0

        self._resizing = False
        self._resize_edge = ''
        self._resize_margin = 8
        self._min_w = 180
        self._min_h = 180
        self._rs_start_pt = wt.POINT()
        self._rs_start_rect = wt.RECT()
        self._last_realloc = 0.0

        self._hdc_win: wt.HDC = wt.HDC(0)
        self._hdc_mem: wt.HDC = wt.HDC(0)
        self._bmp: wt.HBITMAP = wt.HBITMAP(0)
        self._old_bmp: wt.HGDIOBJ = wt.HGDIOBJ(0)

        self._dc_pen = gdi32.GetStockObject(DC_PEN)
        self._dc_brush = gdi32.GetStockObject(DC_BRUSH)

        self._class_name = 'GFusionRadarWindow'
        self._wndproc = WNDPROC(self._on_wndproc)

    def create(self, x: int = 40, y: int = 120, alpha: int = 235) -> None:
        self._register_class()
        ex_style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED
        style = WS_POPUP | WS_VISIBLE
        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            self._class_name,
            self.title,
            style,
            int(x),
            int(y),
            int(self.style.width),
            int(self.style.height),
            None,
            None,
            hinst,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        user32.SetLayeredWindowAttributes(self.hwnd, 0, wt.BYTE(max(30, min(alpha, 255))), LWA_ALPHA)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.UpdateWindow(self.hwnd)
        self._init_gdi()

    def _register_class(self) -> None:
        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wt.UINT),
                ('style', wt.UINT),
                ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE),
                ('hIcon', wt.HICON),
                ('hCursor', wt.HCURSOR),
                ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR),
                ('lpszClassName', wt.LPCWSTR),
                ('hIconSm', wt.HICON),
            ]

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = user32.LoadCursorW(None, wt.LPCWSTR(32512))
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self._class_name
        wc.hIconSm = None

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err != 1410:  # already registered
                raise ctypes.WinError(err)

    def _init_gdi(self) -> None:
        self._hdc_win = user32.GetDC(self.hwnd)
        if not self._hdc_win:
            raise ctypes.WinError(ctypes.get_last_error())

        self._hdc_mem = gdi32.CreateCompatibleDC(self._hdc_win)
        if not self._hdc_mem:
            raise ctypes.WinError(ctypes.get_last_error())

        self._bmp = gdi32.CreateCompatibleBitmap(self._hdc_win, self.style.width, self.style.height)
        if not self._bmp:
            raise ctypes.WinError(ctypes.get_last_error())

        self._old_bmp = gdi32.SelectObject(self._hdc_mem, self._bmp)
        gdi32.SelectObject(self._hdc_mem, self._dc_pen)
        gdi32.SelectObject(self._hdc_mem, self._dc_brush)
        gdi32.SetBkMode(self._hdc_mem, TRANSPARENT)

    def _shutdown_gdi(self) -> None:
        if self._hdc_mem:
            if self._old_bmp:
                gdi32.SelectObject(self._hdc_mem, self._old_bmp)
            if self._bmp:
                gdi32.DeleteObject(self._bmp)
            gdi32.DeleteDC(self._hdc_mem)

        self._hdc_mem = wt.HDC(0)
        self._bmp = wt.HBITMAP(0)
        self._old_bmp = wt.HGDIOBJ(0)

        if self._hdc_win:
            user32.ReleaseDC(self.hwnd, self._hdc_win)
        self._hdc_win = wt.HDC(0)

    def _hit_test_edge(self, x: int, y: int) -> str:
        m = int(self._resize_margin)
        w = int(self.style.width)
        h = int(self.style.height)

        on_l = x <= m
        on_r = x >= w - 1 - m
        on_t = y <= m
        on_b = y >= h - 1 - m

        if on_t and on_l:
            return 'tl'
        if on_t and on_r:
            return 'tr'
        if on_b and on_l:
            return 'bl'
        if on_b and on_r:
            return 'br'
        if on_l:
            return 'l'
        if on_r:
            return 'r'
        if on_t:
            return 't'
        if on_b:
            return 'b'
        return ''

    def _start_resize(self, hwnd: wt.HWND, edge: str) -> None:
        self._resizing = True
        self._resize_edge = edge
        user32.GetWindowRect(hwnd, ctypes.byref(self._rs_start_rect))
        user32.GetCursorPos(ctypes.byref(self._rs_start_pt))
        user32.SetCapture(hwnd)

    def _apply_resize(self, hwnd: wt.HWND) -> None:
        pt = wt.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        dx = int(pt.x - self._rs_start_pt.x)
        dy = int(pt.y - self._rs_start_pt.y)

        r0 = self._rs_start_rect
        left = int(r0.left)
        top = int(r0.top)
        right = int(r0.right)
        bottom = int(r0.bottom)
        edge = self._resize_edge

        if 'l' in edge:
            left += dx
        if 'r' in edge:
            right += dx
        if 't' in edge:
            top += dy
        if 'b' in edge:
            bottom += dy

        min_w = int(self._min_w)
        min_h = int(self._min_h)

        w = right - left
        h = bottom - top

        if w < min_w:
            if 'l' in edge and 'r' not in edge:
                left = right - min_w
            else:
                right = left + min_w
            w = min_w

        if h < min_h:
            if 't' in edge and 'b' not in edge:
                top = bottom - min_h
            else:
                bottom = top + min_h
            h = min_h

        insert_after = HWND_TOPMOST if bool(getattr(self.cfg_ref, 'radar_always_on_top', True)) else HWND_NOTOPMOST
        user32.SetWindowPos(hwnd, insert_after, left, top, w, h, SWP_NOACTIVATE)

        self._cfg_set('radar_x', left)
        self._cfg_set('radar_y', top)
        self._cfg_set('radar_width', w)
        self._cfg_set('radar_height', h)

        now = time.perf_counter()
        if now - self._last_realloc > 0.02:
            self._last_realloc = now
            self._resize_backbuffer(w, h)

    def _resize_backbuffer(self, new_w: int, new_h: int) -> None:
        new_w = int(max(self._min_w, new_w))
        new_h = int(max(self._min_h, new_h))
        if new_w == int(self.style.width) and new_h == int(self.style.height):
            return

        self.style.width = new_w
        self.style.height = new_h
        self._cfg_set('radar_width', int(new_w))
        self._cfg_set('radar_height', int(new_h))

        if not self._hdc_win or not self._hdc_mem:
            return

        if self._hdc_mem and self._old_bmp:
            gdi32.SelectObject(self._hdc_mem, self._old_bmp)
        if self._bmp:
            gdi32.DeleteObject(self._bmp)

        bmp = gdi32.CreateCompatibleBitmap(self._hdc_win, new_w, new_h)
        if not bmp:
            return

        self._bmp = bmp
        self._old_bmp = gdi32.SelectObject(self._hdc_mem, self._bmp)
        gdi32.SelectObject(self._hdc_mem, self._dc_pen)
        gdi32.SelectObject(self._hdc_mem, self._dc_brush)

    def _on_wndproc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_DESTROY:
            self._running = False
            user32.PostQuitMessage(0)
            return 0

        if msg == WM_ERASEBKGND:
            return 1

        if msg == WM_LBUTTONDOWN:
            x = _sign16(_lo_word(lparam))
            y = _sign16(_hi_word(lparam))
            edge = self._hit_test_edge(x, y)
            if edge:
                self._start_resize(hwnd, edge)
                return 0
            if 0 <= x < self.style.width and 0 <= y < self.style.header_h:
                self._dragging = True
                self._drag_dx = x
                self._drag_dy = y
                user32.SetCapture(hwnd)
                return 0
            return 0

        if msg == WM_LBUTTONUP:
            if self._dragging or self._resizing:
                self._dragging = False
                self._resizing = False
                self._resize_edge = ''
                user32.ReleaseCapture()
            return 0

        if msg == WM_MOUSEMOVE:
            if self._resizing:
                self._apply_resize(hwnd)
                return 0
            if self._dragging:
                pt = wt.POINT()
                if user32.GetCursorPos(ctypes.byref(pt)):
                    new_x = int(pt.x - self._drag_dx)
                    new_y = int(pt.y - self._drag_dy)
                    insert_after = HWND_TOPMOST if bool(getattr(self.cfg_ref, 'radar_always_on_top', True)) else HWND_NOTOPMOST
                    user32.SetWindowPos(hwnd, insert_after, new_x, new_y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    self._cfg_set('radar_x', new_x)
                    self._cfg_set('radar_y', new_y)
                return 0

        return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

    def _cfg_get(self, key: str, default):
        try:
            return getattr(self.cfg_ref, key)
        except Exception:
            return default

    def _cfg_set(self, key: str, value) -> None:
        try:
            setattr(self.cfg_ref, key, value)
        except Exception:
            pass

    def _apply_cfg_runtime(self) -> None:
        if getattr(self, '_dragging', False) or getattr(self, '_resizing', False):
            return
        if not self.hwnd:
            return

        try:
            hide_capture = bool(self._cfg_get('hide_esp_from_capture', False))
        except Exception:
            hide_capture = False
        _set_radar_capture_excluded(self.hwnd, hide_capture)

        enabled = bool(self._cfg_get('radar_enabled', True))
        user32.ShowWindow(self.hwnd, SW_SHOW if enabled else SW_HIDE)
        if not enabled:
            return

        try:
            x = int(self._cfg_get('radar_x', 40))
            y = int(self._cfg_get('radar_y', 120))
            w = int(self._cfg_get('radar_width', self.style.width))
            h = int(self._cfg_get('radar_height', self.style.height))
        except Exception:
            x, y, w, h = (40, 120, self.style.width, self.style.height)

        w = max(self._min_w, w)
        h = max(self._min_h, h)

        try:
            alpha = int(self._cfg_get('radar_alpha', 235))
        except Exception:
            alpha = 235
        alpha = max(60, min(255, alpha))

        topmost = bool(self._cfg_get('radar_always_on_top', True))
        insert_after_hwnd = HWND_TOPMOST if topmost else HWND_NOTOPMOST

        user32.SetWindowPos(self.hwnd, insert_after_hwnd, x, y, w, h, SWP_NOACTIVATE)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, alpha, LWA_ALPHA)

        if w != self.style.width or h != self.style.height:
            self._resize_backbuffer(w, h)

    def stop(self) -> None:
        self._running = False
        self._cfg_set('radar_stop', True)
        if self.hwnd:
            try:
                user32.PostMessageW(self.hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass

    def _clear(self, color: int) -> None:
        rect = wt.RECT(0, 0, self.style.width, self.style.height)
        brush = gdi32.CreateSolidBrush(color)
        user32.FillRect(self._hdc_mem, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)

    def _rect(self, x1: int, y1: int, x2: int, y2: int, border: int, fill: Optional[int] = None) -> None:
        if fill is not None:
            gdi32.SetDCBrushColor(self._hdc_mem, fill)
        else:
            gdi32.SelectObject(self._hdc_mem, gdi32.GetStockObject(NULL_BRUSH))
        gdi32.SetDCPenColor(self._hdc_mem, border)
        gdi32.Rectangle(self._hdc_mem, x1, y1, x2, y2)
        gdi32.SelectObject(self._hdc_mem, self._dc_brush)

    def _circle(self, cx: int, cy: int, r: int, border: int, fill: Optional[int] = None) -> None:
        if fill is not None:
            gdi32.SetDCBrushColor(self._hdc_mem, fill)
        else:
            gdi32.SelectObject(self._hdc_mem, gdi32.GetStockObject(NULL_BRUSH))
        gdi32.SetDCPenColor(self._hdc_mem, border)
        gdi32.Ellipse(self._hdc_mem, cx - r, cy - r, cx + r, cy + r)
        gdi32.SelectObject(self._hdc_mem, self._dc_brush)

    def _line(self, x1: int, y1: int, x2: int, y2: int, color: int, width: int = 1) -> None:
        pen = gdi32.CreatePen(0, int(width), color)
        old = gdi32.SelectObject(self._hdc_mem, pen)
        gdi32.MoveToEx(self._hdc_mem, int(x1), int(y1), None)
        gdi32.LineTo(self._hdc_mem, int(x2), int(y2))
        gdi32.SelectObject(self._hdc_mem, old)
        gdi32.DeleteObject(pen)

    def _text(self, s: str, x: int, y: int, w: int, h: int, color: int, center_y: bool = True) -> None:
        rect = wt.RECT(int(x), int(y), int(x + w), int(y + h))
        gdi32.SetTextColor(self._hdc_mem, color)
        fmt = DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX if center_y else DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOPREFIX
        user32.DrawTextW(self._hdc_mem, s, -1, ctypes.byref(rect), fmt)

    def _world_to_radar(
        self,
        ex: float,
        ey: float,
        lx: float,
        ly: float,
        cos_a: float,
        sin_a: float,
        scale: float,
    ) -> Tuple[float, float]:
        dx = ey - ly
        dy = ex - lx
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        return (rx * scale, ry * scale)

    def _render(self) -> None:
        st = self.style
        with self.lock:
            snap = (
                self.snapshot.connected,
                self.snapshot.local_x,
                self.snapshot.local_y,
                self.snapshot.local_yaw,
                self.snapshot.local_team,
                list(self.snapshot.blips),
                self.snapshot.last_ok,
            )
        connected, lx, ly, lyaw, lteam, blips, last_ok = snap

        fixed = bool(self._cfg_get('radar_fixed_range', False))
        if fixed:
            try:
                max_dist = float(self._cfg_get('radar_range_units', 3000.0))
            except Exception:
                max_dist = 3000.0
        else:
            max_dist = 1.0
            for b in blips:
                d = math.hypot(b.x - lx, b.y - ly)
                if d > max_dist:
                    max_dist = d

        max_dist = max(250.0, max_dist)
        scale = min(st.width, st.height) / 2.2 / max_dist
        scale = max(0.05, min(scale, 0.5))

        self._clear(st.bg)

        self._rect(0, 0, st.width - 1, st.height - 1, st.border, None)
        header_fill = _rgb(30, 30, 48)
        self._rect(1, 1, st.width - 2, st.header_h, st.border_shadow, header_fill)

        status = 'CONNECTED' if connected else 'WAITING'
        self._text(f'{self.title}  [{status}]', 8, 1, st.width - 16, st.header_h - 2, st.title_text, center_y=True)

        pad = st.padding
        top = st.header_h + pad
        left = pad
        right = st.width - pad
        bottom = st.height - pad

        radar_fill = _rgb(16, 16, 24)
        self._rect(left, top, right, bottom, st.border_shadow, radar_fill)

        cx = (left + right) // 2
        cy = (top + bottom) // 2

        self._circle(cx, cy, 3, st.me_dot, st.me_dot)

        yaw_rad = math.radians(lyaw)
        fx, fy = (math.cos(yaw_rad), math.sin(yaw_rad))
        dx = fy * 50.0
        dy = fx * 50.0

        angle = math.radians(lyaw + 180.0)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        if bool(self._cfg_get('radar_show_me_dir', True)):
            self._line(cx, cy, int(cx + rx * scale), int(cy + ry * scale), st.me_dir, 2)

        show_team = bool(self._cfg_get('radar_show_team', True))
        show_enemy_dir = bool(self._cfg_get('radar_show_enemy_dir', True))
        show_team_dir = bool(self._cfg_get('radar_show_team_dir', False))

        for b in blips:
            if b.team == lteam and (not show_team):
                continue

            rx, ry = self._world_to_radar(b.x, b.y, lx, ly, cos_a, sin_a, scale)
            px = int(cx + rx)
            py = int(cy + ry)
            px = max(left + 4, min(right - 4, px))
            py = max(top + 4, min(bottom - 4, py))

            dot = st.enemy_dot if b.team != lteam else st.team_dot
            self._circle(px, py, 4, dot, dot)

            if b.team != lteam and show_enemy_dir or (b.team == lteam and show_team_dir):
                eyaw_rad = math.radians(b.yaw)
                fx2, fy2 = (math.cos(eyaw_rad), math.sin(eyaw_rad))
                ex2 = b.x + fx2 * 50.0
                ey2 = b.y + fy2 * 50.0
                rx2, ry2 = self._world_to_radar(ex2, ey2, lx, ly, cos_a, sin_a, scale)
                px2 = int(cx + rx2)
                py2 = int(cy + ry2)
                px2 = max(left + 4, min(right - 4, px2))
                py2 = max(top + 4, min(bottom - 4, py2))
                self._line(px, py, px2, py2, st.enemy_dir, 1)

        gdi32.BitBlt(self._hdc_win, 0, 0, st.width, st.height, self._hdc_mem, 0, 0, SRCCOPY)

    def run(self) -> None:
        if not self.hwnd:
            self.create(
                x=int(self._cfg_get('radar_x', 40)),
                y=int(self._cfg_get('radar_y', 120)),
                alpha=int(self._cfg_get('radar_alpha', 235)),
            )
        self._running = True
        self._last_frame = time.perf_counter()
        frame_dt = 1.0 / max(20.0, float(self._cfg_get('radar_fps', self.fps)))

        class MSG(ctypes.Structure):
            _fields_ = [
                ('hwnd', wt.HWND),
                ('message', wt.UINT),
                ('wParam', wt.WPARAM),
                ('lParam', wt.LPARAM),
                ('time', wt.DWORD),
                ('pt', wt.POINT),
            ]

        msg = MSG()
        while self._running and (not bool(self._cfg_get('radar_stop', False))):
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            now = time.perf_counter()
            if now - self._last_frame >= frame_dt:
                self._apply_cfg_runtime()
                try:
                    frame_dt = 1.0 / max(20.0, float(self._cfg_get('radar_fps', self.fps)))
                except Exception:
                    pass
                self._last_frame = now
                self._render()
            else:
                time.sleep(0.001)

        self._shutdown_gdi()


class RadarApp:
    def __init__(self, title: str = '', cfg_ref=None):
        self.lock = threading.Lock()
        self.snapshot = RadarSnapshot()
        self.cfg_ref = cfg_ref if cfg_ref is not None else Config

        defaults = {
            'radar_enabled': False,
            'radar_stop': False,
            'radar_x': 40,
            'radar_y': 120,
            'radar_width': 280,
            'radar_height': 280,
            'radar_alpha': 235,
            'radar_fps': 60.0,
            'radar_reader_fps': 60.0,
            'radar_always_on_top': True,
            'radar_show_team': True,
            'radar_show_me_dir': True,
            'radar_show_enemy_dir': True,
            'radar_show_team_dir': False,
            'radar_fixed_range': False,
            'radar_range_units': 3000.0,
        }
        for k, v in defaults.items():
            try:
                if not hasattr(self.cfg_ref, k):
                    setattr(self.cfg_ref, k, v)
            except Exception:
                pass

        self.reader = RadarReader(
            self.snapshot,
            self.lock,
            cfg_ref=self.cfg_ref,
            fps=float(getattr(self.cfg_ref, 'radar_reader_fps', 60.0)),
        )
        self.overlay = RadarOverlay(
            self.snapshot,
            self.lock,
            cfg_ref=self.cfg_ref,
            title=title,
            fps=float(getattr(self.cfg_ref, 'radar_fps', 60.0)),
        )

    def start(self) -> None:
        self.reader.start()
        self.overlay.run()

    def stop(self) -> None:
        try:
            setattr(self.cfg_ref, 'radar_stop', True)
        except Exception:
            pass
        self.reader.stop()
        try:
            self.overlay.stop()
        except Exception:
            pass


def main() -> None:
    app = RadarApp(cfg_ref=Config)
    app.start()


if __name__ == '__main__':
    main()
