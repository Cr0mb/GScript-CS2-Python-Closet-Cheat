from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

import time
import random
import ctypes
import win32gui
import win32process
import keyboard

from Process.helpers import (
    CS2Process,
    RPMReader,
    ensure_offsets_loaded,
    get_process_image_name,
    register_memory_reader,
)
from Process.config import Config


class BHopProcess:
    VK_SPACE = 32
    KEYEVENTF_KEYDOWN = 0
    KEYEVENTF_KEYUP = 2

    # Tuning knobs for speed / responsiveness
    FOREGROUND_CHECK_INTERVAL = 5          # was 10 (check active window more often)
    MIN_JUMP_INTERVAL = 0.0               # was 0.08s – now basically instant on-ground hop
    NO_SPACE_SLEEP = 0.0002               # was 0.001 – react faster when you press space
    LOOP_SLEEP_MIN = 0.00010              # was 0.0004 + jitter
    LOOP_SLEEP_MAX = 0.00020

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.cs2 = CS2Process()
        self.cs2.initialize()

        self.Offsets, _ = ensure_offsets_loaded()
        if not getattr(self.Offsets, 'dwLocalPlayerPawn', 0):
            raise RuntimeError('[BHop] Offsets not ready')

        self.base = self.cs2.module_base

        try:
            self.reader = RPMReader(self.cs2.process_id, self.cs2.process_handle, Config)
            register_memory_reader(self.cs2.process_handle, self.reader)
        except Exception:
            self.reader = None

        self.last_jump = 0.0
        self.cached_exe = None
        self.iteration = 0

    # ---------------- Memory helpers ---------------- #

    def _read(self, addr: int, size: int) -> bytes | None:
        r = getattr(self, 'reader', None)
        if not r:
            return None
        try:
            return r.read_bytes(addr, size)
        except Exception:
            return None

    def read_int(self, addr: int) -> int:
        data = self._read(addr, 4)
        return int.from_bytes(data, 'little') if data else 0

    def read_ptr(self, addr: int) -> int:
        data = self._read(addr, 8)
        return int.from_bytes(data, 'little') if data else 0

    # ---------------- Input helpers ---------------- #

    def press_space(self):
        """
        Very short press for faster bhops while still being a valid key event.
        """
        self.user32.keybd_event(self.VK_SPACE, 0, self.KEYEVENTF_KEYDOWN, 0)
        # Slightly shorter hold than before (was 0.001)
        time.sleep(0.0005)
        self.user32.keybd_event(self.VK_SPACE, 0, self.KEYEVENTF_KEYUP, 0)

    # ---------------- Main loop ---------------- #

    def run(self):
        fg_check_interval = self.FOREGROUND_CHECK_INTERVAL
        min_jump_interval = self.MIN_JUMP_INTERVAL
        no_space_sleep = self.NO_SPACE_SLEEP
        loop_min = self.LOOP_SLEEP_MIN
        loop_max = self.LOOP_SLEEP_MAX

        while True:
            try:
                if Config.bhop_stop:
                    break

                if not Config.bhop_enabled:
                    self.last_jump = 0.0
                    time.sleep(0.01)
                    continue

                # Refresh foreground exe more often for quicker attach/detach feeling
                if self.iteration % fg_check_interval == 0:
                    hwnd = win32gui.GetForegroundWindow()
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    self.cached_exe = get_process_image_name(pid) if pid else None

                self.iteration += 1

                if self.cached_exe != 'cs2.exe':
                    time.sleep(0.005)
                    continue

                # Only burn CPU when the space key is held
                if not keyboard.is_pressed('space'):
                    time.sleep(no_space_sleep)
                    continue

                pawn = self.read_ptr(self.base + self.Offsets.dwLocalPlayerPawn)
                if not pawn:
                    # Don't sleep long here so we react quickly once pawn is valid
                    time.sleep(loop_min)
                    continue

                flags = self.read_int(pawn + self.Offsets.m_fFlags)
                on_ground = flags & 1

                now = time.monotonic()
                if on_ground and (now - self.last_jump) > min_jump_interval:
                    # Faster hop: fire jump as soon as we detect on_ground
                    self.press_space()
                    self.last_jump = now

                # Tight loop sleep, still with a tiny jitter to avoid a perfectly fixed pattern
                time.sleep(loop_min + random.uniform(0.0, loop_max - loop_min))

            except Exception:
                # Fail soft – if something glitches, back off briefly
                time.sleep(0.01)

        return


if __name__ == '__main__':
    BHopProcess().run()
