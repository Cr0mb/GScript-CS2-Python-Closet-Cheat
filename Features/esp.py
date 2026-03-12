from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
import logging

_log = logging.getLogger(__name__)
import time
import os
import struct
import ctypes
try:
    _user32 = ctypes.windll.user32
    _WDA_NONE = 0
    _WDA_EXCLUDEFROMCAPTURE = 17
except Exception:
    _user32 = None
    _WDA_NONE = 0
    _WDA_EXCLUDEFROMCAPTURE = 17

def _set_overlay_capture_excluded(overlay, excluded: bool) -> None:
    if _user32 is None or overlay is None or (not getattr(overlay, 'hwnd', None)):
        return
    try:
        current = getattr(overlay, '_capture_excluded_state', None)
        if current is not None and bool(current) == bool(excluded):
            return
        mode = _WDA_EXCLUDEFROMCAPTURE if excluded else _WDA_NONE
        _user32.SetWindowDisplayAffinity(overlay.hwnd, mode)
        setattr(overlay, '_capture_excluded_state', bool(excluded))
    except Exception:
        pass
from Process.helpers import CS2Process, Vec3, Overlay, read_matrix, w2s, get_entities, BONE_POSITIONS, BONE_CONNECTIONS, FLAGS, ensure_offsets_loaded, read_bytes, read_string, get_module_base, RPMReader, get_vk_code, get_current_dynamic_fov, register_memory_reader

from Process.helpers import read_int, safe_read_uint64
from Process.config import Config
import struct

# Read float helper
def read_float(handle, addr):
    """Read float from memory address."""
    try:
        data = read_bytes(handle, addr, 4)
        if data and len(data) >= 4:
            return struct.unpack('f', data[:4])[0]
    except Exception:
        pass
    return 0.0
user32 = ctypes.windll.user32
_PANIC_ESP_HIDDEN = False

import os
import sys

VISCHECK_AVAILABLE = False

try:
    appdata_dir = os.environ.get("APPDATA")
    if not appdata_dir:
        raise RuntimeError("APPDATA not set")

    gscript_dir = os.path.join(appdata_dir, "GScript")

    # Ensure the directory exists
    if os.path.isdir(gscript_dir):
        # Prepend so it has priority over local paths
        if gscript_dir not in sys.path:
            sys.path.insert(0, gscript_dir)

        import vischeck
        VISCHECK_AVAILABLE = True
    else:
        raise FileNotFoundError(f"{gscript_dir} does not exist")

except Exception as exc:
    VISCHECK_AVAILABLE = False
    try:
        _log.debug("ESP: vischeck import failed: %r", exc)
    except Exception:
        pass

DW_GAME_TYPES_MAP_NAME = 288  # Offset within GameTypes structure for map name pointer
vis_checker = None
last_map_check_time = 0.0
current_detected_map = None

def get_current_map_name(handle, matchmaking_base, offsets=None):
    try:
        if not handle or not matchmaking_base:
            return None
        # Use scanned dwGameTypes offset if available, otherwise fall back
        dw_game_types = getattr(offsets, 'dwGameTypes', None) if offsets else None
        if not dw_game_types:
            from Process.helpers import ensure_offsets_loaded
            _Offsets, _ = ensure_offsets_loaded()
            dw_game_types = getattr(_Offsets, 'dwGameTypes', None)
        if not dw_game_types:
            return None  # Can't proceed without valid offset
        map_name_ptr_address = matchmaking_base + dw_game_types + DW_GAME_TYPES_MAP_NAME
        ptr_bytes = read_bytes(handle, map_name_ptr_address, 8)
        if not ptr_bytes:
            return None
        map_name_ptr = struct.unpack('Q', ptr_bytes)[0]
        if not map_name_ptr or map_name_ptr > 140737488355327:
            return None
        name = read_string(handle, map_name_ptr, 64)
        if not name:
            return '<empty>'
        return name
    except Exception:
        return None

# === Helper functions for new ESP features ===

def get_weapon_name_from_pawn(handle, pawn_addr, offsets):
    """Read active weapon name from player pawn."""
    try:
        # Read weapon services
        weapon_services = safe_read_uint64(handle, pawn_addr + offsets.m_pWeaponServices)
        if not weapon_services:
            return ""
        
        # Read active weapon handle
        active_weapon_handle = read_int(handle, weapon_services + offsets.m_hActiveWeapon) & 0x7FFF
        if not active_weapon_handle or active_weapon_handle == 0x7FFF:
            return ""
        
        # Get entity list and resolve weapon entity
        entity_list = safe_read_uint64(handle, pawn_addr)  # This needs proper base
        if not entity_list:
            return ""
        
        # Resolve weapon entity from handle
        list_entry = safe_read_uint64(handle, entity_list + (8 * ((active_weapon_handle & 0x7FFF) >> 9) + 16))
        if not list_entry:
            return ""
        
        weapon_entity = safe_read_uint64(handle, list_entry + (112 * (active_weapon_handle & 0x1FF)))
        if not weapon_entity:
            return ""
        
        # Read weapon designer name
        entity_identity = safe_read_uint64(handle, weapon_entity + 0x10)
        if not entity_identity:
            return ""
        
        designer_name_ptr = safe_read_uint64(handle, entity_identity + 0x20)
        if not designer_name_ptr:
            return ""
        
        weapon_name = read_string(handle, designer_name_ptr, 64)
        if weapon_name and weapon_name.startswith("weapon_"):
            return weapon_name[7:]  # Strip "weapon_" prefix
        return weapon_name
    except Exception:
        return ""

def get_weapon_name_simple(handle, pawn_addr, entity_list_base, offsets):
    """Simplified weapon name reader using entity list base."""
    try:
        # Check if required offsets exist
        weapon_services_offset = getattr(offsets, 'm_pWeaponServices', None)
        active_weapon_offset = getattr(offsets, 'm_hActiveWeapon', None)
        
        if not weapon_services_offset or not active_weapon_offset:
            return ""
        
        weapon_services = safe_read_uint64(handle, pawn_addr + weapon_services_offset)
        if not weapon_services:
            return ""
        
        active_weapon_handle = read_int(handle, weapon_services + active_weapon_offset) & 0x7FFF
        if not active_weapon_handle or active_weapon_handle == 0x7FFF:
            return ""
        
        list_entry = safe_read_uint64(handle, entity_list_base + (8 * (active_weapon_handle >> 9) + 16))
        if not list_entry:
            return ""
        
        weapon_entity = safe_read_uint64(handle, list_entry + (112 * (active_weapon_handle & 0x1FF)))
        if not weapon_entity:
            return ""
        
        entity_identity = safe_read_uint64(handle, weapon_entity + 0x10)
        if not entity_identity:
            return ""
        
        designer_name_ptr = safe_read_uint64(handle, entity_identity + 0x20)
        if not designer_name_ptr:
            return ""
        
        weapon_name = read_string(handle, designer_name_ptr, 64)
        if weapon_name and weapon_name.startswith("weapon_"):
            return weapon_name[7:]
        return weapon_name
    except Exception:
        return ""

def draw_crosshair(overlay, cfg):
    """Draw external crosshair at screen center."""
    try:
        if not getattr(cfg, 'crosshair_enabled', False):
            return
        
        size = int(getattr(cfg, 'crosshair_size', 10))
        thickness = int(getattr(cfg, 'crosshair_thickness', 2))
        color = getattr(cfg, 'crosshair_color', (0, 255, 0))
        
        cx = overlay.width // 2
        cy = overlay.height // 2
        
        # Draw horizontal line
        overlay.draw_filled_rect(cx - size, cy - thickness // 2, size * 2, thickness, color)
        # Draw vertical line
        overlay.draw_filled_rect(cx - thickness // 2, cy - size, thickness, size * 2, color)
    except Exception:
        pass

# === Spectator List (ported from GFusion) ===

# Initial on-screen position for the spectator list box.
spectator_list_pos = [20, 300]  # x, y
# Drag state for spectator list
spectator_dragging = False
spectator_drag_offset = [0, 0]  # mouse offset inside the box while dragging

# === Team List (draggable overlay like spectator list) ===

team_list_pos = [0, 0]          # x, y (initialized on first draw)
team_list_pos_inited = False

team_dragging = False
team_drag_offset = [0, 0]

# === Map Status (draggable overlay like spectator list) ===
map_status_pos = [0, 0]
map_status_pos_inited = False

map_status_dragging = False
map_status_drag_offset = [0, 0]

# === FPS (draggable overlay like spectator list) ===
fps_pos = [0, 0]
fps_pos_inited = False

fps_dragging = False
fps_drag_offset = [0, 0]


class SpectatorList:
    """Lightweight helper to resolve who is spectating the local player."""

    def __init__(self, handle, client_base, offsets):
        self.handle = handle
        self.client_base = client_base
        self.offsets = offsets
        self.last_spec_check = 0.0
        self.cached_spectators = []

    def _safe_read_uint64(self, addr: int) -> int:
        if not addr or addr > 0x7FFFFFFFFFFF:
            return 0
        try:
            return safe_read_uint64(self.handle, addr)
        except Exception:
            return 0

    def _safe_read_int(self, addr: int) -> int:
        if not addr or addr > 0x7FFFFFFFFFFF:
            return 0
        try:
            return read_int(self.handle, addr)
        except Exception:
            return 0

    def _safe_read_string(self, addr: int, max_length: int = 32) -> str:
        if not addr or addr > 0x7FFFFFFFFFFF:
            return ""
        try:
            raw = read_bytes(self.handle, addr, max_length)
            if not raw:
                return ""
            return raw.split(b"\x00")[0].decode(errors="ignore")
        except Exception:
            return ""

    def _get_entity(self, entity_list: int, handle: int) -> int:
        hi = handle >> 9
        lo = handle & 0x1FF
        entry_addr = entity_list + 0x8 * hi + 0x10
        entry = self._safe_read_uint64(entry_addr)
        if not entry:
            return 0
        # 112 == sizeof(entry) in CS2 entity list
        return self._safe_read_uint64(entry + 112 * lo)

    def GetSpectators(self):
        """Resolve a list of player names currently spectating the local player."""
        try:
            o = self.offsets
            entity_list = self._safe_read_uint64(self.client_base + o.dwEntityList)
            local_controller = self._safe_read_uint64(self.client_base + o.dwLocalPlayerController)
            if not local_controller or not entity_list:
                return []

            local_pawn_handle = self._safe_read_int(local_controller + o.m_hPawn) & 0x7FFF
            local_pawn = self._get_entity(entity_list, local_pawn_handle)
            if not local_pawn:
                return []

            spectators = []
            # Hard cap at 64 players – CS2 standard.
            for i in range(1, 65):
                controller = self._get_entity(entity_list, i)
                if not controller or controller == local_controller:
                    continue

                obs_pawn_handle = self._safe_read_int(controller + o.m_hPawn) & 0x7FFF
                observer_pawn = self._get_entity(entity_list, obs_pawn_handle)
                if not observer_pawn:
                    continue

                observer_services = self._safe_read_uint64(observer_pawn + o.m_pObserverServices)
                if not observer_services:
                    continue

                target_handle = self._safe_read_int(observer_services + o.m_hObserverTarget) & 0x7FFF
                target_pawn = self._get_entity(entity_list, target_handle)
                if target_pawn == local_pawn:
                    name = self._safe_read_string(controller + o.m_iszPlayerName)
                    if name:
                        spectators.append(name)
            return spectators
        except Exception:
            # Hard-fail should not kill ESP; just treat as no spectators.
            return []

    def GetSpectatorsCached(self):
        """Cache spectator list for ~1s to avoid spamming RPM."""
        now = time.time()
        if now - self.last_spec_check > 1.0:
            self.cached_spectators = self.GetSpectators()
            self.last_spec_check = now
        return self.cached_spectators


# === Spectator list card styling (clean, centered, menu-like) ===

def draw_info_box(overlay, x, y, w, h, title, lines, font_size: int = 12,
                  title_color=None, body_color=None):
    """Card-style info box used by the spectator list.

    Clean dark panel, centered title, no split header/line through text.
    """
    from Process.config import Config  # local import to avoid cycles

    # Panel + border colors – tied into menu theme when available
    bg = getattr(
        Config,
        "color_menu_panel_bg",
        getattr(Config, "color_local_box_background", (18, 18, 22)),
    )
    bd = getattr(
        Config,
        "color_menu_panel_border",
        getattr(Config, "color_local_box_border", (80, 80, 90)),
    )

    # Text colors
    tcol = (
        title_color
        if title_color is not None
        else getattr(Config, "color_menu_title", (255, 255, 255))
    )
    bcol = (
        body_color
        if body_color is not None
        else getattr(Config, "color_menu_text", (220, 220, 220))
    )

    # Draw background panel + border
    overlay.draw_filled_rect(x, y, w, h, bg)
    overlay.draw_box(x, y, w, h, bd)

    header_h = font_size + 10
    body_start_y = y + 6

    if title:
        # Rough horizontal centering of title based on character width
        approx_char_width = font_size * 0.55
        title_pixel_w = int(len(title) * approx_char_width)
        title_x = x + (w // 2) - (title_pixel_w // 2)
        title_y = y + 6

        overlay.draw_text(title_x, title_y, str(title), tcol)
        body_start_y = y + header_h

    # Body lines (spectator names) start below the title area
    if lines:
        line_spacing = font_size + 4
        for i, line in enumerate(lines):
            overlay.draw_text(
                x + 10,
                body_start_y + i * line_spacing,
                str(line),
                bcol,
            )

def update_fps_drag(overlay, box_w, box_h):
    """Update fps_pos based on mouse drag over the box."""
    global fps_pos, fps_dragging, fps_drag_offset

    try:
        if not getattr(overlay, 'hwnd', None):
            return

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        user32.ScreenToClient(overlay.hwnd, ctypes.byref(pt))
        mx, my = pt.x, pt.y

        left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

        if left_down:
            if not fps_dragging:
                x, y = fps_pos
                if x <= mx <= x + box_w and y <= my <= y + box_h:
                    fps_dragging = True
                    fps_drag_offset[0] = mx - x
                    fps_drag_offset[1] = my - y

            if fps_dragging:
                fps_pos[0] = mx - fps_drag_offset[0]
                fps_pos[1] = my - fps_drag_offset[1]
                clamp_box_to_screen(fps_pos, box_w, box_h, overlay.width, overlay.height)
        else:
            fps_dragging = False
    except Exception:
        pass


def draw_fps_box(overlay, fps_value: float):
    """Draw a draggable FPS card."""
    global fps_pos, fps_pos_inited

    from Process.config import Config  # local import

    font_size = 12
    line_spacing = font_size + 4

    title = "Performance"
    lines = [f"FPS: {fps_value:.0f}"]

    if not fps_pos_inited:
        # Default: top-left corner (same area you had before)
        fps_pos[0] = 20
        fps_pos[1] = 20
        fps_pos_inited = True

    max_len = max(len(title), *(len(s) for s in lines))
    approx_char_width = font_size * 0.55
    w = max(170, int(max_len * approx_char_width) + 24)

    header_h = font_size + 10
    body_h = len(lines) * line_spacing
    h = header_h + body_h + 8

    update_fps_drag(overlay, w, h)
    clamp_box_to_screen(fps_pos, w, h, overlay.width, overlay.height)

    body_col = getattr(Config, "color_fps_text", getattr(Config, "color_menu_text", (220, 220, 220)))

    draw_info_box(
        overlay,
        fps_pos[0],
        fps_pos[1],
        w,
        h,
        title,
        lines,
        font_size=font_size,
        title_color=None,
        body_color=body_col,
    )


def update_map_status_drag(overlay, box_w, box_h):
    """Update map_status_pos based on mouse drag over the box."""
    global map_status_pos, map_status_dragging, map_status_drag_offset

    try:
        if not getattr(overlay, 'hwnd', None):
            return

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        user32.ScreenToClient(overlay.hwnd, ctypes.byref(pt))
        mx, my = pt.x, pt.y

        left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

        if left_down:
            if not map_status_dragging:
                x, y = map_status_pos
                if x <= mx <= x + box_w and y <= my <= y + box_h:
                    map_status_dragging = True
                    map_status_drag_offset[0] = mx - x
                    map_status_drag_offset[1] = my - y

            if map_status_dragging:
                map_status_pos[0] = mx - map_status_drag_offset[0]
                map_status_pos[1] = my - map_status_drag_offset[1]
                clamp_box_to_screen(map_status_pos, box_w, box_h, overlay.width, overlay.height)
        else:
            map_status_dragging = False
    except Exception:
        pass


def draw_map_status(overlay, map_name: str):
    """Draw a draggable map status card."""
    global map_status_pos, map_status_pos_inited

    from Process.config import Config  # local import

    font_size = 12
    line_spacing = font_size + 4

    title = "Map Status"
    lines = [f"Map: {map_name}"]

    if not map_status_pos_inited:
        # Default: top-left-ish, under FPS line
        map_status_pos[0] = 20
        map_status_pos[1] = 60
        map_status_pos_inited = True

    max_len = max(len(title), *(len(s) for s in lines))
    approx_char_width = font_size * 0.55
    w = max(200, int(max_len * approx_char_width) + 24)

    header_h = font_size + 10
    body_h = len(lines) * line_spacing
    h = header_h + body_h + 8

    update_map_status_drag(overlay, w, h)
    clamp_box_to_screen(map_status_pos, w, h, overlay.width, overlay.height)

    body_col = getattr(Config, "color_map_status_text", getattr(Config, "color_menu_text", (220, 220, 220)))

    draw_info_box(
        overlay,
        map_status_pos[0],
        map_status_pos[1],
        w,
        h,
        title,
        lines,
        font_size=font_size,
        title_color=None,
        body_color=body_col,
    )


def update_spectator_drag(overlay, box_w, box_h):
    """Update spectator_list_pos based on mouse drag over the box."""
    global spectator_list_pos, spectator_dragging, spectator_drag_offset

    try:
        # We need a valid window handle to convert screen -> client coords
        if not getattr(overlay, 'hwnd', None):
            return

        # POINT struct for WinAPI calls
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()

        # Get mouse cursor position in screen coords
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        # Convert to overlay client coords
        user32.ScreenToClient(overlay.hwnd, ctypes.byref(pt))
        mx, my = pt.x, pt.y

        # Left mouse button state
        left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

        if left_down:
            if not spectator_dragging:
                # Start drag if we clicked inside the current box rect
                x, y = spectator_list_pos
                if x <= mx <= x + box_w and y <= my <= y + box_h:
                    spectator_dragging = True
                    spectator_drag_offset[0] = mx - x
                    spectator_drag_offset[1] = my - y

            if spectator_dragging:
                # Update position while dragging
                spectator_list_pos[0] = mx - spectator_drag_offset[0]
                spectator_list_pos[1] = my - spectator_drag_offset[1]
                # Keep within the overlay bounds
                clamp_box_to_screen(
                    spectator_list_pos, box_w, box_h, overlay.width, overlay.height
                )
        else:
            # Mouse released, stop dragging
            spectator_dragging = False

    except Exception:
        # Never let drag handling kill ESP
        pass


def clamp_box_to_screen(pos, w, h, screen_w, screen_h):
    """Clamp a draggable box to stay fully visible on-screen."""
    x = max(0, min(pos[0], max(0, screen_w - w)))
    y = max(0, min(pos[1], max(0, screen_h - h)))
    pos[0], pos[1] = x, y


def update_team_list_drag(overlay, box_w, box_h):
    """Update team_list_pos based on mouse drag over the box."""
    global team_list_pos, team_dragging, team_drag_offset

    try:
        if not getattr(overlay, 'hwnd', None):
            return

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        user32.ScreenToClient(overlay.hwnd, ctypes.byref(pt))
        mx, my = pt.x, pt.y

        left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

        if left_down:
            if not team_dragging:
                x, y = team_list_pos
                if x <= mx <= x + box_w and y <= my <= y + box_h:
                    team_dragging = True
                    team_drag_offset[0] = mx - x
                    team_drag_offset[1] = my - y

            if team_dragging:
                team_list_pos[0] = mx - team_drag_offset[0]
                team_list_pos[1] = my - team_drag_offset[1]
                clamp_box_to_screen(team_list_pos, box_w, box_h, overlay.width, overlay.height)
        else:
            team_dragging = False
    except Exception:
        pass


def draw_team_list(overlay, t_players, ct_players):
    """Draw a draggable team list card."""
    global team_list_pos, team_list_pos_inited

    from Process.config import Config  # local import

    font_size = 12
    line_spacing = font_size + 4

    # Build lines (single card with sections)
    lines = []
    lines.append(f"T ({len(t_players)}):")
    if t_players:
        lines.extend(t_players[:10])
    else:
        lines.append("None")

    lines.append("")  # spacer

    lines.append(f"CT ({len(ct_players)}):")
    if ct_players:
        lines.extend(ct_players[:10])
    else:
        lines.append("None")

    title = f"Team List (T:{len(t_players)} | CT:{len(ct_players)})"

    # First-time default placement: top-right-ish, but inside screen
    if not team_list_pos_inited:
        # rough default width guess; we'll clamp again after sizing
        team_list_pos[0] = max(0, int(overlay.width - 260))
        team_list_pos[1] = 100
        team_list_pos_inited = True

    # Size calc based on widest text
    max_len = max([len(title)] + [len(str(x)) for x in lines]) if lines else len(title)
    approx_char_width = font_size * 0.55
    content_w = int(max_len * approx_char_width) + 24
    min_w = 220
    max_w = max(260, int(overlay.width * 0.40))
    w = max(min_w, min(content_w, max_w))

    header_block_h = font_size + 10
    body_h = max(1, len(lines)) * line_spacing
    h = header_block_h + body_h + 8

    # Drag + clamp
    update_team_list_drag(overlay, w, h)
    clamp_box_to_screen(team_list_pos, w, h, overlay.width, overlay.height)

    # You can tweak this via Config if you want; otherwise default to menu text
    body_col = getattr(Config, "color_team_list_text", getattr(Config, "color_menu_text", (220, 220, 220)))

    draw_info_box(
        overlay,
        team_list_pos[0],
        team_list_pos[1],
        w,
        h,
        title,
        lines,
        font_size=font_size,
        title_color=None,
        body_color=body_col,
    )


def draw_spectator_list(overlay, spectators):
    """Draw the spectator list card at the current drag position.

    The box auto-sizes based on title + names and is clamped inside the
    overlay so the title never clips off the window.
    """
    global spectator_list_pos
    from Process.config import Config  # local import

    rows = spectators if spectators else ["None"]
    font_size = 12

    # Title styling and count
    count = 0 if not spectators else len(spectators)
    title = f"Spectators ({count})"

    # Width based on both title and body text
    max_body_len = max(len(str(r)) for r in rows) if rows else 0
    title_len = len(title)
    max_len = max(max_body_len, title_len)

    approx_char_width = font_size * 0.55
    content_w = int(max_len * approx_char_width) + 24  # padding left/right
    min_w = 190
    max_w = max(220, int(overlay.width * 0.35))

    w = max(min_w, min(content_w, max_w))

    # Height: header block + lines (must match logic in draw_info_box)
    line_spacing = font_size + 4
    header_block_h = font_size + 10
    body_h = max(1, len(rows)) * line_spacing
    h = header_block_h + body_h + 8  # bottom padding

    # Handle dragging using the current box size
    update_spectator_drag(overlay, w, h)

    # Keep card fully on-screen after drag
    clamp_box_to_screen(spectator_list_pos, w, h, overlay.width, overlay.height)

    # Spectator text color hooked into config
    spec_color = getattr(Config, "color_spectators", (200, 200, 200))

    draw_info_box(
        overlay,
        spectator_list_pos[0],
        spectator_list_pos[1],
        w,
        h,
        title,
        rows,
        font_size=font_size,
        title_color=None,
        body_color=spec_color,
    )


def _get_gscript_maps_dir() -> str:
    """
    Returns the absolute path to the maps directory located next to GScript.py.
    Maps are stored in GScript/maps/ subdirectory.
    """
    # Get the directory where GScript.py is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate up to project root (from Features/ to GScript/)
    project_root = os.path.dirname(script_dir)
    maps_dir = os.path.join(project_root, "maps")
    os.makedirs(maps_dir, exist_ok=True)
    return maps_dir


def auto_map_loader(handle, matchmaking_base, vis_checker_obj):
    global last_map_check_time, current_detected_map

    if not handle or not matchmaking_base or (not vis_checker_obj):
        return

    current_time = time.time()
    if current_time - last_map_check_time < 3.0:
        return
    last_map_check_time = current_time

    detected_map = get_current_map_name(handle, matchmaking_base)
    if not detected_map or detected_map == "<empty>":
        return

    loaded_map_name = None
    try:
        if vis_checker_obj.is_map_loaded():
            loaded_map_path = vis_checker_obj.get_current_map()
            if loaded_map_path:
                loaded_map_name = os.path.basename(loaded_map_path).replace(".opt", "")
    except Exception:
        loaded_map_name = None

    if detected_map != current_detected_map:
        current_detected_map = detected_map

    if detected_map != loaded_map_name:
        target_map_file = f"{detected_map}.opt"
        maps_dir = _get_gscript_maps_dir()
        target_map_path = os.path.join(maps_dir, target_map_file)

        if os.path.exists(target_map_path):
            # Prefer absolute paths so downstream loaders don’t depend on cwd
            target_map_path = os.path.abspath(target_map_path)
            setattr(Config, "visibility_map_path", target_map_path)
            setattr(Config, "visibility_map_reload_needed", True)
        else:
            pass
    else:
        pass
        
def check_player_visibility(local_pos, entity_pos, vis_checker_obj):
    """Cheap wrapper around vischeck with an optional per-frame budget.

    When Performance.vischeck_optimizer.can_do_vischeck is available, this will
    cap the number of expensive visibility raycasts per frame so ESP + aimbot
    cannot accidentally spam vischeck when many entities are on screen.
    """
    try:
        if not local_pos or not entity_pos or (not vis_checker_obj):
            return False

        try:
            if not vis_checker_obj.is_map_loaded():
                return True
        except Exception:
            return True

        eye_offset = 64.0
        local_eye_pos = (float(local_pos.x), float(local_pos.y), float(local_pos.z + eye_offset))
        entity_eye_pos = (float(entity_pos.x), float(entity_pos.y), float(entity_pos.z + eye_offset))
        is_visible = None
        if hasattr(vis_checker_obj, 'is_visible'):
            is_visible = vis_checker_obj.is_visible(local_eye_pos, entity_eye_pos)
        elif hasattr(vis_checker_obj, 'trace'):
            dx = entity_eye_pos[0] - local_eye_pos[0]
            dy = entity_eye_pos[1] - local_eye_pos[1]
            dz = entity_eye_pos[2] - local_eye_pos[2]
            is_visible = vis_checker_obj.trace(local_eye_pos[0], local_eye_pos[1], local_eye_pos[2], dx, dy, dz)
        if is_visible is None:
            return True
        return bool(is_visible)
    except Exception:
        return True


def render_bone_esp(overlay: Overlay, ent, matrix, is_visible: bool | None=None):
    skeleton_enabled = FLAGS.get('skeleton_esp_enabled', False)
    if not skeleton_enabled:
        return
    color_bone = FLAGS.get('color_bone', (255, 255, 255))
    try:
        team = getattr(ent, 'team', 0)
    except Exception:
        team = 0
    if team == 2:
        if is_visible is True:
            color_bone = FLAGS.get('color_skeleton_t_visible', FLAGS.get('color_skeleton_t', FLAGS.get('color_vis_t_visible', FLAGS.get('color_t', color_bone))))
        elif is_visible is False:
            color_bone = FLAGS.get('color_skeleton_t_invisible', FLAGS.get('color_skeleton_t', FLAGS.get('color_vis_t_invisible', FLAGS.get('color_t', color_bone))))
        else:
            color_bone = FLAGS.get('color_skeleton_t', FLAGS.get('color_t', color_bone))
    elif team == 3:
        if is_visible is True:
            color_bone = FLAGS.get('color_skeleton_ct_visible', FLAGS.get('color_skeleton_ct', FLAGS.get('color_vis_ct_visible', FLAGS.get('color_ct', color_bone))))
        elif is_visible is False:
            color_bone = FLAGS.get('color_skeleton_ct_invisible', FLAGS.get('color_skeleton_ct', FLAGS.get('color_vis_ct_invisible', FLAGS.get('color_ct', color_bone))))
        else:
            color_bone = FLAGS.get('color_skeleton_ct', FLAGS.get('color_ct', color_bone))
    needed_bones: set[int] = set((b for conn in BONE_CONNECTIONS for b in conn))
    now = time.perf_counter()
    bone_positions = ent.get_bone_positions(needed_bones, now=now)
    bone_screens: dict[int, tuple[float, float] | None] = {}
    w, h = (overlay.width, overlay.height)
    for bone in needed_bones:
        pos = bone_positions.get(bone)
        if not pos:
            bone_screens[bone] = None
            continue
        try:
            s = w2s(matrix, pos, w, h)
            bone_screens[bone] = (s['x'], s['y'])
        except Exception:
            bone_screens[bone] = None
    for a, b in BONE_CONNECTIONS:
        pa, pb = (bone_screens.get(a), bone_screens.get(b))
        if pa and pb:
            overlay.draw_line(pa[0], pa[1], pb[0], pb[1], color_bone)

def _esp_vis_enabled(cfg) -> bool:
    val = getattr(cfg, 'visibility_esp_enabled', None)
    if val is not None:
        return bool(val)
    val = getattr(cfg, 'visibility_aim_enabled', None)
    if val is not None:
        return bool(val)
    val = getattr(cfg, 'visibility_enabled', None)
    if val is not None:
        return bool(val)
    return True

def main():
    global vis_checker
    try:
        cs2 = CS2Process()
        cs2.initialize()
    except TimeoutError:
        return
    handle = cs2.process_handle
    base = cs2.module_base
    pid = cs2.get_pid() if hasattr(cs2, 'get_pid') else getattr(cs2, 'process_id', None)
    Offsets, _ClassOffsets = ensure_offsets_loaded()
    if Offsets is None:
        return
    matchmaking_base = get_module_base(pid, 'matchmaking.dll') if pid else None
    reader = None
    if pid is not None:
        try:
            reader = RPMReader(pid, handle, Config)
            register_memory_reader(handle, reader)
        except Exception:
            reader = None

    # Delay vischecker setup until the main loop so we can handle the case
    # where matchmaking.dll loads after the cheat starts.
    vis_checker = None
    overlay = Overlay()
    overlay.init('CS2 Box + Skeleton ESP')

    spectator_list = SpectatorList(handle, base, Offsets)
    head_bone_index = BONE_POSITIONS.get('head', 6)
    last_frame_time = time.time()
    smoothed_fps = 0.0
    cfg = Config
    _esp_cfg_last_refresh = 0.0
    _esp_cfg_refresh_interval = 0.25
    show_t = True
    show_ct = True
    draw_aimbot_fov = False
    dynamic_fov_enabled = False
    base_fov_deg = 0.0
    dynamic_fov_max_distance = 3000.0
    dynamic_fov_min_scale = 0.5
    dynamic_fov_max_scale = 1.5
    game_horizontal_fov = 90.0
    box_esp_enabled = FLAGS.get('box_esp_enabled', True)
    hp_bar_enabled = FLAGS.get('hp_bar_enabled', True)
    skeleton_esp_enabled = FLAGS.get('skeleton_esp_enabled', FLAGS.get('skeleton_esp_enabled', False))
    name_esp_enabled = FLAGS.get('name_esp_enabled', True)
    while overlay.begin_scene():
        try:
            # Lazily resolve matchmaking.dll base and vischecker so that
            # starting the loader before CS2 or before joining a match still
            # results in a valid vischeck setup once the module is loaded.
            if VISCHECK_AVAILABLE and handle:
                if (matchmaking_base is None) and (pid is not None):
                    try:
                        new_base = get_module_base(pid, 'matchmaking.dll')
                        if new_base:
                            matchmaking_base = new_base
                    except Exception:
                        pass
                if (vis_checker is None) and matchmaking_base:
                    try:
                        vis_checker = vischeck.VisCheck()
                    except Exception:
                        vis_checker = None

            now_perf = time.perf_counter()
            if now_perf - _esp_cfg_last_refresh >= _esp_cfg_refresh_interval:
                _esp_cfg_last_refresh = now_perf
                try:
                    show_t = bool(getattr(cfg, 'esp_show_t', show_t))
                    show_ct = bool(getattr(cfg, 'esp_show_ct', show_ct))
                    draw_aimbot_fov = bool(getattr(cfg, 'draw_aimbot_fov', draw_aimbot_fov))
                    dynamic_fov_enabled = bool(getattr(cfg, 'dynamic_fov_enabled', dynamic_fov_enabled))
                    base_fov_deg = float(getattr(cfg, 'FOV', base_fov_deg))
                    dynamic_fov_max_distance = float(getattr(cfg, 'dynamic_fov_max_distance', dynamic_fov_max_distance))
                    dynamic_fov_min_scale = float(getattr(cfg, 'dynamic_fov_min_scale', dynamic_fov_min_scale))
                    dynamic_fov_max_scale = float(getattr(cfg, 'dynamic_fov_max_scale', dynamic_fov_max_scale))
                    game_horizontal_fov = float(getattr(cfg, 'game_horizontal_fov', game_horizontal_fov))
                    spectator_list_enabled = bool(getattr(cfg, 'spectator_list_enabled', False))
                except Exception:
                    pass
                try:
                    box_esp_enabled = bool(FLAGS.get('box_esp_enabled', box_esp_enabled))
                    hp_bar_enabled = bool(FLAGS.get('hp_bar_enabled', hp_bar_enabled))
                    skeleton_esp_enabled = bool(FLAGS.get('skeleton_esp_enabled', skeleton_esp_enabled))
                    name_esp_enabled = bool(FLAGS.get('name_esp_enabled', name_esp_enabled))
                except Exception:
                    pass
                # Allow runtime tuning of ESP FPS and antialiasing from Config.
                try:
                    max_fps_val = getattr(cfg, 'esp_max_fps', None)
                    if max_fps_val is not None:
                        overlay.fps = max(0, int(max_fps_val))
                except Exception:
                    pass
                try:
                    aa_val = getattr(cfg, 'esp_antialiasing', None)
                    if aa_val is not None:
                        setattr(overlay, 'use_antialiasing', bool(aa_val))
                except Exception:
                    pass
            cfg = Config
            try:
                draw_fps = bool(getattr(cfg, 'esp_draw_fps', False))
            except Exception:
                draw_fps = False
            if draw_fps:
                now = time.time()
                dt = max(now - last_frame_time, 1e-06)
                inst_fps = 1.0 / dt
                alpha = 0.1
                smoothed_fps = inst_fps if smoothed_fps <= 0.0 else (1.0 - alpha) * smoothed_fps + alpha * inst_fps
                last_frame_time = now
                try:
                    draw_fps_box(overlay, smoothed_fps)
                except Exception:
                    pass


            # Spectator list overlay
            try:
                if spectator_list_enabled and spectator_list is not None:
                    specs = spectator_list.GetSpectatorsCached()
                    draw_spectator_list(overlay, specs)
            except Exception:
                pass


            hide_from_capture = bool(getattr(cfg, 'hide_esp_from_capture', False))
            _set_overlay_capture_excluded(overlay, hide_from_capture)
            try:
                panic_key_name = getattr(cfg, 'panic_key', '') or ''
            except Exception:
                panic_key_name = ''
            if panic_key_name:
                try:
                    vk = get_vk_code(panic_key_name)
                except Exception:
                    vk = None
                if vk:
                    global _PANIC_ESP_HIDDEN
                    try:
                        if user32.GetAsyncKeyState(vk) & 1:
                            _PANIC_ESP_HIDDEN = not _PANIC_ESP_HIDDEN
                    except Exception:
                        pass
            if _PANIC_ESP_HIDDEN:
                try:
                    overlay.end_scene()
                except Exception:
                    pass
                continue
            if VISCHECK_AVAILABLE and vis_checker and matchmaking_base and _esp_vis_enabled(cfg):
                auto_map_loader(handle, matchmaking_base, vis_checker)
                if getattr(cfg, 'visibility_map_reload_needed', False):
                    try:
                        map_path = getattr(cfg, 'visibility_map_path', '')
                        if map_path and os.path.exists(map_path):
                            current_map = vis_checker.get_current_map() if vis_checker.is_map_loaded() else ''
                            if current_map == map_path:
                                pass
                            else:
                                if vis_checker.is_map_loaded():
                                    vis_checker.unload_map()
                                if vis_checker.load_map(map_path):
                                    setattr(cfg, 'visibility_map_loaded', True)
                                else:
                                    setattr(cfg, 'visibility_map_loaded', False)
                        elif vis_checker.is_map_loaded():
                            current_map = vis_checker.get_current_map()
                            vis_checker.unload_map()
                            setattr(cfg, 'visibility_map_loaded', False)
                        setattr(cfg, 'visibility_map_reload_needed', False)
                    except Exception:
                        setattr(cfg, 'visibility_map_reload_needed', False)
            matrix = read_matrix(handle, base + Offsets.dwViewMatrix)
            w, h = (overlay.width, overlay.height)
            local_pos = None
            if reader is not None:
                try:
                    lpawn = reader.read(base + Offsets.dwLocalPlayerPawn, 'long')
                    if lpawn:
                        raw_lp = reader.read_vec3(lpawn + Offsets.m_vOldOrigin)
                        if raw_lp is not None:
                            if hasattr(raw_lp, 'x'):
                                local_pos = raw_lp
                            else:
                                local_pos = Vec3(raw_lp[0], raw_lp[1], raw_lp[2])
                except Exception:
                    local_pos = None
            entities = list(get_entities(handle, base))
            if local_pos is None:
                for ent in entities:
                    if getattr(ent, 'is_local', False) or getattr(ent, 'is_local_player', False):
                        if ent.pos is not None:
                            p = ent.pos
                            if hasattr(p, 'x'):
                                local_pos = p
                            else:
                                local_pos = Vec3(p[0], p[1], p[2])
                        break
            render_list = []
            for ent in entities:
                if ent.hp <= 0 or ent.pos is None:
                    continue
                if ent.team == 2 and (not show_t):
                    continue
                if ent.team == 3 and (not show_ct):
                    continue
                now_ent = time.perf_counter()
                bones = ent.get_bone_positions({head_bone_index}, now=now_ent)
                head_pos = bones.get(head_bone_index)
                if not head_pos:
                    continue
                try:
                    feet2d = w2s(matrix, ent.pos, w, h)
                    head2d = w2s(matrix, head_pos, w, h)
                except Exception:
                    continue
                box_h = (feet2d['y'] - head2d['y']) * 1.08
                if box_h <= 1:
                    continue
                box_w = box_h / 2.0
                x = head2d['x'] - box_w / 2.0
                y = head2d['y'] - box_h * 0.08
                is_visible_for_skeleton = None
                if _esp_vis_enabled(cfg) and VISCHECK_AVAILABLE and (vis_checker is not None) and (local_pos is not None):
                    try:
                        is_visible_for_skeleton = check_player_visibility(local_pos, ent.pos, vis_checker)
                    except Exception:
                        is_visible_for_skeleton = None
                render_list.append({'ent': ent, 'head2d': head2d, 'feet2d': feet2d, 'box_x': x, 'box_y': y, 'box_w': box_w, 'box_h': box_h, 'is_visible': is_visible_for_skeleton})
            if draw_aimbot_fov and base_fov_deg > 0.0:
                try:
                    w, h = (overlay.width, overlay.height)
                    horiz_fov = game_horizontal_fov or 90.0
                    if horiz_fov <= 0.0:
                        horiz_fov = 90.0
                    if dynamic_fov_enabled and local_pos is not None and render_list:
                        try:
                            if hasattr(local_pos, 'x'):
                                lx, ly, lz = (float(local_pos.x), float(local_pos.y), float(local_pos.z))
                            else:
                                lx, ly, lz = (float(local_pos[0]), float(local_pos[1]), float(local_pos[2]))
                        except Exception:
                            lx = ly = lz = None
                        if lx is not None:
                            max_dist = dynamic_fov_max_distance or 3000.0
                            if max_dist <= 0.0:
                                max_dist = 3000.0
                            min_scale = dynamic_fov_min_scale
                            max_scale = dynamic_fov_max_scale
                            if max_scale < min_scale:
                                max_scale = min_scale
                            for item in render_list:
                                ent = item['ent']
                                pos3 = getattr(ent, 'pos', None)
                                if pos3 is None:
                                    continue
                                try:
                                    if hasattr(pos3, 'x'):
                                        ex, ey, ez = (float(pos3.x), float(pos3.y), float(pos3.z))
                                    else:
                                        ex, ey, ez = (float(pos3[0]), float(pos3[1]), float(pos3[2]))
                                except Exception:
                                    continue
                                dx3 = ex - lx
                                dy3 = ey - ly
                                dz3 = ez - lz
                                dist = (dx3 * dx3 + dy3 * dy3 + dz3 * dz3) ** 0.5
                                t = max(0.0, min(dist / max_dist, 1.0))
                                scale = min_scale + (max_scale - min_scale) * t
                                fov_deg = base_fov_deg * scale
                                half_side = fov_deg / horiz_fov * (w / 1.5)
                                if half_side <= 2.0:
                                    continue
                                head2d = item['head2d']
                                feet2d = item['feet2d']
                                cx = head2d['x']
                                cy = (head2d['y'] + feet2d['y']) / 2.0
                                fx = cx - half_side
                                fy = cy - half_side
                                size = half_side * 2.0
                                overlay.draw_box(fx, fy, size, size, (255, 255, 255))
                    else:
                        half_side = base_fov_deg / horiz_fov * (w / 1.5)
                        if half_side > 2.0:
                            cx = w / 2.0
                            cy = h / 2.0
                            fx = cx - half_side
                            fy = cy - half_side
                            size = half_side * 2.0
                            overlay.draw_box(fx, fy, size, size, (255, 255, 255))
                except Exception:
                    pass
            if box_esp_enabled:
                for item in render_list:
                    ent = item['ent']
                    x = item['box_x']
                    y = item['box_y']
                    box_w = item['box_w']
                    box_h = item['box_h']
                    is_visible_for_skeleton = item['is_visible']
                    col = FLAGS['color_t'] if ent.team == 2 else FLAGS['color_ct']
                    if is_visible_for_skeleton is not None:
                        if ent.team == 2:
                            if is_visible_for_skeleton:
                                col = FLAGS.get('color_vis_t_visible', col)
                            else:
                                col = FLAGS.get('color_vis_t_invisible', col)
                        elif is_visible_for_skeleton:
                            col = FLAGS.get('color_vis_ct_visible', col)
                        else:
                            col = FLAGS.get('color_vis_ct_invisible', col)
                    overlay.draw_box(x, y, box_w, box_h, col)
            if name_esp_enabled:
                for item in render_list:
                    ent = item['ent']
                    x = item['box_x']
                    y = item['box_y']
                    box_w = item['box_w']
                    name = getattr(ent, 'name', '') or ''
                    if not name:
                        continue
                    try:
                        if getattr(ent, 'team', 0) == 2:
                            name_color = FLAGS.get('color_name_t', FLAGS.get('color_t', (255, 0, 0)))
                        elif getattr(ent, 'team', 0) == 3:
                            name_color = FLAGS.get('color_name_ct', FLAGS.get('color_ct', (0, 128, 255)))
                        else:
                            name_color = FLAGS.get('color_name_other', (255, 255, 255))
                    except Exception:
                        name_color = (255, 255, 255)
                    overlay.draw_text(x, y - 14, str(name), name_color)
            if hp_bar_enabled:
                for item in render_list:
                    ent = item['ent']
                    x = item['box_x']
                    y = item['box_y']
                    box_h = item['box_h']
                    hp_ratio = max(0.0, min(1.0, ent.hp / 100.0))
                    bar_h = box_h * hp_ratio
                    if hp_ratio > 0.66:
                        hp_color = (0, 255, 0)
                    elif hp_ratio > 0.33:
                        hp_color = (255, 255, 0)
                    else:
                        hp_color = (255, 0, 0)
                    overlay.draw_filled_rect(x - 5, y + (box_h - bar_h), 3, bar_h, hp_color)
            if skeleton_esp_enabled:
                for item in render_list:
                    ent = item['ent']
                    is_visible_for_skeleton = item['is_visible']
                    render_bone_esp(overlay, ent, matrix, is_visible_for_skeleton)
            
            # === NEW ESP FEATURES ===
            
            # Crosshair
            draw_crosshair(overlay, cfg)
            
            # Get entity list base for weapon/money/flash/scope ESP
            entity_list_base = safe_read_uint64(handle, base + Offsets.dwEntityList)
            
            # Weapon, Money, Flash, Scope ESP
            try:
                weapon_esp_enabled = bool(getattr(cfg, 'weapon_esp_enabled', False))
                money_esp_enabled = bool(getattr(cfg, 'money_esp_enabled', False))
                flash_esp_enabled = bool(getattr(cfg, 'flash_esp_enabled', False))
                scope_esp_enabled = bool(getattr(cfg, 'scope_esp_enabled', False))
                visible_only = bool(getattr(cfg, 'visible_only_esp', False))
                
                if weapon_esp_enabled or money_esp_enabled or flash_esp_enabled or scope_esp_enabled:
                    for item in render_list:
                        ent = item['ent']
                        x = item['box_x']
                        y = item['box_y']
                        box_w = item['box_w']
                        box_h = item['box_h']
                        is_visible_check = item['is_visible']
                        
                        # Skip if visible_only mode and not visible
                        if visible_only and is_visible_check is False:
                            continue
                        
                        y_offset = 0
                        
                        # Weapon ESP (right side of box)
                        if weapon_esp_enabled and entity_list_base:
                            try:
                                weapon_name = get_weapon_name_simple(handle, ent.pawn, entity_list_base, Offsets)
                                if weapon_name:
                                    weapon_color = getattr(cfg, 'color_weapon_text', (200, 200, 255))
                                    overlay.draw_text(x + box_w + 5, y + y_offset, weapon_name, weapon_color)
                                    y_offset += 14
                            except Exception:
                                pass
                        
                        # Money ESP (right side of box)
                        if money_esp_enabled:
                            try:
                                money = getattr(ent, 'money', 0)
                                if money > 0:
                                    money_color = getattr(cfg, 'color_money_text', (0, 255, 255))
                                    overlay.draw_text(x + box_w + 5, y + y_offset, f"${money}", money_color)
                                    y_offset += 14
                            except Exception:
                                pass
                        
                        # Flash ESP (indicator when player is flashed)
                        if flash_esp_enabled:
                            try:
                                flash_offset = getattr(Offsets, 'm_flFlashDuration', None)
                                if flash_offset:
                                    flash_duration = read_float(handle, ent.pawn + flash_offset)
                                    if flash_duration > 0:
                                        flash_color = getattr(cfg, 'color_flash_indicator', (255, 255, 0))
                                        overlay.draw_text(x + box_w + 5, y + y_offset, "FLASHED", flash_color)
                                        y_offset += 14
                            except Exception:
                                pass
                        
                        # Scope ESP (indicator when player is scoped)
                        if scope_esp_enabled:
                            try:
                                scope_offset = getattr(Offsets, 'm_bIsScoped', None)
                                if scope_offset:
                                    is_scoped = bool(read_int(handle, ent.pawn + scope_offset))
                                    if is_scoped:
                                        scope_color = getattr(cfg, 'color_scope_indicator', (0, 255, 255))
                                        overlay.draw_text(x + box_w + 5, y + y_offset, "SCOPED", scope_color)
                                        y_offset += 14
                            except Exception:
                                pass
            except Exception:
                pass
            
            
            # Map Status Display
            try:
                map_status_enabled = bool(getattr(cfg, 'map_status_enabled', False))
                if map_status_enabled and matchmaking_base:
                    map_name = get_current_map_name(handle, matchmaking_base)
                    if map_name and map_name != '<empty>':
                        draw_map_status(overlay, map_name)
            except Exception:
                pass

            
            # Team List Display
            try:
                team_list_enabled = bool(getattr(cfg, 'team_list_enabled', False))
                if team_list_enabled and entities:
                    t_players = []
                    ct_players = []

                    for ent in entities:
                        if ent.hp <= 0:
                            continue
                        name = getattr(ent, 'name', 'Unknown')
                        hp = getattr(ent, 'hp', 0)
                        team = getattr(ent, 'team', 0)

                        if team == 2:  # T
                            t_players.append(f"{name} [{hp}]")
                        elif team == 3:  # CT
                            ct_players.append(f"{name} [{hp}]")

                    draw_team_list(overlay, t_players, ct_players)
            except Exception:
                pass

            
        except Exception:
            pass
        overlay.end_scene()
if __name__ == '__main__':
    main()