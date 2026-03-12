import os, sys as _sys_internal
_sys_internal.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
import time
import ctypes
from win32gui import GetWindowText, GetForegroundWindow
from Process.config import Config
from Process.helpers import CS2Process, RPMReader, get_vk_code, ensure_offsets_loaded, mouse_left_click, register_memory_reader
GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState

class TriggerBot:

    def __init__(self, shared_config=None):
        self.shared_config = shared_config if shared_config is not None else Config
        self.Offsets, _ = ensure_offsets_loaded()
        self.cs2 = CS2Process()
        self.cs2.initialize()
        self.client = self.cs2.module_base
        try:
            self.reader = RPMReader(self.cs2.process_id, self.cs2.process_handle, self.shared_config)
            register_memory_reader(self.cs2.process_handle, self.reader)
        except Exception:
            self.reader = None
        self.last_shot_time = 0.0

    def _read_longlong(self, address: int) -> int:
        r = getattr(self, 'reader', None)
        if not r:
            return 0
        try:
            val = r.read(address, 'long')
            return int(val) if val is not None else 0
        except Exception:
            return 0

    def _read_int(self, address: int) -> int:
        r = getattr(self, 'reader', None)
        if not r:
            return 0
        try:
            val = r.read(address, 'int')
            return int(val) if val is not None else 0
        except Exception:
            return 0

    def shoot(self):
        mouse_left_click(hold_time=0.005)

    def enable(self):
        try:
            if GetWindowText(GetForegroundWindow()) != 'Counter-Strike 2':
                return
            if not getattr(self.shared_config, 'triggerbot_always_on', False):
                key_name = getattr(self.shared_config, 'trigger_key', 'mouse5')
                vk = get_vk_code(key_name) or get_vk_code('mouse5') or get_vk_code('shift')
                if vk is None:
                    return
                if not GetAsyncKeyState(vk) & 32768:
                    return
            off = self.Offsets
            if not getattr(off, 'dwLocalPlayerPawn', 0) or not getattr(off, 'dwEntityList', 0):
                return
            player = self._read_longlong(self.client + off.dwLocalPlayerPawn)
            if not player:
                return
            entityId = self._read_int(player + off.m_iIDEntIndex)
            if entityId <= 0:
                return
            entList = self._read_longlong(self.client + off.dwEntityList)
            if not entList:
                return
            entEntry = self._read_longlong(entList + 8 * (entityId >> 9) + 16)
            entity = self._read_longlong(entEntry + 112 * (entityId & 511))
            if not entity:
                return
            entityTeam = self._read_int(entity + off.m_iTeamNum)
            entityHp = self._read_int(entity + off.m_iHealth)
            playerTeam = self._read_int(player + off.m_iTeamNum)
            cooldown = getattr(self.shared_config, 'triggerbot_cooldown', 0.8)
            allow_team = getattr(self.shared_config, 'shoot_teammates', False)
            if entityTeam != 0 and entityHp > 0:
                if allow_team or entityTeam != playerTeam:
                    now = time.time()
                    if now - self.last_shot_time >= float(cooldown):
                        self.shoot()
                        self.last_shot_time = now
        except Exception:
            return

    def run(self):
        try:
            while not getattr(self.shared_config, 'triggerbot_stop', False):
                if getattr(self.shared_config, 'triggerbot_enabled', False):
                    self.enable()
                time.sleep(0.005)
        except KeyboardInterrupt:
            return
if __name__ == '__main__':
    bot = TriggerBot(shared_config=Config)
    bot.run()
