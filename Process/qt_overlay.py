from __future__ import annotations
import os, sys, time, threading
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from typing import List, Tuple, Optional

try:
    from PyQt5.QtCore import Qt, QRect
    from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QGuiApplication
    from PyQt5.QtWidgets import QApplication, QWidget
except Exception as _e:  # pragma: no cover - PyQt5 missing at import time
    # We keep import-time failures soft so the rest of the script can still run.
    QApplication = None  # type: ignore
    QGuiApplication = None  # type: ignore
    QWidget = object  # type: ignore

try:
    from Process.config import Config  # type: ignore
except Exception:
    Config = None  # type: ignore

_global_qapp: Optional[QApplication] = None
_global_qapp_lock = threading.Lock()


def ensure_qapp() -> QApplication:
    """Return a global QApplication instance, creating it if needed."""
    global _global_qapp
    with _global_qapp_lock:
        if _global_qapp is not None:
            return _global_qapp
        if QApplication is None:
            raise RuntimeError("PyQt5 is required for the Qt overlay but is not installed")
        app = QApplication.instance()
        if app is None:
            # We do not call exec_(); the main loop is driven via processEvents()
            app = QApplication(sys.argv or ["gscript_overlay"])
        _global_qapp = app  # type: ignore[assignment]
        return app  # type: ignore[return-value]


class _OverlayWidget(QWidget):
    """Transparent, top-most widget that paints primitives owned by an Overlay."""

    def __init__(self, owner: "QtOverlay", title: str):
        super().__init__()
        self._owner = owner
        self.setWindowTitle(title or "GScript Overlay")
        # Top-most, borderless, tool window (no taskbar / Alt+Tab entry)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        # Translucent background + no background erase
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        # Make overlay click-through so the game keeps focus/input.
        try:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        try:
            # Qt 5.15+; on earlier versions this will just be ignored.
            self.setWindowFlag(Qt.WindowTransparentForInput, True)
        except Exception:
            pass

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            self._owner.width = geo.width()
            self._owner.height = geo.height()
            self.setGeometry(geo)
        else:
            # Reasonable default; will still cover most viewports.
            self._owner.width = 1920
            self._owner.height = 1080
            self.setGeometry(0, 0, self._owner.width, self._owner.height)

        self.show()

        # Small object caches to avoid re-allocating QPen/QBrush every primitive.
        self._pen_cache = {}
        self._brush_cache = {}

    def paintEvent(self, event):  # type: ignore[override]
        # Snapshot primitives so ESP/menu threads can keep appending while we paint.
        primitives = self._owner._snapshot_primitives()
        if not primitives:
            return
        painter = QPainter(self)
        # Text remains smoothed, but full-scene antialiasing is optional for FPS.
        if getattr(self._owner, "use_antialiasing", False):
            painter.setRenderHint(QPainter.Antialiasing, True)
        else:
            painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        for prim in primitives:
            kind = prim[0]
            if kind == "rect":
                _, x, y, w, h, color, filled = prim
                r, g, b, a = color
                if filled:
                    painter.setPen(Qt.NoPen)
                    brush_key = (r, g, b, a)
                    brush = self._brush_cache.get(brush_key)
                    if brush is None:
                        brush = QBrush(QColor(r, g, b, a))
                        self._brush_cache[brush_key] = brush
                    painter.setBrush(brush)
                else:
                    pen_key = (r, g, b, a, 1)
                    pen = self._pen_cache.get(pen_key)
                    if pen is None:
                        pen = QPen(QColor(r, g, b, a))
                        pen.setWidth(1)
                        self._pen_cache[pen_key] = pen
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRect(int(x), int(y), int(w), int(h)))
            elif kind == "line":
                _, x1, y1, x2, y2, color, width = prim
                r, g, b, a = color
                width_i = max(1, int(width))
                pen_key = (r, g, b, a, width_i)
                pen = self._pen_cache.get(pen_key)
                if pen is None:
                    pen = QPen(QColor(r, g, b, a))
                    pen.setWidth(width_i)
                    self._pen_cache[pen_key] = pen
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            elif kind == "circle":
                _, cx, cy, r_, color, filled = prim
                r, g, b, a = color
                if filled:
                    painter.setPen(Qt.NoPen)
                    brush_key = (r, g, b, a)
                    brush = self._brush_cache.get(brush_key)
                    if brush is None:
                        brush = QBrush(QColor(r, g, b, a))
                        self._brush_cache[brush_key] = brush
                    painter.setBrush(brush)
                else:
                    pen_key = (r, g, b, a, 1)
                    pen = self._pen_cache.get(pen_key)
                    if pen is None:
                        pen = QPen(QColor(r, g, b, a))
                        pen.setWidth(1)
                        self._pen_cache[pen_key] = pen
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(
                    int(cx - r_), int(cy - r_), int(2 * r_), int(2 * r_)
                )
            elif kind == "text":
                _, x, y, text, color = prim
                r, g, b, a = color
                painter.setPen(QColor(r, g, b, a))
                painter.drawText(int(x), int(y), str(text))

        painter.end()


class QtOverlay:
    """Qt-based overlay providing the same primitive API as the old GDI overlay."""

    def __init__(self):
        # These are populated once the widget is created.
        self.width: int = 1920
        self.height: int = 1080

        # FPS cap for the ESP overlay. Can be overridden from Config.esp_max_fps.
        fps_default = 144
        try:
            if Config is not None:
                fps_default = int(getattr(Config, "esp_max_fps", fps_default) or fps_default)
        except Exception:
            pass
        self.fps: int = max(0, int(fps_default))

        # Optional antialiasing toggle (off by default for better FPS).
        use_aa_default = False
        try:
            if Config is not None:
                use_aa_default = bool(getattr(Config, "esp_antialiasing", use_aa_default))
        except Exception:
            pass
        self.use_antialiasing: bool = bool(use_aa_default)

        self._title: str = "GScript Overlay"
        self._widget: Optional[_OverlayWidget] = None
        self._last_frame: float = 0.0
        self._primitives: List[tuple] = []
        self._lock = threading.Lock()
        self._hwnd: Optional[int] = None

    # ---- compatibility surface ----
    @property
    def hwnd(self) -> Optional[int]:
        """Expose underlying HWND for SetWindowDisplayAffinity."""
        if self._hwnd is not None:
            return self._hwnd
        w = self._widget
        if w is None:
            return None
        try:
            self._hwnd = int(w.winId())
        except Exception:
            self._hwnd = None
        return self._hwnd

    # Old GDI overlay had .init(title); keep that.
    def init(self, title: str = "GScript Overlay") -> None:
        self._title = title
        app = ensure_qapp()
        del app  # noqa: F841
        if self._widget is None:
            self._widget = _OverlayWidget(self, title)

    # ---- internal helpers ----
    def _color_to_rgba(self, color) -> Tuple[int, int, int, int]:
        try:
            r, g, b = color
        except Exception:
            r = g = b = 255
        return int(r) & 255, int(g) & 255, int(b) & 255, 255

    def _push_prim(self, prim: tuple) -> None:
        with self._lock:
            self._primitives.append(prim)

    def _snapshot_primitives(self) -> List[tuple]:
        with self._lock:
            return list(self._primitives)

    # ---- frame lifecycle ----
    def begin_scene(self) -> bool:
        """Start a frame: FPS pacing + primitive clear."""
        # FPS cap roughly like the old overlay.
        if self.fps:
            now = time.perf_counter()
            min_dt = 1.0 / float(self.fps)
            dt = now - self._last_frame
            if dt < min_dt:
                time.sleep(min_dt - dt)
            self._last_frame = time.perf_counter()

        if self._widget is None:
            try:
                self.init(self._title)
            except Exception:
                return False

        with self._lock:
            self._primitives.clear()
        return True

    def end_scene(self) -> None:
        """Trigger repaint and pump the Qt event loop once."""
        if self._widget is None:
            return
        try:
            self._widget.update()
            app = ensure_qapp()
            app.processEvents()
        except Exception:
            # Soft-fail: we don't want ESP/menu to crash just because Qt hiccuped.
            pass

    # ---- primitive draw API ----
    def draw_box(self, x, y, w, h, color) -> None:
        rgba = self._color_to_rgba(color)
        self._push_prim(("rect", float(x), float(y), float(w), float(h), rgba, False))

    def draw_line(self, x1, y1, x2, y2, color, width: int = 1) -> None:
        rgba = self._color_to_rgba(color)
        self._push_prim(("line", float(x1), float(y1), float(x2), float(y2), rgba, int(width)))

    def draw_circle(self, x, y, r, color) -> None:
        rgba = self._color_to_rgba(color)
        self._push_prim(("circle", float(x), float(y), float(r), rgba, False))

    def draw_filled_rect(self, x, y, w, h, color) -> None:
        rgba = self._color_to_rgba(color)
        self._push_prim(("rect", float(x), float(y), float(w), float(h), rgba, True))

    def draw_text(self, x, y, text, color) -> None:
        rgba = self._color_to_rgba(color)
        self._push_prim(("text", float(x), float(y), str(text), rgba))
