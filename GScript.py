from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
DEBUG_LOGGING = False
import logging, os
logger = logging.getLogger(__name__)
if DEBUG_LOGGING and (not logger.handlers):
    os.makedirs('logs', exist_ok=True)
    log_path = os.path.join('logs', f"{__name__.replace('.', '_')}.log")
    handler = logging.FileHandler(log_path, encoding='utf-8')
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
import time, ctypes, threading, sys, json, traceback, subprocess, math

# Early, minimal import for overlay style. Heavy feature modules are
# imported lazily later so the CS2 waiting overlay can appear quickly.
try:
    from Process.helpers import Overlay as HelpersOverlay
except Exception as e:
    HelpersOverlay = None
    if DEBUG_LOGGING:
        try:
            logger.debug(f'[Main] Early HelpersOverlay import error: {e}')
            traceback.print_exc()
        except Exception:
            pass

# Heavy modules (ESP, aimbot, config, etc.) are loaded on demand.
esp = None
AimbotRCS = None
bhop = None
TriggerBot = None
RadarApp = None
Config = None
_main_get_offsets = None
set_global_offsets = None
VIRTUAL_KEYS = None

def _lazy_import_features():
    """Import heavy feature modules the first time we actually need them.

    This keeps initial startup light so the 'waiting for CS2' overlay can show
    as early as possible, instead of blocking on large imports.
    """
    global esp, AimbotRCS, bhop, TriggerBot, RadarApp, Config
    global _main_get_offsets, set_global_offsets, VIRTUAL_KEYS, HelpersOverlay, _VK_NAME_FROM_CODE
    if esp is not None and Config is not None:
        return
    try:
        import Features.esp as _esp
        from Features.aimbot import AimbotRCS as _AimbotRCS
        import Features.bhop as _bhop
        from Features.triggerbot import TriggerBot as _TriggerBot
        from Features.radar import RadarApp as _RadarApp
        from Process.config import Config as _Config
        from Process.offset_manager import get_offsets as _get_offsets
        from Process.helpers import set_global_offsets as _set_global_offsets, Overlay as _HelpersOverlay, VIRTUAL_KEYS as _VIRTUAL_KEYS
    except Exception as e:
        if DEBUG_LOGGING:
            try:
                logger.debug(f'[Main] Import error during _lazy_import_features: {e}')
                traceback.print_exc()
            except Exception:
                pass
        sys.exit(1)
    esp = _esp
    AimbotRCS = _AimbotRCS
    bhop = _bhop
    TriggerBot = _TriggerBot
    RadarApp = _RadarApp
    Config = _Config
    _main_get_offsets = _get_offsets
    set_global_offsets = _set_global_offsets
    VIRTUAL_KEYS = _VIRTUAL_KEYS
    HelpersOverlay = _HelpersOverlay
    # Rebuild VK name lookup now that VIRTUAL_KEYS has been imported.
    try:
        _VK_NAME_FROM_CODE = {code: name for name, code in VIRTUAL_KEYS.items()}
    except Exception:
        _VK_NAME_FROM_CODE = {}


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
COLOR_PRESETS = [(255, 0, 0), (0, 128, 255), (0, 255, 0), (255, 255, 0), (255, 255, 255), (255, 0, 255), (0, 255, 255)]
# -----------------------------
# Menu theme / style constants
# -----------------------------

def _clamp255(v: int) -> int:
    try:
        return 0 if v < 0 else 255 if v > 255 else int(v)
    except Exception:
        return 255

def _colorref(rgb):
    """Convert an (r,g,b) tuple into a Win32 COLORREF (0x00bbggrr)."""
    try:
        r, g, b = rgb
    except Exception:
        r, g, b = (255, 255, 255)
    r = _clamp255(r); g = _clamp255(g); b = _clamp255(b)
    return (b << 16) | (g << 8) | r

THEME = {
    # Surfaces
    'bg': (12, 12, 16),
    'panel': (18, 18, 24),
    'panel_2': (22, 22, 30),
    'header': (26, 26, 36),
    'footer': (16, 16, 22),

    # Lines / accents
    'border': (70, 70, 95),
    'divider': (28, 28, 40),
    'accent': (180, 40, 40),
    'accent_2': (200, 70, 70),

    # States
    'hover': (50, 50, 70),
    'active': (62, 62, 92),

    # Text (use COLORREF via _colorref)
    'text': (245, 245, 245),
    'muted': (175, 175, 190),
    'dim': (140, 140, 155),
    'good': (70, 220, 120),
    'warn': (235, 200, 90),
}

def _draw_shadow(ov, x: int, y: int, w: int, h: int, *, layers: int = 3):
    """Fake a soft shadow with a few offset rectangles."""
    try:
        # Dark -> lighter as we approach the panel
        for i in range(layers, 0, -1):
            off = i
            shade = 6 + (layers - i) * 3
            ov.draw_filled_rect(x + off, y + off, w, h, (shade, shade, shade))
    except Exception:
        pass


def is_cs2_running() -> bool:
    """Return True if a cs2.exe process is currently running.

    This uses the built-in Windows *tasklist* command so we do not introduce
    any new Python dependencies.
    """
    if os.name != 'nt':
        return False
    try:
        out = subprocess.check_output(
            ['tasklist', '/FI', 'IMAGENAME eq cs2.exe'],
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return b'cs2.exe' in out.lower()
    except Exception:
        return False


def _wait_for_cs2_with_overlay():
    """Block startup until cs2.exe is running, showing a small overlay.

    The overlay is styled similarly to the main menu so the user can see that
    GScript is waiting for CS2 to be launched instead of silently doing nothing.
    """
    # If the early overlay import failed, fall back to a headless wait.
    if HelpersOverlay is None:
        while True:
            try:
                if is_cs2_running():
                    return
            except Exception:
                return
            time.sleep(1.0)

    try:
        ov = HelpersOverlay()
        try:
            ov.init('GScript - Waiting for CS2')
        except Exception:
            raise
    except Exception as e:
        if DEBUG_LOGGING:
            try:
                logger.debug(f'[Main] Failed to create waiting overlay: {e}')
            except Exception:
                pass
        while True:
            try:
                if is_cs2_running():
                    return
            except Exception:
                return
            time.sleep(1.0)

    box_w, box_h = 460, 150
    x = (ov.width - box_w) // 2
    y = (ov.height - box_h) // 3

    title = 'GScript | Made by Cr0mb'
    subtitle = 'Waiting for CS2 to be opened'
    tip = 'Launch CS2 — this window will close automatically.'

    target_fps = max(30, min(getattr(ov, 'fps', 144), 144))
    delay = 1.0 / float(target_fps)

    while True:
        try:
            if is_cs2_running():
                break
        except Exception:
            break

        if not _orig_begin(ov):
            time.sleep(0.05)
            continue

        try:
            # Animated dots '...'
            dots = '.' * (int(time.time() * 2.0) % 4)

            # Shadow + panel
            _draw_shadow(ov, x, y, box_w, box_h, layers=3)
            ov.draw_filled_rect(x, y, box_w, box_h, THEME['panel'])
            ov.draw_box(x, y, box_w, box_h, THEME['border'])

            # Header strip + accent
            header_h = 34
            ov.draw_filled_rect(x, y, box_w, header_h, THEME['header'])
            ov.draw_filled_rect(x, y + header_h - 2, box_w, 2, THEME['accent'])

            # Title/subtitle
            ov.draw_text(x + 12, y + 22, title, THEME['text'])
            line = f'{subtitle}{dots}'
            ov.draw_text(x + 12, y + 52, line, THEME['muted'])
            ov.draw_text(x + 12, y + 74, tip, THEME['dim'])

            # Subtle progress bar shimmer
            bar_x, bar_y, bar_w, bar_h = x + 12, y + box_h - 34, box_w - 24, 8
            ov.draw_filled_rect(bar_x, bar_y, bar_w, bar_h, (28, 28, 40))
            # moving highlight
            t = (time.time() * 220.0) % (bar_w + 80.0)
            hx = int(bar_x + t) - 80
            start = max(bar_x, hx)
            end = min(bar_x + bar_w, hx + 80)
            hw = max(0, int(end - start))
            if hw:
                ov.draw_filled_rect(int(start), bar_y, hw, bar_h, THEME['accent_2'])
            ov.draw_box(bar_x, bar_y, bar_w, bar_h, THEME['divider'])
        except Exception as e:
            if DEBUG_LOGGING:
                try:
                    logger.debug(f'[Main] Waiting overlay draw error: {e}')
                    traceback.print_exc()
                except Exception:
                    pass

        try:
            _orig_end(ov)
        except Exception:
            pass

        time.sleep(delay)

    # Once CS2 has been detected, hide the temporary overlay window.
    try:
        import win32gui, win32con  # type: ignore
        if getattr(ov, 'hwnd', None):
            win32gui.ShowWindow(ov.hwnd, win32con.SW_HIDE)
            try:
                win32gui.DestroyWindow(ov.hwnd)
            except Exception:
                pass
    except Exception:
        pass

CONFIG_FILE_PATH = None
_cfg_status = ''
_cfg_status_time = 0.0

# Crash / restart status for menu
crash_status_text = ''
crash_status_time = 0.0


def _set_crash_status(msg: str):
    """Update crash/restart status text used by the menu."""
    global crash_status_text, crash_status_time
    crash_status_text = str(msg)
    crash_status_time = time.time()
    if DEBUG_LOGGING:
        try:
            logger.debug(f'[Main] [CrashStatus] {crash_status_text}')
        except Exception:
            pass


def _init_config_path():
    global CONFIG_FILE_PATH
    if CONFIG_FILE_PATH:
        return CONFIG_FILE_PATH

    # Prefer: %APPDATA%\GScript\gscript_config.json
    try:
        appdata = os.environ.get("APPDATA") or ""
        if appdata:
            gscript_dir = os.path.join(appdata, "GScript")
            os.makedirs(gscript_dir, exist_ok=True)
            CONFIG_FILE_PATH = os.path.join(gscript_dir, "gscript_config.json")
            return CONFIG_FILE_PATH
    except Exception:
        pass

    # Fallback (non-Windows / weird env)
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = os.getcwd()
    CONFIG_FILE_PATH = os.path.join(base, "gscript_config.json")
    return CONFIG_FILE_PATH


def _init_config_path():
    global CONFIG_FILE_PATH
    if CONFIG_FILE_PATH:
        return CONFIG_FILE_PATH

    # Prefer: %APPDATA%\GScript\gscript_config.json
    try:
        appdata = os.environ.get("APPDATA") or ""
        if appdata:
            gscript_dir = os.path.join(appdata, "GScript")
            os.makedirs(gscript_dir, exist_ok=True)
            CONFIG_FILE_PATH = os.path.join(gscript_dir, "gscript_config.json")
            return CONFIG_FILE_PATH
    except Exception:
        pass

    # Fallback (non-Windows / weird env)
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = os.getcwd()
    CONFIG_FILE_PATH = os.path.join(base, "gscript_config.json")
    return CONFIG_FILE_PATH


def _set_cfg_status(msg: str):
    global _cfg_status, _cfg_status_time
    _cfg_status = str(msg)
    _cfg_status_time = time.time()


def _iter_menu_fields():
    fields = []
    try:
        for _, items in TABS:
            for _label, key, kind in items:
                if kind in ('bool', 'float', 'select', 'key', 'color'):
                    fields.append((key, kind))
    except Exception:
        pass
    return fields


def save_menu_config():
    path = _init_config_path()
    try:
        data = {}
        for key, kind in _iter_menu_fields():
            try:
                data[key] = getattr(Config, key)
            except Exception:
                pass
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        _set_cfg_status('Config saved')
        if DEBUG_LOGGING:
            logger.debug(f'[Main] Config saved to {path}')
    except Exception as e:
        if DEBUG_LOGGING:
            logger.debug(f'[Main] Failed to save config: {e}')
        _set_cfg_status('Save failed')

def load_menu_config():
    path = _init_config_path()
    try:
        if not os.path.exists(path):
            _set_cfg_status('No config file')
            if DEBUG_LOGGING:
                logger.debug(f'[Main] No config file found at {path}')
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        if DEBUG_LOGGING:
            logger.debug(f'[Main] Failed to load config: {e}')
        _set_cfg_status('Load failed')
        return
    kinds = {key: kind for key, kind in _iter_menu_fields()}
    for key, value in data.items():
        kind = kinds.get(key)
        if not kind:
            continue
        try:
            if kind == 'bool':
                setattr(Config, key, bool(value))
            elif kind == 'float':
                setattr(Config, key, float(value))
            else:
                setattr(Config, key, value)
        except Exception:
            continue
    _set_cfg_status('Config loaded')

def reset_menu_config():
    try:
        defaults = {}
        for name, value in Config.__dict__.items():
            if name.startswith('_'):
                continue
            if isinstance(value, (bool, int, float, str, tuple, list)):
                defaults[name] = value
        for name, value in defaults.items():
            try:
                setattr(Config, name, value)
            except Exception:
                continue
        _set_cfg_status('Config reset')
        if DEBUG_LOGGING:
            logger.debug('[Main] Config reset to defaults from Config class.')
    except Exception as e:
        if DEBUG_LOGGING:
            logger.debug(f'[Main] Failed to reset config: {e}')
        _set_cfg_status('Reset failed')

VK_INSERT = 45
VK_LBUTTON = 1
VK_SHIFT = 0x10
VK_CONTROL = 0x11
_prev_mouse_down = False
_prev_mouse_down_press = False
_suppress_next_click = False

def key_down(vk: int) -> bool:
    """Return True while the key is held down."""
    try:
        return (user32.GetAsyncKeyState(vk) & 32768) != 0
    except Exception:
        return False

def mouse_just_pressed() -> bool:
    """Return True only on the transition from mouse up -> mouse down."""
    global _prev_mouse_down_press
    down = mouse_down()
    jp = down and (not _prev_mouse_down_press)
    _prev_mouse_down_press = down
    return jp
try:
    _VK_NAME_FROM_CODE = {code: name for name, code in VIRTUAL_KEYS.items()}
except Exception:
    _VK_NAME_FROM_CODE = {}

def vk_to_key_name(vk: int) -> str:
    name = _VK_NAME_FROM_CODE.get(vk)
    if name:
        return name
    if 48 <= vk <= 57 or 65 <= vk <= 90:
        return chr(vk).lower()
    if 112 <= vk <= 123:
        return f'f{vk - 111}'
    if vk == 37:
        return 'left'
    if vk == 38:
        return 'up'
    if vk == 39:
        return 'right'
    if vk == 40:
        return 'down'
    return f'vk_{vk}'

def mouse_clicked():
    global _prev_mouse_down, _suppress_next_click
    down = user32.GetAsyncKeyState(VK_LBUTTON) & 32768 != 0
    clicked = not down and _prev_mouse_down
    if _suppress_next_click and clicked:
        clicked = False
        _suppress_next_click = False
    _prev_mouse_down = down
    return clicked

def mouse_down():
    return user32.GetAsyncKeyState(VK_LBUTTON) & 32768 != 0

def pressed(vk):
    return user32.GetAsyncKeyState(vk) & 1 != 0

def get_mouse_pos():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

TABS = [
    (
        "Aimbot",
        [
            ("Aimbot Enabled", "aimbot_enabled", "bool"),
            ("RCS Enabled", "rcs_enabled", "bool"),
            ("Dynamic FOV (player)", "dynamic_fov_enabled", "bool"),
            ("Closest To Cross", "closest_to_crosshair", "bool"),
            ("Shoot Teammates", "shoot_teammates", "bool"),
            ("Draw Aimbot FOV", "draw_aimbot_fov", "bool"),

            ("Aim Key", "aim_key", "key"),
            ("Field of View", "FOV", "float"),
            ("Recoil Scale", "rcs_scale", "float"),
            ("Aim Smoothness", "max_mouse_move", "float"),
            ("Aim Bone", "target_bone_name", "select"),
        ],
    ),

    (
        "Player ESP",
        [
            ("Box ESP", "box_esp_enabled", "bool"),
            ("HP Bar", "hp_bar_enabled", "bool"),
            ("Skeleton ESP", "skeleton_esp_enabled", "bool"),
            ("Name ESP", "name_esp_enabled", "bool"),
            ("Weapon ESP", "weapon_esp_enabled", "bool"),
            ("Money ESP", "money_esp_enabled", "bool"),
            ("Flash ESP", "flash_esp_enabled", "bool"),
            ("Scope ESP", "scope_esp_enabled", "bool"),
            ("Visible Only ESP", "visible_only_esp", "bool"),
            ("Show T Team", "esp_show_t", "bool"),
            ("Show CT Team", "esp_show_ct", "bool"),
        ],
    ),

    (
        "World ESP",
        [
            ("Map Status", "map_status_enabled", "bool"),
            ("Team List", "team_list_enabled", "bool"),
            ("Spectator List", "spectator_list_enabled", "bool"),
            ("External Crosshair", "crosshair_enabled", "bool"),
            ("Crosshair Size", "crosshair_size", "int"),
            ("Crosshair Thickness", "crosshair_thickness", "int"),
            ("Draw FPS Overlay", "esp_draw_fps", "bool"),
            ("Hide From Screen Capture", "hide_esp_from_capture", "bool"),
        ],
    ),

    (
        "TriggerBot",
        [
            ("TriggerBot Enabled", "triggerbot_enabled", "bool"),
            ("Trigger Key", "trigger_key", "key"),
            ("Always On", "triggerbot_always_on", "bool"),
            ("Shoot Teammates", "shoot_teammates", "bool"),
            ("Cooldown (s)", "triggerbot_cooldown", "float"),
        ],
    ),

    (
        "Misc",
        [
            ("BHop", "bhop_enabled", "bool"),
            ("Radar Enabled", "radar_enabled", "bool"),
            ("Radar FPS", "radar_fps", "float"),
        ],
    ),

    (
        "System",
        [
            ("ESP VisCheck", "visibility_esp_enabled", "bool"),
            ("Aim VisCheck", "visibility_aim_enabled", "bool"),
            ("Current Map", "current_map_display", "map"),

            ("Save Config", "save_config", "action"),
            ("Load Config", "load_config", "action"),
            ("Reset Config", "reset_config", "action"),

            ("Panic Key", "panic_key", "key"),
        ],
    ),

    (
        "Colors",
        [
            ("T Color", "color_t", "color"),
            ("CT Color", "color_ct", "color"),
            ("Spectator Color", "color_spectators", "color"),

            ("Name T Color", "color_name_t", "color"),
            ("Name CT Color", "color_name_ct", "color"),

            ("Skeleton T Color", "color_skeleton_t", "color"),
            ("Skeleton CT Color", "color_skeleton_ct", "color"),

            ("Skeleton T Visible", "color_skeleton_t_visible", "color"),
            ("Skeleton T Occluded", "color_skeleton_t_invisible", "color"),

            ("Skeleton CT Visible", "color_skeleton_ct_visible", "color"),
            ("Skeleton CT Occluded", "color_skeleton_ct_invisible", "color"),

            ("T Visible Color", "color_vis_t_visible", "color"),
            ("T Occluded Color", "color_vis_t_invisible", "color"),

            ("CT Visible Color", "color_vis_ct_visible", "color"),
            ("CT Occluded Color", "color_vis_ct_invisible", "color"),

            ("Weapon Text", "color_weapon_text", "color"),
            ("Money Text", "color_money_text", "color"),
            ("Flash Indicator", "color_flash_indicator", "color"),
            ("Scope Indicator", "color_scope_indicator", "color"),
            ("Crosshair", "crosshair_color", "color"),
        ],
    ),
]
menu_open = bool(getattr(Config, 'menu_open', True))
active_tab = 0
hover_index = None
sidebar_hover = None
menu_x, menu_y = (40, 60)
MENU_W, MENU_H = 560, 480  # keep drawing + input hitboxes consistent
dragging = False
drag_off_x = drag_off_y = 0
slider_drag = None
key_listen_target = None
# Per-tab scroll offset for tall content (currently used for Colors tab)
colors_scroll_offset = 0.0
scroll_drag = None


# Slider behavior tuning (min/max/step/format) for float fields.
# If a key is not present, a conservative auto-range is derived from its current value.
SLIDER_SPECS = {
    # Aimbot
    'FOV':                {'min': 1.0,  'max': 300.0, 'step': 1.0,   'fmt': '{:.0f}'},
    'rcs_scale':          {'min': 0.0,  'max': 5.0,   'step': 0.05,  'fmt': '{:.2f}'},
    'max_mouse_move':     {'min': 0.1,  'max': 50.0,  'step': 0.1,   'fmt': '{:.1f}'},
    # TriggerBot
    'triggerbot_cooldown':{'min': 0.0,  'max': 1.5,   'step': 0.01,  'fmt': '{:.2f}'},
    # Misc
    'radar_fps':          {'min': 5.0,  'max': 240.0, 'step': 1.0,   'fmt': '{:.0f}'},
    # Crosshair
    'crosshair_size':     {'min': 1.0,  'max': 50.0,  'step': 1.0,   'fmt': '{:.0f}'},
    'crosshair_thickness':{'min': 1.0,  'max': 10.0,  'step': 1.0,   'fmt': '{:.0f}'},
}

def _get_slider_spec(key: str, current: float):
    spec = SLIDER_SPECS.get(key)
    if spec:
        return float(spec['min']), float(spec['max']), float(spec['step']), str(spec.get('fmt', '{:.2f}'))
    # Auto-range: keep it sensible and stable.
    cur = float(current or 0.0)
    mn = 0.0
    mx = max(10.0, abs(cur) * 2.0)
    # If value is tiny, widen a bit so the slider isn't stuck.
    if mx < 5.0:
        mx = 5.0
    step = max(0.01, (mx - mn) / 200.0)
    return mn, mx, step, '{:.2f}'

def _clamp(v: float, mn: float, mx: float) -> float:
    return mn if v < mn else (mx if v > mx else v)

def _snap(v: float, step: float) -> float:
    if step <= 0:
        return v
    return round(v / step) * step


def exit_program():
    try:
        if hasattr(esp, 'shutdown'):
            esp.shutdown()
    except Exception:
        pass
    sys.exit(0)


def handle_menu():
    global menu_open, active_tab, hover_index, sidebar_hover
    global menu_x, menu_y, dragging, drag_off_x, drag_off_y
    global slider_drag, key_listen_target
    global colors_scroll_offset, scroll_drag

    # Toggle menu with INSERT
    if pressed(VK_INSERT):
        menu_open = not menu_open
        try:
            setattr(Config, 'menu_open', bool(menu_open))
        except Exception:
            pass
        user32.ShowCursor(menu_open)

    if not menu_open:
        return

    mx, my = get_mouse_pos()
    x, y = (menu_x, menu_y)
    w, h = (MENU_W, MENU_H)
    sidebar_w = 140
    row_h = 24
    header_h = 36
    footer_h = 44  # keep in sync with draw_menu()

    # Drag window by header
    if x < mx < x + w and y < my < y + header_h:
        if mouse_down() and (not dragging):
            dragging = True
            drag_off_x = mx - x
            drag_off_y = my - y
    if dragging:
        if mouse_down():
            menu_x = mx - drag_off_x
            menu_y = my - drag_off_y
            return
        else:
            dragging = False

    hover_index = None
    sidebar_hover = None

    # Sidebar tab clicks
    for i, _ in enumerate(TABS):
        ty = y + header_h + 12 + i * row_h
        if x + 8 < mx < x + sidebar_w - 8 and ty < my < ty + row_h:
            sidebar_hover = i
            if mouse_clicked():
                active_tab = i
                hover_index = None
                colors_scroll_offset = 0.0
            return

    # Tab item interactions
    items = TABS[active_tab][1]

    # IMPORTANT: keep input hitboxes aligned with draw_menu() layout.
    # draw_menu() uses:
    #   content_y = y + header_h + 10
    #   list_y    = content_y + 34
    #   iy        = list_y + i * row_h
    content_x = x + sidebar_w + 10
    content_y = y + header_h + 10
    content_w = w - sidebar_w - 20
    list_y = content_y + 34

    visible_top = list_y
    visible_bottom = y + h - footer_h - 10
    visible_h = max(0, visible_bottom - visible_top)
    tab_name = TABS[active_tab][0]
    use_scroll = False
    scroll_offset = 0.0
    max_offset = 0.0
    total_h = len(items) * row_h
    if tab_name == "Colors" and visible_h > 0 and total_h > visible_h:
        use_scroll = True
        max_offset = max(0, total_h - visible_h)
        # Clamp and apply scroll offset
        try:
            off = float(colors_scroll_offset)
        except Exception:
            off = 0.0
        if off < 0.0:
            off = 0.0
        elif off > float(max_offset):
            off = float(max_offset)
        colors_scroll_offset = off
        scroll_offset = off
        list_y = list_y - int(scroll_offset)
        visible_top = content_y + 34
        visible_bottom = visible_top + visible_h

    # Effective clickable width for items (avoid hitting the scrollbar area on the right)
    click_max_x = content_x + content_w
    if use_scroll and tab_name == "Colors":
        # Leave a margin on the right where the scrollbar lives
        click_max_x = content_x + content_w - 18

    for i, (_, key, kind) in enumerate(items):
        iy = list_y + i * row_h
        if use_scroll:
            if iy + row_h < visible_top or iy > visible_bottom:
                continue
        if content_x < mx < click_max_x and iy < my < iy + row_h:
            hover_index = i

            if kind == 'bool' and mouse_clicked():
                current = bool(getattr(Config, key, False))
                new_val = not current
                setattr(Config, key, new_val)

            if kind == 'color' and mouse_clicked():
                col_val = getattr(Config, key, (255, 255, 255))
                try:
                    r, g, b = col_val
                except Exception:
                    r, g, b = (255, 255, 255)
                r = max(0, min(255, int(r)))
                g = max(0, min(255, int(g)))
                b = max(0, min(255, int(b)))
                presets = COLOR_PRESETS
                current = (r, g, b)
                try:
                    idx = presets.index(current)
                    new_col = presets[(idx + 1) % len(presets)]
                except ValueError:
                    new_col = presets[0]
                setattr(Config, key, new_col)
                _set_cfg_status(f'{key} color updated')

            if kind == 'key' and mouse_clicked():
                key_listen_target = key

            if kind == 'float':
                # Slider: click-to-set + drag handle (hitboxes match draw_menu)
                try:
                    cur = float(getattr(Config, key, 0.0))
                except Exception:
                    cur = 0.0
                mn, mxv, step, fmt = _get_slider_spec(key, cur)

                right_pad = 14
                rx = content_x + content_w - right_pad
                bar_w, bar_h = 160, 8
                bar_x = rx - bar_w
                bar_y = iy + (row_h - bar_h) // 2 + 2

                if (slider_drag is None) and mouse_just_pressed():
                    # Expanded hitbox so it feels easy to grab.
                    if (bar_x - 6) <= mx <= (bar_x + bar_w + 6) and (bar_y - 10) <= my <= (bar_y + bar_h + 10):
                        slider_drag = {
                            'key': key,
                            'mn': mn,
                            'mx': mxv,
                            'step': step,
                            'fmt': fmt,
                            'bar_x': bar_x,
                            'bar_w': bar_w,
                        }
                        # Prevent the release-edge "click" from triggering other controls.
                        try:
                            global _suppress_next_click
                            _suppress_next_click = True
                        except Exception:
                            pass

                        # Set value immediately at press position.
                        t = (mx - bar_x) / float(bar_w or 1)
                        if t < 0.0:
                            t = 0.0
                        elif t > 1.0:
                            t = 1.0
                        raw = mn + t * (mxv - mn)

                        step_mod = step
                        if key_down(VK_SHIFT):
                            step_mod = step_mod / 10.0
                        if key_down(VK_CONTROL):
                            step_mod = step_mod * 10.0

                        new_val = _snap(raw, step_mod)
                        new_val = _clamp(new_val, mn, mxv)
                        try:
                            old_val = float(getattr(Config, key, 0.0))
                        except Exception:
                            old_val = None
                        if old_val is None or abs(old_val - new_val) > 1e-9:
                            setattr(Config, key, float(new_val))

            if kind == 'select' and mouse_clicked():
                options = getattr(Config, 'aim_bones', [])
                if options:
                    current = getattr(Config, key, options[0])
                    try:
                        idx = options.index(str(current))
                    except ValueError:
                        idx = -1
                    new_idx = (idx + 1) % len(options)
                    setattr(Config, key, options[new_idx])

            if kind == 'action' and mouse_clicked():
                if key == 'save_config':
                    save_menu_config()
                elif key == 'load_config':
                    load_menu_config()
                elif key == 'reset_config':
                    reset_menu_config()
            break

    # Scrollbar clicks / drags for tall tabs (Colors)
    if use_scroll and visible_h > 0 and total_h > visible_h:
        scroll_track_x = content_x + content_w - 8
        scroll_track_w = 10
        scroll_track_y = visible_top
        scroll_track_h = visible_h
        if scroll_track_x <= mx <= scroll_track_x + scroll_track_w and scroll_track_y <= my <= scroll_track_y + scroll_track_h:
            thumb_min_h = 12
            thumb_h = max(thumb_min_h, int(visible_h * visible_h / float(total_h)))
            max_thumb_move = max(1, visible_h - thumb_h)
            # Compute current thumb position based on scroll_offset
            if max_offset <= 0:
                thumb_y = scroll_track_y
            else:
                thumb_y = scroll_track_y + int((scroll_offset / float(max_offset)) * max_thumb_move)
            thumb_x0 = scroll_track_x - 3
            thumb_x1 = scroll_track_x + scroll_track_w + 3
            thumb_y0 = thumb_y
            thumb_y1 = thumb_y + thumb_h

            if mouse_clicked():
                # Map click position along the track to a scroll offset (jump).
                click_t = (my - scroll_track_y) / float(scroll_track_h or 1)
                new_offset = click_t * float(max_offset)
                if new_offset < 0.0:
                    new_offset = 0.0
                elif new_offset > float(max_offset):
                    new_offset = float(max_offset)
                colors_scroll_offset = new_offset
            else:
                # Begin drag when pressing inside the thumb.
                if scroll_drag is None and mouse_down() and thumb_x0 <= mx <= thumb_x1 and thumb_y0 <= my <= thumb_y1:
                    scroll_drag = {
                        'start_y': my,
                        'start_offset': colors_scroll_offset,
                        'track_y': scroll_track_y,
                        'track_h': scroll_track_h,
                        'max_offset': max_offset,
                    }


    # Scroll dragging (while left mouse held on thumb)
    if scroll_drag and use_scroll and visible_h > 0 and total_h > visible_h:
        try:
            start_y = float(scroll_drag.get('start_y', my))
            start_offset = float(scroll_drag.get('start_offset', colors_scroll_offset))
            track_y = float(scroll_drag.get('track_y', visible_top))
            track_h = float(scroll_drag.get('track_h', visible_h))
            max_off = float(scroll_drag.get('max_offset', max_offset))
        except Exception:
            start_y = my
            start_offset = colors_scroll_offset
            track_y = visible_top
            track_h = visible_h
            max_off = max_offset
        if mouse_down():
            # Map vertical mouse delta to scroll offset delta.
            dy = my - start_y
            if track_h <= 0:
                new_offset = start_offset
            else:
                new_offset = start_offset + (dy * 2.5 / track_h) * max_off
            if new_offset < 0.0:
                new_offset = 0.0
            elif new_offset > float(max_off):
                new_offset = float(max_off)
            colors_scroll_offset = new_offset
        else:
            scroll_drag = None

    # Slider dragging (absolute position on the bar)
    if slider_drag:
        try:
            key = slider_drag.get('key')
            mn = float(slider_drag.get('mn', 0.0))
            mxv = float(slider_drag.get('mx', 1.0))
            step = float(slider_drag.get('step', 0.01))
            bar_x = int(slider_drag.get('bar_x', 0))
            bar_w = int(slider_drag.get('bar_w', 1))
        except Exception:
            key = None

        mx, _ = get_mouse_pos()
        if (not mouse_down()) or (not key):
            slider_drag = None
        else:
            t = (mx - bar_x) / float(bar_w or 1)
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0

            raw = mn + t * (mxv - mn)

            # Modifiers: Shift = fine, Ctrl = coarse
            step_mod = step
            if key_down(VK_SHIFT):
                step_mod = step_mod / 10.0
            if key_down(VK_CONTROL):
                step_mod = step_mod * 10.0

            new_val = _snap(raw, step_mod)
            new_val = _clamp(new_val, mn, mxv)

            try:
                old_val = float(getattr(Config, key, 0.0))
            except Exception:
                old_val = None

            if old_val is None or abs(old_val - new_val) > 1e-9:
                # Check if this is an integer type config
                if key in ['crosshair_size', 'crosshair_thickness']:
                    setattr(Config, key, int(new_val))
                else:
                    setattr(Config, key, float(new_val))

    # Key listening for keybind fields
    if key_listen_target:
        for vk in range(1, 256):
            if vk == VK_INSERT:
                continue
            state = user32.GetAsyncKeyState(vk)
            if state & 32768:
                key_name = vk_to_key_name(vk)
                setattr(Config, key_listen_target, key_name)
                _suppress_next_click = True
                key_listen_target = None
                break

    # EXIT button (bottom right)
    exit_w, exit_h = (92, 26)
    exit_x = x + w - exit_w - 12
    exit_y = y + h - exit_h - 10
    if exit_x < mx < exit_x + exit_w and exit_y < my < exit_y + exit_h:
        if mouse_clicked():
            exit_program()

def draw_menu(ov):
    global colors_scroll_offset
    if not menu_open:
        return
    try:
        x, y = (menu_x, menu_y)
        w, h = (MENU_W, MENU_H)
        sidebar_w = 140
        row_h = 24
        header_h = 36
        footer_h = 44


        if menu_open:
            # Shadow + base panel
            _draw_shadow(ov, x, y, w, h, layers=3)
            ov.draw_filled_rect(x, y, w, h, THEME['panel'])
            ov.draw_box(x, y, w, h, THEME['border'])

            # Header
            ov.draw_filled_rect(x, y, w, header_h, THEME['header'])
            # Animated accent glow
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(time.time() * 2.2))
            acc = THEME['accent']
            acc2 = (int(acc[0] * pulse), int(acc[1] * pulse), int(acc[2] * pulse))
            ov.draw_filled_rect(x, y + header_h - 2, w, 2, acc2)

            # Title + hint
            title = 'GScript'
            sub = 'INSERT = Toggle | Drag header to move'
            ov.draw_text(x + 12, y + 22, title, THEME['text'])
            ov.draw_text(x + 110, y + 22, sub, THEME['dim'])

            # Sidebar
            ov.draw_filled_rect(x, y + header_h, sidebar_w, h - header_h - footer_h, THEME['panel_2'])
            ov.draw_filled_rect(x + sidebar_w - 1, y + header_h, 1, h - header_h - footer_h, THEME['divider'])

            for i, (tab, _) in enumerate(TABS):
                ty = y + header_h + 12 + i * row_h
                is_active = (i == active_tab)
                is_hover = (sidebar_hover == i)
                if is_active:
                    ov.draw_filled_rect(x + 8, ty, sidebar_w - 16, row_h, THEME['active'])
                    ov.draw_filled_rect(x + 8, ty, 3, row_h, THEME['accent'])
                elif is_hover:
                    ov.draw_filled_rect(x + 8, ty, sidebar_w - 16, row_h, THEME['hover'])

                tab_col = THEME['text'] if is_active else THEME['muted']
                ov.draw_text(x + 16, ty + 18, tab, tab_col)

            # Content area
            content_x = x + sidebar_w + 10
            content_y = y + header_h + 10
            content_w = w - sidebar_w - 20
            content_h = h - header_h - footer_h - 14
            ov.draw_filled_rect(content_x, content_y, content_w, content_h, THEME['bg'])
            ov.draw_box(content_x, content_y, content_w, content_h, THEME['divider'])

            # Tab title
            tab_name = str(TABS[active_tab][0])
            ov.draw_text(content_x + 10, content_y + 22, tab_name, THEME['muted'])
            ov.draw_filled_rect(content_x + 10, content_y + 26, content_w - 20, 1, THEME['divider'])

            # Items
            items = TABS[active_tab][1]
            list_y = content_y + 34

            # Scroll handling for tall tabs (currently Colors).
            visible_top = list_y
            visible_bottom = y + h - footer_h - 10
            visible_h = max(0, visible_bottom - visible_top)
            tab_name = TABS[active_tab][0]
            use_scroll = False
            scroll_offset = 0.0
            max_offset = 0.0
            total_h = len(items) * row_h
            if tab_name == "Colors" and visible_h > 0 and total_h > visible_h:
                use_scroll = True
                max_offset = max(0, total_h - visible_h)
                # Clamp and apply scroll offset
                try:
                    off = float(colors_scroll_offset)
                except Exception:
                    off = 0.0
                if off < 0.0:
                    off = 0.0
                elif off > float(max_offset):
                    off = float(max_offset)
                colors_scroll_offset = off
                scroll_offset = off
                list_y = list_y - int(scroll_offset)
                visible_top = content_y + 34
                visible_bottom = visible_top + visible_h

            def draw_badge(bx, by, bw, bh, text, *, fill=None, border=None, text_col=None):
                """Small pill-style badge used for values, keys, and map labels.

                This keeps the layout consistent across all rows and avoids text being
                clipped by using the badge height for vertical centering.
                """
                if fill is None:
                    fill = THEME['panel_2']
                if border is None:
                    border = THEME['divider']
                if text_col is None:
                    text_col = THEME['text']
                # Base pill
                ov.draw_filled_rect(bx, by, bw, bh, fill)
                ov.draw_box(bx, by, bw, bh, border)
                # Vertically center text using the badge height instead of a fixed offset.
                text_y = by + (bh // 2) + 4
                ov.draw_text(bx + 8, text_y, text, text_col)

            for i, (label, key, kind) in enumerate(items):
                iy = list_y + i * row_h
                if use_scroll:
                    # Skip rows that are completely outside the visible area.
                    if iy + row_h < visible_top or iy > visible_bottom:
                        continue
                # hover row
                if i == hover_index:
                    ov.draw_filled_rect(content_x + 6, iy - 1, content_w - 12, row_h, THEME['hover'])

                ov.draw_text(content_x + 14, iy + 16, label, THEME['text'])

                val = getattr(Config, key, None)

                # Right-side value/control region
                right_pad = 14
                rx = content_x + content_w - right_pad
                ctrl_y = iy + 5

                if kind == 'bool':
                    # Toggle switch
                    sw, sh = 44, 16
                    sx = rx - sw
                    sy = iy + (row_h - sh) // 2
                    on = bool(val)
                    track = THEME['accent'] if on else (38, 38, 52)
                    ov.draw_filled_rect(sx, sy, sw, sh, track)
                    ov.draw_box(sx, sy, sw, sh, THEME['divider'])
                    knob_w = 18
                    kx = sx + (sw - knob_w - 2) if on else sx + 2
                    ov.draw_filled_rect(kx, sy + 2, knob_w, sh - 4, (230, 230, 230) if on else (160, 160, 170))
                    ov.draw_box(kx, sy + 2, knob_w, sh - 4, THEME['divider'])

                elif kind == 'color':
                    col_val = getattr(Config, key, (255, 255, 255))
                    try:
                        r, g, b = col_val
                    except Exception:
                        r, g, b = (255, 255, 255)
                    r = _clamp255(r); g = _clamp255(g); b = _clamp255(b)
                    # swatch + rgb badge
                    swatch_w, swatch_h = 34, 14
                    swx = rx - swatch_w
                    swy = iy + (row_h - swatch_h) // 2
                    ov.draw_filled_rect(swx, swy, swatch_w, swatch_h, (r, g, b))
                    ov.draw_box(swx, swy, swatch_w, swatch_h, (240, 240, 240))
                    rgb_txt = f'{r},{g},{b}'
                    bw = 110
                    draw_badge(swx - bw - 8, iy + 4, bw, 16, rgb_txt, fill=THEME['panel_2'], border=THEME['divider'], text_col=THEME['muted'])

                elif kind == 'select':
                    txt = str(val) if val is not None else ''
                    bw = 130
                    draw_badge(rx - bw, iy + 4, bw, 16, txt.upper(), fill=THEME['panel_2'], border=THEME['divider'], text_col=THEME['muted'])

                elif kind == 'key':
                    if key_listen_target == key:
                        txt = 'PRESS KEY...'
                        fill = THEME['warn']
                        tcol = (0, 0, 0)
                    else:
                        txt = 'UNBOUND' if not val else str(val).upper()
                        fill = THEME['panel_2']
                        tcol = THEME['muted']
                    bw = 140
                    draw_badge(rx - bw, iy + 4, bw, 16, txt, fill=fill, border=THEME['divider'], text_col=tcol)

                elif kind == 'action':
                    if key == 'save_config':
                        txt = 'SAVE'
                        fill = THEME['active']
                    elif key == 'load_config':
                        txt = 'LOAD'
                        fill = THEME['active']
                    elif key == 'reset_config':
                        txt = 'RESET'
                        fill = (110, 55, 55)
                    else:
                        txt = 'RUN'
                        fill = THEME['active']
                    bw = 92
                    draw_badge(rx - bw, iy + 4, bw, 16, txt, fill=fill, border=THEME['divider'], text_col=THEME['text'])

                elif kind == 'map':
                    map_name = getattr(esp, 'current_detected_map', None)
                    if not map_name:
                        path = getattr(Config, 'visibility_map_path', '')
                        if path:
                            import os as _os
                            map_name = _os.path.splitext(_os.path.basename(str(path)))[0]
                    loaded = bool(getattr(Config, 'visibility_map_loaded', False))
                    txt = str(map_name or '<unknown>') if loaded else '<no map loaded>'
                    bw = 200
                    draw_badge(rx - bw, iy + 4, bw, 16, txt, fill=THEME['panel_2'], border=THEME['divider'], text_col=THEME['muted'])

                else:
                    # float / slider
                    try:
                        fval = float(val)
                    except Exception:
                        fval = 0.0

                    # slider track (click-to-set + knob)
                    mn, mxv, step, fmt = _get_slider_spec(key, fval)
                    fval = _clamp(fval, mn, mxv)

                    bar_w, bar_h = 160, 8
                    bar_x = rx - bar_w
                    bar_y = iy + (row_h - bar_h) // 2 + 2

                    # Rail
                    ov.draw_filled_rect(bar_x, bar_y, bar_w, bar_h, (34, 34, 48))

                    # Normalized fill
                    denom = (mxv - mn) if (mxv - mn) != 0 else 1.0
                    t = (fval - mn) / denom
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    fill_w = int(bar_w * t)
                    if fill_w > 0:
                        ov.draw_filled_rect(bar_x, bar_y, fill_w, bar_h, THEME['accent'])
                    ov.draw_box(bar_x, bar_y, bar_w, bar_h, THEME['divider'])

                    # Knob (small handle)
                    knob_w, knob_h = 10, 16
                    knob_x = bar_x + fill_w
                    knob_y = bar_y + (bar_h // 2) - (knob_h // 2)
                    knob_fill = THEME['active'] if (i == hover_index) else THEME['panel_2']
                    ov.draw_filled_rect(knob_x - (knob_w // 2), knob_y, knob_w, knob_h, knob_fill)
                    ov.draw_box(knob_x - (knob_w // 2), knob_y, knob_w, knob_h, THEME['divider'])

                    # numeric badge
                    try:
                        txt = fmt.format(fval)
                    except Exception:
                        txt = f'{fval:.2f}'
                    bw = 64
                    draw_badge(bar_x - bw - 8, iy + 4, bw, 16, txt, fill=THEME['panel_2'], border=THEME['divider'], text_col=THEME['muted'])


            # Scrollbar for tall tabs (Colors)
            if use_scroll and visible_h > 0 and total_h > visible_h:
                scroll_track_x = content_x + content_w - 8
                scroll_track_w = 10
                scroll_track_y = visible_top
                scroll_track_h = visible_h
                # Track
                ov.draw_filled_rect(scroll_track_x, scroll_track_y, scroll_track_w, scroll_track_h, (30, 30, 40))
                ov.draw_box(scroll_track_x, scroll_track_y, scroll_track_w, scroll_track_h, THEME['divider'])
                # Thumb
                thumb_min_h = 12
                thumb_h = max(thumb_min_h, int(visible_h * visible_h / float(total_h)))
                max_thumb_move = max(1, visible_h - thumb_h)
                if max_offset <= 0:
                    thumb_y = scroll_track_y
                else:
                    thumb_y = scroll_track_y + int((scroll_offset / float(max_offset)) * max_thumb_move)
                ov.draw_filled_rect(scroll_track_x + 1, thumb_y + 1, scroll_track_w - 2, thumb_h - 2, THEME['accent'])

            # Footer bar
            fy = y + h - footer_h
            ov.draw_filled_rect(x, fy, w, footer_h, THEME['footer'])
            ov.draw_filled_rect(x, fy, w, 1, THEME['divider'])

            # Status text areas
            left = x + sidebar_w + 18
            line2_y = fy + 24

            # Config status (short)
            if _cfg_status and time.time() - _cfg_status_time < 3.0:
                ov.draw_text(left, line2_y, _cfg_status, THEME['dim'])

            # Crash / restart status (short)
            if crash_status_text and time.time() - crash_status_time < 5.0:
                ov.draw_text(left + 220, line2_y, crash_status_text, THEME['warn'])

            # EXIT button (bottom right)
            exit_w, exit_h = (92, 26)
            exit_x = x + w - exit_w - 12
            exit_y = fy + (footer_h - exit_h) // 2
            mx, my = get_mouse_pos()
            hovered = exit_x < mx < exit_x + exit_w and exit_y < my < exit_y + exit_h
            fill = THEME['accent'] if hovered else (135, 30, 30)
            ov.draw_filled_rect(exit_x, exit_y, exit_w, exit_h, fill)
            ov.draw_box(exit_x, exit_y, exit_w, exit_h, THEME['accent_2'])
            ov.draw_text(exit_x + 30, exit_y + 18, 'EXIT', THEME['text'])

    except Exception:
        pass

# -------------------------------------------------
# Overlay hooks: run menu input + draw each frame
# -------------------------------------------------
try:
    _orig_begin = HelpersOverlay.begin_scene  # type: ignore[attr-defined]
    _orig_end = HelpersOverlay.end_scene      # type: ignore[attr-defined]
except Exception:
    _orig_begin = None
    _orig_end = None

def begin_hook(self):
    try:
        handle_menu()
    except Exception as e:
        try:
            if DEBUG_LOGGING:
                logger.debug(f'[Main] Menu handling error: {e}')
            traceback.print_exc()
        except Exception:
            pass
    try:
        if _orig_begin is None:
            return False
        return _orig_begin(self)
    except Exception as e:
        try:
            if DEBUG_LOGGING:
                logger.debug(f'[Main] Overlay begin_scene error: {e}')
            traceback.print_exc()
        except Exception:
            pass
        return False

def end_hook(self):
    try:
        draw_menu(self)
    except Exception as e:
        try:
            if DEBUG_LOGGING:
                logger.debug(f'[Main] Menu draw error: {e}')
            traceback.print_exc()
        except Exception:
            pass
    try:
        if _orig_end is None:
            return None
        return _orig_end(self)
    except Exception as e:
        try:
            if DEBUG_LOGGING:
                logger.debug(f'[Main] Overlay end_scene error: {e}')
            traceback.print_exc()
        except Exception:
            pass
        return None

# Apply hooks only if overlay class exists
if HelpersOverlay is not None:
    try:
        HelpersOverlay.begin_scene = begin_hook  # type: ignore[attr-defined]
        HelpersOverlay.end_scene = end_hook      # type: ignore[attr-defined]
    except Exception:
        pass

def _run_with_restart(name, func, *args, **kwargs):
    """Run a worker function in a restart loop.

    If it ever crashes with an unexpected exception, notify the user in the
    overlay and then automatically restart the worker after a brief delay.
    """
    while True:
        try:
            func(*args, **kwargs)
        except SystemExit:
            # Respect explicit exit requests.
            raise
        except Exception as e:
            # Notify user in overlay and logs, then restart.
            try:
                _set_crash_status(f"{name} crashed, restarting...")
            except Exception:
                pass
            try:
                if DEBUG_LOGGING:
                    logger.debug(f"[Main] Worker '{name}' crashed: {e}")
                traceback.print_exc()
            except Exception:
                pass
            time.sleep(1.0)

def _start_safe_thread(name, func, *args, **kwargs):
    t = threading.Thread(target=_run_with_restart, args=(name, func) + args, kwargs=kwargs, daemon=True)
    t.start()
    return t

def main():
    # Before starting any features or kernel checks, wait for CS2 to be running.
    try:
        _wait_for_cs2_with_overlay()
    except Exception as e:
        if DEBUG_LOGGING:
            try:
                logger.debug(f'[Main] CS2 wait overlay error: {e}')
                traceback.print_exc()
            except Exception:
                pass

    # After CS2 is running, import heavy feature modules (ESP, aimbot, etc.)
    try:
        _lazy_import_features()
    except Exception as e:
        if DEBUG_LOGGING:
            try:
                logger.debug(f'[Main] Lazy feature import error: {e}')
                traceback.print_exc()
            except Exception:
                pass
        sys.exit(1)

    # Load offsets via signature scanning
    try:
        Offsets, ClassOffsets = _main_get_offsets(force_update=False)
        set_global_offsets(Offsets, ClassOffsets)
    except Exception as e:
        print(f'[ERROR] Failed to load offsets: {e}')
        traceback.print_exc()
        sys.exit(1)

    _start_safe_thread('AimbotRCS', AimbotRCS(Config).run)
    _start_safe_thread('BHop', bhop.BHopProcess().run)
    _start_safe_thread('TriggerBot', TriggerBot(shared_config=Config).run)
    _start_safe_thread('Radar', lambda: RadarApp(cfg_ref=Config).start())
    while True:
        try:
            esp.main()
            break
        except SystemExit:
            raise
        except Exception as e:
            # Notify user and restart ESP render loop
            try:
                _set_crash_status('ESP crashed, restarting...')
            except Exception:
                pass
            try:
                if DEBUG_LOGGING:
                    logger.debug(f'[Main] ESP main loop crashed: {e}')
                traceback.print_exc()
            except Exception:
                pass
            time.sleep(1.0)

if __name__ == '__main__':
    main()
