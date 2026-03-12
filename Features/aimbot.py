import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
import time
import math
import threading
import ctypes
import struct
from ctypes import wintypes
from Process.helpers import CS2Process, RPMReader, get_vk_code, move_mouse, ensure_offsets_loaded, set_current_dynamic_fov, register_memory_reader, get_entities, get_module_base
from Process.config import Config
try:
    # Share the exact same vischeck helpers that ESP uses
    from Features import esp as _esp_module
    from Features.esp import check_player_visibility, auto_map_loader
    ESP_VISCHECK_AVAILABLE = True
except Exception:
    _esp_module = None
    ESP_VISCHECK_AVAILABLE = False
    check_player_visibility = None
    auto_map_loader = None
BONES = {'head': 6, 'neck': 5, 'chest': 2, 'stomach': 15, 'pelvis': 0, 'right_hand': 10, 'left_hand': 13, 'right_leg': 26, 'left_leg': 23}
DEFAULT_AIM_BONES = (BONES['head'], BONES['neck'], BONES['chest'], BONES['pelvis'], BONES['left_hand'], BONES['right_hand'], BONES['left_leg'], BONES['right_leg'])

class AimbotRCS:
    MAX_DELTA_ANGLE = 60
    SENSITIVITY = None
    INVERT_Y = -1

    def __init__(self, cfg):
        self.cfg = cfg
        self.o, _ = ensure_offsets_loaded()
        self.cs2 = CS2Process()
        self.cs2.initialize()
        self.matchmaking_base = get_module_base(self.cs2.process_id, 'matchmaking.dll')
        self.base = self.cs2.module_base
        self.process_handle = self.cs2.process_handle
        self.reader = RPMReader(self.cs2.process_id, self.process_handle, cfg)
        register_memory_reader(self.process_handle, self.reader)
        self.local_player_controller = self.base + self.o.dwLocalPlayerController
        self.bone_indices = BONES
        self.left_down = False
        self.shots_fired = 0
        self.last_punch = (0.0, 0.0)
        self.target_key = None
        self.prev_target_key = None
        self.aim_start_time = None
        self.last_aim_angle = None
        self.recoil_active = False
        self.lock = threading.Lock()
        self._isnan = math.isnan
        self._hypot = math.hypot
        self._atan2 = math.atan2
        self._degrees = math.degrees
        self.vis_checker = None
        self.use_esp_vischeck = ESP_VISCHECK_AVAILABLE

    @staticmethod
    def ease_out_quint(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 1 - (1 - t) ** 5

    @staticmethod
    def ease_out_cubic(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 1 - (1 - t) ** 3

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t

    def reset_recoil(self, reason='unknown'):
        with self.lock:
            self.shots_fired = 0
            self.last_punch = (0.0, 0.0)
            self.recoil_active = False

    def read_vec3(self, addr):
        return self.reader.read_vec3(addr)

    def read(self, addr, t='int'):
        return self.reader.read(addr, t)

    def is_cs2_focused(self):
        user32 = ctypes.windll.user32
        kernel32_local = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        PROCESS_QUERY_LIMITED_INFORMATION = 4096
        PROCESS_VM_READ = 16
        PROCESS_QUERY_INFORMATION = 1024
        hProcess = kernel32_local.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid.value)
        if not hProcess:
            return False
        try:
            buffer_len = wintypes.DWORD(260)
            exe_path_buffer = ctypes.create_unicode_buffer(buffer_len.value)
            QueryFullProcessImageName = kernel32_local.QueryFullProcessImageNameW
            if not QueryFullProcessImageName(hProcess, 0, exe_path_buffer, ctypes.byref(buffer_len)):
                return False
            exe_name = exe_path_buffer.value.split('\\')[-1].lower()
            return exe_name == 'cs2.exe'
        finally:
            kernel32_local.CloseHandle(hProcess)
    kernel32 = ctypes.windll.kernel32

    def get_entity(self, base, idx, local_ctrl=None):
        array_idx = (idx & 32767) >> 9
        entity_addr = self.read(base + 8 * array_idx + 16, 'long')
        if not entity_addr:
            return 0
        ctrl = self.read(entity_addr + 112 * (idx & 511), 'long')
        if not ctrl:
            return 0
        if local_ctrl is None:
            local_ctrl = self.read(self.local_player_controller, 'long')
        return ctrl if ctrl != local_ctrl else 0

    def read_bone_pos(self, pawn, idx):
        scene = self.read(pawn + self.o.m_pGameSceneNode, 'long')
        if not scene:
            return None
        bones = self.read(scene + self.o.m_pBoneArray, 'long')
        if not bones:
            return None
        return self.reader.read_vec3(bones + idx * 32)

    def read_weapon_id(self, pawn):
        w = self.read(pawn + self.o.m_pClippingWeapon, 'long')
        if not w:
            return 0
        return self.read(w + self.o.m_AttributeManager + self.o.m_Item + self.o.m_iItemDefinitionIndex, 'ushort')

    def calc_angle(self, src, dst):
        dx, dy, dz = (dst[0] - src[0], dst[1] - src[1], dst[2] - src[2])
        hyp = self._hypot(dx, dy)
        pitch = -self._degrees(self._atan2(dz, hyp))
        yaw = self._degrees(self._atan2(dy, dx))
        return (pitch, yaw)

    def normalize(self, pitch, yaw):
        if self._isnan(pitch) or self._isnan(yaw):
            return (0.0, 0.0)
        pitch = max(min(pitch, 89.0), -89.0)
        yaw = (yaw + 180.0) % 360.0 - 180.0
        return (pitch, yaw)

    def angle_diff(self, a, b):
        return (a - b + 180) % 360 - 180

    def in_fov(self, pitch1, yaw1, pitch2, yaw2, fov=None):
        dp = self.angle_diff(pitch2, pitch1)
        dy = self.angle_diff(yaw2, yaw1)
        base_fov = float(getattr(self.cfg, 'FOV', 60.0))
        if fov is None:
            fov = base_fov
        try:
            fov = float(fov)
        except Exception:
            fov = base_fov
        return abs(dp) <= fov and abs(dy) <= fov

    def compute_effective_fov(self, base_fov, dist_sq=None):
        try:
            base = float(base_fov)
        except Exception:
            base = float(getattr(self.cfg, 'FOV', 60.0))
        if not bool(getattr(self.cfg, 'dynamic_fov_enabled', False)) or dist_sq is None or dist_sq <= 0:
            try:
                set_current_dynamic_fov(base)
            except Exception:
                pass
            return base
        try:
            d = float(dist_sq)
            if d < 0:
                d = 0.0
            dist = math.sqrt(d)
        except Exception:
            dist = 0.0
        max_dist = float(getattr(self.cfg, 'dynamic_fov_max_distance', 3000.0))
        if max_dist <= 0.0:
            max_dist = 3000.0
        t = max(0.0, min(dist / max_dist, 1.0))
        min_scale = float(getattr(self.cfg, 'dynamic_fov_min_scale', 0.5))
        max_scale = float(getattr(self.cfg, 'dynamic_fov_max_scale', 1.5))
        if max_scale < min_scale:
            max_scale = min_scale
        scale = min_scale + (max_scale - min_scale) * t
        eff = base * scale
        try:
            set_current_dynamic_fov(eff)
        except Exception:
            pass
        return eff

    @staticmethod
    def lerp(a, b, t):
        return a + (b - a) * t

    def clamp_angle_diff(self, current, target, max_delta=MAX_DELTA_ANGLE):
        d = self.angle_diff(target, current)
        if abs(d) > max_delta:
            d = max_delta if d > 0 else -max_delta
        return current + d

    def get_current_bone_index(self, pawn, my_pos, pitch, yaw, frame_time=1.0 / 60.0):
        if not pawn or not my_pos:
            return self.bone_indices.get('head', 6)
        if not bool(getattr(self.cfg, 'closest_to_crosshair', False)):
            name = str(getattr(self.cfg, 'target_bone_name', 'head')).lower().strip()
            if name in self.bone_indices:
                return self.bone_indices[name]
            bone_names = getattr(self.cfg, 'aim_bones', ['head'])
            if bone_names:
                first = str(bone_names[0]).lower().strip()
                if first in self.bone_indices:
                    return self.bone_indices[first]
            return self.bone_indices.get('head', 6)
        bone_names = getattr(self.cfg, 'aim_bones', ['head'])
        bone_ids = [self.bone_indices[b] for b in bone_names if b in self.bone_indices]
        if not bone_ids:
            return self.bone_indices.get('head', 6)
        best_bone = None
        best_delta = float('inf')
        vel = self.read_vec3(pawn + self.o.m_vecVelocity) if getattr(self.cfg, 'enable_velocity_prediction', False) else None
        for bone in bone_ids:
            pos = self.read_bone_pos(pawn, bone)
            if not pos:
                continue
            if vel:
                factor = float(getattr(self.cfg, 'velocity_prediction_factor', 1.0))
                pos = [pos[i] + vel[i] * frame_time * factor for i in range(3)]
            pos[2] -= float(getattr(self.cfg, 'downward_offset', 0.0))
            p, y = self.calc_angle(my_pos, pos)
            if math.isnan(p) or math.isnan(y):
                continue
            delta = math.hypot(self.angle_diff(p, pitch), self.angle_diff(y, yaw))
            if delta < best_delta:
                best_delta = delta
                best_bone = bone
        return best_bone if best_bone is not None else self.bone_indices.get('head', 6)

    def is_target_visible(self, local_pos, target_pos):
        """Aimbot visibility check using the shared ESP vischecker but
        without the per-frame vischeck budget that ESP uses.

        This keeps ESP colours stable while still preventing the aimbot
        from locking targets that are genuinely behind walls.
        """
        # If vischeck is disabled or misconfigured, fail open (treat as visible)
        # so the aimbot still functions.
        if (not ESP_VISCHECK_AVAILABLE) or (not getattr(self.cfg, 'visibility_aim_enabled', True)):
            return True
        if (local_pos is None) or (target_pos is None):
            return True

        # Reuse the same vischecker instance that ESP uses.
        try:
            from Features import esp as esp_module
        except Exception:
            self.use_esp_vischeck = False
            return True

        try:
            vc = getattr(esp_module, 'vis_checker', None)
        except Exception:
            vc = None

        if not vc:
            return True

        self.vis_checker = vc

        # If vischecker reports that no map is loaded, don't gate aimbot.
        try:
            if (not hasattr(self.vis_checker, 'is_map_loaded')) or (not self.vis_checker.is_map_loaded()):
                return True
        except Exception:
            return True

        # Perform a direct vischeck ray from our eye position to the target.
        try:
            eye_offset = 64.0
            lx, ly, lz = float(local_pos[0]), float(local_pos[1]), float(local_pos[2]) + eye_offset
            tx, ty, tz = float(target_pos[0]), float(target_pos[1]), float(target_pos[2]) + eye_offset
        except Exception:
            return True

        try:
            is_visible = None
            if hasattr(self.vis_checker, 'is_visible'):
                is_visible = self.vis_checker.is_visible((lx, ly, lz), (tx, ty, tz))
            elif hasattr(self.vis_checker, 'trace'):
                dx, dy, dz = (tx - lx), (ty - ly), (tz - lz)
                is_visible = self.vis_checker.trace(lx, ly, lz, dx, dy, dz)
            if is_visible is None:
                return True
            return bool(is_visible)
        except Exception:
            # Any failure in the vischecker should not hard-disable the aimbot.
            return True
    def run(self):
        from ctypes import windll
        GetAsyncKeyState = windll.user32.GetAsyncKeyState
        o, base, cfg = (self.o, self.base, self.cfg)
        last_aim_key = None
        aim_vk = None
        fps = int(getattr(cfg, 'aim_tick_rate', 60))
        frame_time = 1.0 / max(30, min(240, fps))
        cache_rate = float(getattr(cfg, 'entity_cache_refresh', 0.2))
        last_cache = 0.0
        entity_cache, prev_weapon = ({}, None)
        enable_vel_pred = bool(getattr(cfg, 'enable_velocity_prediction', False))
        vel_factor = float(getattr(cfg, 'velocity_prediction_factor', 1.0))
        downward_offset = float(getattr(cfg, 'downward_offset', 0.0))
        stickiness_time = float(getattr(cfg, 'stickiness_time', 0.18))
        smooth_ramp_speed = float(getattr(cfg, 'smooth_ramp_speed', 1.45))
        max_entities = int(getattr(cfg, 'max_entities', 64))

        def sq_dist(a, b):
            return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

        def valid(pawn, team):
            if not pawn:
                return False
            h = self.read(pawn + o.m_iHealth)
            if not h or h <= 0 or self.read(pawn + o.m_lifeState) != 256:
                return False
            if self.read(pawn + o.m_bDormant, 'int'):
                return False
            t = self.read(pawn + o.m_iTeamNum)
            shoot_mates = bool(getattr(cfg, 'shoot_teammates', False))
            if getattr(cfg, 'DeathMatch', False) or shoot_mates:
                return True
            return t != team
        while not cfg.aim_stop:
            t0 = time.perf_counter()
            dx = dy = 0
            max_mouse_move = int(getattr(cfg, 'max_mouse_move', 35))
            rcs_scale_cfg = float(getattr(cfg, 'rcs_scale', 2.0))
            rcs_enabled = bool(getattr(cfg, 'rcs_enabled', True))
            sens = float(getattr(cfg, 'sensitivity', 0.022))
            invy = float(getattr(cfg, 'invert_y', -1.0))
            angle_deadzone = float(getattr(cfg, 'angle_deadzone', 0.25))
            try:
                cur_aim_key = getattr(cfg, 'aim_key', 'mouse5')
                if cur_aim_key != last_aim_key:
                    last_aim_key = cur_aim_key
                    aim_vk = get_vk_code(cur_aim_key) or get_vk_code('mouse5')
                if aim_vk is None or not self.is_cs2_focused():
                    time.sleep(0.1)
                    continue
                if getattr(cfg, 'menu_open', False):
                    self.left_down = False
                    time.sleep(0.05)
                    continue
                state = GetAsyncKeyState(aim_vk) & 32768 != 0
                if state != self.left_down:
                    self.aim_start_time = time.perf_counter() if state else None
                    self.reset_recoil()
                    self.smooth_ramp = 0.0
                self.left_down = state
                if not (cfg.enabled and getattr(cfg, 'aimbot_enabled', True)):
                    self.left_down = False
                    time.sleep(0.05)
                    continue
                if not self.left_down:
                    time.sleep(0.01)
                    continue
                pawn = self.read(base + o.dwLocalPlayerPawn, 'long')
                if not pawn:
                    time.sleep(0.01)
                    continue
                hp = self.read(pawn + o.m_iHealth)
                if not hp or hp <= 0:
                    time.sleep(0.01)
                    continue
                ctrl = self.read(base + o.dwLocalPlayerController, 'long')
                my_team = self.read(pawn + o.m_iTeamNum)
                my_pos = self.read_vec3(pawn + o.m_vOldOrigin)
                view = self.reader.read_bytes(base + o.dwViewAngles, 8)
                pitch, yaw = struct.unpack('ff', view) if view else (0.0, 0.0)
                punch_bytes = self.reader.read_bytes(pawn + o.m_aimPunchAngle, 8)
                if punch_bytes and len(punch_bytes) >= 8:
                    rp, ry = struct.unpack('ff', punch_bytes)
                else:
                    rp = ry = 0.0
                now = time.time()
                if now - last_cache > cache_rate:
                    last_cache = now
                    entity_cache.clear()
                    try:
                        entities = get_entities(self.process_handle, base)
                    except Exception:
                        entities = []
                    for ent in entities:
                        pawn_addr = getattr(ent, 'pawn', 0)
                        if not pawn_addr:
                            continue
                        if not valid(pawn_addr, my_team):
                            continue
                        entity_cache[pawn_addr] = ent
                if not entity_cache:
                    time.sleep(0.01)
                    continue
                target = pos = None
                if self.target_key in entity_cache:
                    ent = entity_cache[self.target_key]
                    tpawn = getattr(ent, 'pawn', self.target_key)
                    b = self.get_current_bone_index(tpawn, my_pos, pitch, yaw, frame_time)
                    p = self.read_bone_pos(tpawn, b) or self.read_vec3(tpawn + o.m_vOldOrigin)
                    v = self.read_vec3(tpawn + self.o.m_vecVelocity) if enable_vel_pred else [0, 0, 0]
                    pred = [p[i] + v[i] * frame_time * vel_factor for i in range(3)]
                    pred[2] -= downward_offset
                    tp, ty = self.calc_angle(my_pos, pred)
                    base_fov = float(getattr(self.cfg, 'FOV', 60.0))
                    d_sq = sq_dist(my_pos, pred)
                    eff_fov = self.compute_effective_fov(base_fov, d_sq)
                    if not self.in_fov(pitch, yaw, tp, ty, eff_fov) or not self.is_target_visible(my_pos, pred):
                        self.target_key = None
                    else:
                        target, pos = (tpawn, pred)
                if not target:
                    mind = float('inf')
                    for pawn_addr, ent in entity_cache.items():
                        p = getattr(ent, 'pawn', pawn_addr)
                        if not p:
                            continue
                        b = self.get_current_bone_index(p, my_pos, pitch, yaw, frame_time)
                        pp = self.read_bone_pos(p, b) or self.read_vec3(p + o.m_vOldOrigin)
                        v = self.read_vec3(p + self.o.m_vecVelocity) if enable_vel_pred else [0, 0, 0]
                        pr = [pp[j] + v[j] * frame_time * vel_factor for j in range(3)]
                        pr[2] -= downward_offset
                        tp, ty = self.calc_angle(my_pos, pr)
                        base_fov = float(getattr(self.cfg, 'FOV', 60.0))
                        d = sq_dist(my_pos, pr)
                        eff_fov = self.compute_effective_fov(base_fov, d)
                        if not self.in_fov(pitch, yaw, tp, ty, eff_fov) or not self.is_target_visible(my_pos, pr):
                            continue
                        if d < mind:
                            mind, target, pos, self.target_key = (d, p, pr, pawn_addr)
                if self.target_key != self.prev_target_key:
                    stick_t = stickiness_time
                    if self.prev_target_key and now - getattr(self, 'stickiness_timer', 0) < stick_t and (self.prev_target_key in entity_cache):
                        self.target_key = self.prev_target_key
                    else:
                        self.reset_recoil()
                        self.smooth_ramp = 0.0
                        self.stickiness_timer = now
                    self.prev_target_key = self.target_key
                if self.left_down and target and pos:
                    self.shots_fired += 1
                    tp, ty = self.calc_angle(my_pos, pos)
                    if rcs_enabled:
                        burst = min(self.shots_fired / 3.0, 1.0)
                        scale = rcs_scale_cfg * burst
                        cp, cy = (tp - rp * scale, ty - ry * scale)
                        cp = self.clamp_angle_diff(pitch, cp, 5.0)
                        cy = self.clamp_angle_diff(yaw, cy, 5.0)
                    else:
                        cp, cy = (tp, ty)
                    if abs(self.angle_diff(cp, pitch)) < angle_deadzone and abs(self.angle_diff(cy, yaw)) < angle_deadzone:
                        self.last_aim_angle = (pitch, yaw)
                        continue
                    base_smoothing = min(0.14, 0.065 + self.shots_fired * 0.0013)
                    self.smooth_ramp = min(1.0, self.smooth_ramp + frame_time * smooth_ramp_speed)
                    ramp = self.ease_in_out_quad(self.smooth_ramp)
                    smooth = max(0.01, base_smoothing * (0.55 + 0.45 * ramp))
                    t = self.ease_out_cubic(min(1.0, smooth * 1.12))
                    sp, sy = self.normalize(self.lerp(pitch, cp, t), self.lerp(yaw, cy, t))
                    raw_dx = -(sy - yaw) / sens
                    raw_dy = -((sp - pitch) / sens) * invy
                    mv = max_mouse_move
                    dx = max(-mv, min(mv, raw_dx))
                    dy = max(-mv, min(mv, raw_dy))
                    dx, dy = (int(round(dx)), int(round(dy)))
                    if -1 <= dx <= 1 and -1 <= dy <= 1:
                        dx = dy = 0
                    self.last_aim_angle = (sp, sy)
                else:
                    self.reset_recoil()
                if dx or dy:
                    move_mouse(dx, dy)
            except Exception:
                time.sleep(0.05)
            elapsed = time.perf_counter() - t0
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)

def start_aim_rcs(cfg):
    aimbot = AimbotRCS(cfg)
    aimbot.run()
if __name__ == '__main__':
    start_aim_rcs(Config)