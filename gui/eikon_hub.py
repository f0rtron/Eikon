#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Eikon Hub  ·  Production Dashboard  ·  PyQt6
Cyprus + Sand Design System
v2  —  DWM shadow · Solid/pulse LED · No-flicker metrics
        Animated hover cards · DPI-aware · Dark/Light audit
"""

import sys, os, re, time, socket, logging, threading, subprocess, ctypes
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFrame, QTabWidget, QTextEdit,
    QGridLayout, QDialog, QLineEdit, QScrollArea, QSizeGrip,
    QGraphicsDropShadowEffect, QProgressBar, QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal,
    QPropertyAnimation, QEasingCurve, QPoint, QSettings,
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QBrush

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS  ·  Cyprus + Sand
# ══════════════════════════════════════════════════════════════════════════════

# Font stack: Segoe UI on Windows, Inter/system on macOS/Linux
FONT_UI   = "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue"
FONT_MONO = '"Cascadia Code","JetBrains Mono","Consolas",monospace'

SP_XS, SP_SM, SP_MD, SP_LG, SP_XL, SP_XXL = 4, 8, 12, 16, 24, 32

# ── Brand (sidebar is always Cyprus regardless of theme) ─────────────────────
CY_DEEP    = "#004643"
CY_MID     = "#005F5A"
CY_BRIGHT  = "#00827D"
CY_DARKEST = "#00312F"
CY_ACCENT  = "#00C2BA"
SD_WARM    = "#EDE9E1"

# ── Semantic: LED / painted widgets (mode-independent — large enough to see) ─
C_SUCCESS_LED = "#22C55E"
C_WARNING_LED = "#E8A838"
C_ERROR_LED   = "#EF4444"

# ── Semantic: text / inline styles (mode-aware for WCAG-AA compliance) ────────
#   Dark:  bright on dark surfaces  |  Light:  darkened on near-white surfaces
C_SUCCESS_DARK = "#22C55E";  C_SUCCESS_LIGHT = "#15803D"   # contrast ≥ 4.5 on white
C_WARNING_DARK = "#E8A838";  C_WARNING_LIGHT = "#A35500"   # contrast ≥ 4.5 on white
C_ERROR_DARK   = "#EF4444";  C_ERROR_LIGHT   = "#B91C1C"   # contrast ≥ 4.5 on white

# ── Console log palette (mode-aware for WCAG-AA compliance) ──────────────────
LOG_COLORS_DARK = {
    "INFO":    "#6B9C9A",
    "SUCCESS": "#22C55E",
    "WARN":    "#E8A838",
    "ERROR":   "#EF4444",
    "OUT":     "#7BAAA8",
}
LOG_COLORS_LIGHT = {
    "INFO":    "#4A7B79",
    "SUCCESS": "#15803D",
    "WARN":    "#A35500",
    "ERROR":   "#B91C1C",
    "OUT":     "#3D7A78",
}


# ── Shadow factory ────────────────────────────────────────────────────────────

def _new_shadow(blur: int = 16, dx: int = 0, dy: int = 3,
                alpha: int = 28) -> QGraphicsDropShadowEffect:
    """Always returns a fresh instance (Qt allows only one effect per widget)."""
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(blur)
    fx.setOffset(dx, dy)
    fx.setColor(QColor(0, 0, 0, alpha))
    return fx


# ══════════════════════════════════════════════════════════════════════════════
#  THEME ENGINE  ·  Full dark / light audit
# ══════════════════════════════════════════════════════════════════════════════
#
#  DARK SURFACE HIERARCHY
#   BG #0A1918  <  SURF #0D2120  <  CARD #132B29
#   Muted text  #6B9C9A  →  5.1:1 on CARD  ✓ WCAG AA
#
#  LIGHT SURFACE HIERARCHY
#   BG #EAE6DE  <  SURF #F5F2EB  <  CARD #FDFCFA
#   Muted text  #5C5C55  →  5.4:1 on white  ✓ WCAG AA
#   Input bg    #E3DFDA  →  clearly distinct from CARD
#   Card hover  #EAF6F5  →  teal tint, visible without being harsh
#   Tab accent  #007570  →  4.6:1 on white  ✓ WCAG AA
#
def build_qss(dark: bool) -> str:
    if dark:
        BG      = "#0A1918"; SURF    = "#0D2120"; CARD    = "#132B29"
        CARD_H  = "#183330"; BORD    = "#1F4240"; TEXT    = "#EDE9E1"
        MUT     = "#6B9C9A"; SCR     = "#1F4240"; DLG     = "#0D2120"
        INP     = "#0A1918"; INP_B   = "#1F4240"; TAB_ACC = CY_ACCENT
    else:
        BG      = "#EAE6DE"; SURF    = "#F5F2EB"; CARD    = "#FDFCFA"
        CARD_H  = "#EAF6F5"; BORD    = "#C8C3BB"; TEXT    = "#1C2221"
        MUT     = "#5C5C55"; SCR     = "#B5B0A7"; DLG     = "#F5F2EB"
        INP     = "#E3DFDA"; INP_B   = "#C8C3BB"; TAB_ACC = "#007570"

    return f"""
    /* ── Base ────────────────────────────────────────────── */
    QWidget {{
        font-family: "{FONT_UI}"; font-size: 13px; color: {TEXT};
    }}
    QMainWindow {{ background: {BG}; }}

    /* ── Sidebar — always Cyprus Deep ────────────────────── */
    #Sidebar {{ background: {CY_DEEP}; border-right: 1px solid {CY_MID}; }}
    #Sidebar QLabel {{ color: {SD_WARM}; background: transparent; }}
    #BrandTitle {{
        font-size: 20px; font-weight: 700;
        color: {SD_WARM}; letter-spacing: 0.5px;
    }}
    #BrandSub {{ font-size: 9px; color: #6B8E8A; letter-spacing: 1.5px; }}
    #SidebarDivider {{ background: {CY_MID}; max-height: 1px; border: none; }}
    #Sidebar QPushButton {{
        background: transparent; color: {SD_WARM}; border: none;
        border-radius: 8px; padding: 10px 14px; text-align: left;
        font-size: 13px; font-weight: 500;
    }}
    #Sidebar QPushButton:hover {{ background: {CY_MID}; color: #fff; }}
    #Sidebar QPushButton:pressed {{ background: {CY_BRIGHT}; }}
    #CamLabel {{
        color: #6B8E8A; font-size: 9px;
        font-weight: 700; letter-spacing: 1.5px;
    }}
    QComboBox#CamCombo {{
        background: {CY_DARKEST}; color: {SD_WARM};
        border: 1px solid {CY_MID}; border-radius: 6px;
        padding: 6px 10px; font-size: 12px;
    }}
    QComboBox#CamCombo::drop-down {{ border: none; width: 20px; }}
    QComboBox#CamCombo QAbstractItemView {{
        background: {CY_DARKEST}; color: {SD_WARM};
        selection-background-color: {CY_BRIGHT};
        border: 1px solid {CY_MID}; outline: none;
    }}
    #SidebarStatusCard {{
        background: {CY_DARKEST}; border: 1px solid {CY_MID}; border-radius: 10px;
    }}
    #SidebarStatusCard QLabel {{ background: transparent; }}
    #UtilBtn {{
        background: {CY_DARKEST}; color: #6B8E8A;
        border: 1px solid {CY_MID}; border-radius: 6px;
        padding: 7px 10px; font-size: 11px; font-weight: 600;
    }}
    #UtilBtn:hover {{ background: {CY_MID}; color: {SD_WARM}; }}
    #VersionLabel {{ color: #4A7573; font-size: 9px; letter-spacing: 0.5px; }}

    /* ── Custom title bar ─────────────────────────────────── */
    #TitleBar {{ background: {SURF}; border-bottom: 1px solid {BORD}; }}
    #TitleText {{ font-size: 13px; font-weight: 600; color: {TEXT}; letter-spacing: 0.3px; }}
    #TitleClock {{ font-size: 11px; color: {MUT}; }}
    #WinBtn {{
        background: transparent; border: none; border-radius: 4px;
        color: {MUT}; font-size: 14px; padding: 0;
        min-width: 40px; min-height: 32px;
    }}
    #WinBtn:hover {{ background: {BORD}; color: {TEXT}; }}
    #WinBtnClose {{
        background: transparent; border: none; border-radius: 4px;
        color: {MUT}; font-size: 14px; padding: 0;
        min-width: 40px; min-height: 32px;
    }}
    #WinBtnClose:hover {{ background: #C0392B; color: white; }}

    /* ── 2-px task progress bar ───────────────────────────── */
    QProgressBar#TaskBar {{
        background: transparent; border: none;
        max-height: 2px; min-height: 2px;
    }}
    QProgressBar#TaskBar::chunk {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {CY_BRIGHT}, stop:1 {CY_ACCENT});
        border-radius: 1px;
    }}

    /* ── Main content area ────────────────────────────────── */
    #MainPanel {{ background: {BG}; }}
    #SectionLabel {{
        font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: {MUT};
    }}

    /* ── Action cards ─────────────────────────────────────── */
    #ActionCard {{
        background: {CARD}; border: 1px solid {BORD}; border-radius: 14px;
        border-left: 3px solid {CY_BRIGHT};
    }}
    #ActionCard:hover {{
        border-color: {CY_ACCENT}; background: {CARD_H};
        border-left: 3px solid {CY_ACCENT};
    }}
    #CardTitle {{ font-size: 13px; font-weight: 700; color: {TEXT}; background: transparent; }}
    #CardDesc  {{ font-size: 11px; color: {MUT}; background: transparent; }}
    #CardBtn {{
        background: {CY_DEEP}; color: {SD_WARM}; border: none;
        border-radius: 6px; padding: 7px 14px;
        font-size: 11px; font-weight: 700; letter-spacing: 0.3px;
    }}
    #CardBtn:hover {{ background: {CY_BRIGHT}; color: #fff; }}
    #CardBtn:pressed {{ background: {CY_DARKEST}; }}
    #IconCircle {{
        border-radius: 22px; min-width: 44px; max-width: 44px;
        min-height: 44px; max-height: 44px;
        background: {'#0D2120' if dark else '#E0F0EF'};
    }}
    #IconCircle QLabel {{ background: transparent; }}
    /* ── Sidebar live stats ─────────────────────────────────── */
    #SidebarSection {{
        color: #6B8E8A; font-size: 9px;
        font-weight: 700; letter-spacing: 1.5px;
        background: transparent;
    }}
    #SidebarStatVal {{
        color: {CY_ACCENT}; font-size: 18px; font-weight: 700;
        background: transparent;
    }}
    #SidebarStatLabel {{
        color: #6B8E8A; font-size: 9px; font-weight: 600;
        background: transparent; letter-spacing: 0.3px;
    }}

    /* ── Underline tab bar ────────────────────────────────── */
    QTabWidget::pane {{
        border: none; background: transparent;
        border-top: 1px solid {BORD}; padding-top: {SP_SM}px;
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent; color: {MUT}; border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 18px; margin-right: 4px; font-weight: 600; font-size: 12px;
    }}
    QTabBar::tab:hover {{ color: {TEXT}; }}
    QTabBar::tab:selected {{ color: {TAB_ACC}; border-bottom-color: {TAB_ACC}; }}

    /* ── Status & metrics cards ───────────────────────────── */
    #StatusCard {{ background: {CARD}; border: 1px solid {BORD}; border-radius: 12px; }}
    #StatusCard QLabel {{ background: transparent; }}
    #StatusTitle {{ font-size: 12px; font-weight: 700; color: {TEXT}; }}
    #StatusState {{ font-size: 11px; font-weight: 600; }}
    #StatusDesc  {{ font-size: 10px; color: {MUT}; }}
    #MetricsCard {{ background: {CARD}; border: 1px solid {BORD}; border-radius: 12px; }}
    #MetricsCard QLabel {{ background: transparent; }}
    #MetricKey {{ font-size: 12px; font-weight: 600; color: {MUT}; }}
    #MetricVal {{ font-size: 12px; color: {TEXT}; }}

    /* ── Developer console ────────────────────────────────── */
    QTextEdit#Console {{
        background: {CARD}; color: {TEXT}; border: 1px solid {BORD};
        border-radius: 10px; font-family: {FONT_MONO};
        font-size: 12px; padding: 12px;
        selection-background-color: {CY_BRIGHT};
    }}
    #ConsoleTitle {{ font-size: 11px; font-weight: 700; color: {TAB_ACC}; }}
    #ConsoleClearBtn {{
        background: transparent; color: {MUT};
        border: 1px solid {BORD}; border-radius: 5px;
        padding: 4px 12px; font-size: 11px;
    }}
    #ConsoleClearBtn:hover {{ color: {TEXT}; border-color: {TAB_ACC}; }}

    /* ── 6 px slim scrollbars ─────────────────────────────── */
    QScrollBar:vertical {{
        border: none; background: transparent; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {SCR}; min-height: 30px; border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {CY_MID}; }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{ height: 0; background: none; }}
    QScrollBar:horizontal {{
        border: none; background: transparent; height: 6px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {SCR}; min-width: 30px; border-radius: 3px;
    }}

    /* ── Dialogs & inputs ─────────────────────────────────── */
    QDialog   {{ background: {DLG}; }}
    QLineEdit {{
        background: {INP}; color: {TEXT};
        border: 1px solid {INP_B}; border-radius: 7px;
        padding: 9px 12px; font-size: 13px;
        selection-background-color: {CY_BRIGHT};
    }}
    QLineEdit:focus {{ border-color: {CY_ACCENT}; }}

    /* ── Toast overlay ────────────────────────────────────── */
    #Toast {{
        background: {'#152E2C' if dark else '#1A3332'};
        border: 1px solid {CY_MID}; border-radius: 10px;
    }}
    #Toast QLabel {{ background: transparent; color: {SD_WARM}; }}

    QLabel {{ color: {TEXT}; }}
    """


# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA ENUMERATION
# ══════════════════════════════════════════════════════════════════════════════

def enumerate_cameras(max_idx: int = 4):
    import cv2
    import sys
    sources = []
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    for i in range(max_idx):
        cap = None
        try:
            cap = cv2.VideoCapture(i, backend)
            if not cap.isOpened():
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                sources.append((i, f"Camera {i}  ({w}×{h})"))
            cap.release()
        except Exception:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return sources


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ══════════════════════════════════════════════════════════════════════════════

class CameraScanner(QThread):
    finished_signal = pyqtSignal(list)

    def run(self):
        try:
            self.finished_signal.emit(enumerate_cameras(max_idx=4))
        except Exception:
            self.finished_signal.emit([])


class BackendPoller(QThread):
    finished_signal = pyqtSignal(bool, dict)

    def run(self):
        try:
            from config import PORT
            is_up = False
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=1.5):
                    is_up = True
            except OSError:
                pass
            stats = {"total": 0, "encoded": 0, "today": 0}
            if is_up:
                try:
                    from db.connection import db_session
                    from db.models import Student, AttendanceLog
                    with db_session() as session:
                        stats["total"]   = session.query(Student).count()
                        stats["encoded"] = session.query(Student).filter(
                            Student.face_encoding.isnot(None)).count()
                        today = datetime.now().strftime("%Y-%m-%d")
                        stats["today"]   = session.query(AttendanceLog).filter(
                            AttendanceLog.timestamp.like(f"{today}%")).count()
                except Exception:
                    pass
            self.finished_signal.emit(is_up, stats)
        except Exception:
            self.finished_signal.emit(False, {"total": 0, "encoded": 0, "today": 0})


class SubprocessWorker(QThread):
    line_received   = pyqtSignal(str, str)
    finished_signal = pyqtSignal(int)

    def __init__(self, cmd, stream_output=False, is_gui=False):
        super().__init__()
        self.cmd = cmd; self.stream_output = stream_output
        self.is_gui = is_gui; self.proc = None

    def run(self):
        try:
            root = Path(__file__).resolve().parent.parent
            if self.is_gui:
                self.proc = subprocess.Popen(
                    self.cmd, cwd=str(root),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self.proc = subprocess.Popen(
                    self.cmd, cwd=str(root),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                        if sys.platform == "win32" else 0)
                if self.stream_output and self.proc.stdout:
                    for line in self.proc.stdout:
                        s = line.strip()
                        if s:
                            self.line_received.emit(s, "OUT")
            self.proc.wait()
            self.finished_signal.emit(self.proc.returncode)
        except Exception as e:
            self.line_received.emit(f"Subprocess error: {e}", "ERROR")
            self.finished_signal.emit(1)

    def terminate_proc(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
#  FIX 2 · PulsingLED — solid when healthy, pulsing only for warn/error
# ─────────────────────────────────────────────────────────────────────────────
class PulsingLED(QWidget):
    """
    Animated status dot.
      set_pulsing(True)  → gentle alpha cycle  (warn / offline)
      set_pulsing(False) → frozen full opacity  (healthy / online)
    Paint uses proportional fractions of widget rect so it is sharp on any DPI.
    """

    def __init__(self, color: str = C_WARNING_LED, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color   = QColor(color)
        self._alpha   = 255
        self._dir     = -1        # -1 fading  / +1 brightening
        self._pulsing = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(35)     # ~28 fps  —  smooth but cheap

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def set_pulsing(self, on: bool):
        """True → animate; False → freeze at full brightness (solid)."""
        self._pulsing = on
        if not on:
            self._alpha = 255
        self.update()

    def _tick(self):
        if not self._pulsing:
            return
        self._alpha += self._dir * 7
        if self._alpha <= 55:
            self._alpha = 55;  self._dir = 1
        elif self._alpha >= 255:
            self._alpha = 255; self._dir = -1
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # Outer glow — full extent of widget
        glow = QColor(self._color); glow.setAlpha(self._alpha // 5)
        p.setBrush(QBrush(glow))
        p.drawEllipse(0, 0, w, h)

        # Core dot — 56 % of widget diameter (proportional → DPI-safe)
        r = w * 0.28
        core = QColor(self._color); core.setAlpha(self._alpha)
        p.setBrush(QBrush(core))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  FIX 4 · HoverCard — 120 ms animated shadow elevation
# ─────────────────────────────────────────────────────────────────────────────
class HoverCard(QFrame):
    """
    Action card with smooth shadow depth animation.
    QPropertyAnimation drives QGraphicsDropShadowEffect.blurRadius,
    which is a proper Qt property and fully animatable in PyQt6.
    """

    _BLUR_REST  = 14
    _BLUR_HOVER = 30
    _DY_REST    = 3
    _DY_HOVER   = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumHeight(164)

        self._fx = QGraphicsDropShadowEffect()
        self._fx.setBlurRadius(self._BLUR_REST)
        self._fx.setOffset(0, self._DY_REST)
        self._fx.setColor(QColor(0, 0, 0, 28))
        self.setGraphicsEffect(self._fx)

        self._anim = QPropertyAnimation(self._fx, b"blurRadius")
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        self._fx.setColor(QColor(0, 66, 63, 52))
        self._fx.setOffset(0, self._DY_HOVER)
        self._anim.stop()
        self._anim.setStartValue(int(self._fx.blurRadius()))
        self._anim.setEndValue(self._BLUR_HOVER)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._fx.setColor(QColor(0, 0, 0, 28))
        self._fx.setOffset(0, self._DY_REST)
        self._anim.stop()
        self._anim.setStartValue(int(self._fx.blurRadius()))
        self._anim.setEndValue(self._BLUR_REST)
        self._anim.start()
        super().leaveEvent(event)


# ── Toast notification ────────────────────────────────────────────────────────

class ToastNotification(QFrame):
    _LEVELS = {
        "success": (C_SUCCESS_LED, "✓"),
        "warn":    (C_WARNING_LED, "⚠"),
        "error":   (C_ERROR_LED,   "✕"),
        "info":    (CY_ACCENT,     "◆"),
    }

    def __init__(self, parent: QWidget, message: str,
                 level: str = "info", duration: int = 3200):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setFixedWidth(310)
        color, icon = self._LEVELS.get(level, (CY_ACCENT, "◆"))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(SP_MD, SP_SM, SP_MD, SP_SM)
        lay.setSpacing(SP_SM)

        dot = QLabel(icon)
        dot.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        dot.setStyleSheet(f"color:{color};background:transparent;")
        lay.addWidget(dot)

        lbl = QLabel(message)
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)

        self.adjustSize()
        self.raise_()
        self._start(parent, duration)

    def _start(self, parent: QWidget, duration: int):
        margin   = SP_LG
        target_x = parent.width() - self.width() - margin
        target_y = 60 + margin
        off_x    = parent.width() + 10
        self.move(off_x, target_y)
        self.show()
        self._in = QPropertyAnimation(self, b"pos")
        self._in.setDuration(280)
        self._in.setStartValue(QPoint(off_x, target_y))
        self._in.setEndValue(QPoint(target_x, target_y))
        self._in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._in.start()
        QTimer.singleShot(duration, self._dismiss)

    def _dismiss(self):
        par = self.parent()
        if par is None:
            self.deleteLater(); return
        cur = self.pos()
        out = QPoint(par.width() + 10, cur.y())
        self._out = QPropertyAnimation(self, b"pos")
        self._out.setDuration(220)
        self._out.setStartValue(cur)
        self._out.setEndValue(out)
        self._out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._out.finished.connect(self.deleteLater)
        self._out.start()


# ── Custom title bar ──────────────────────────────────────────────────────────

class TitleBar(QWidget):
    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)
        self._win      = window
        self._drag_pos = None
        self._btn_max  = None
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(SP_LG, 0, SP_SM, 0)
        lay.setSpacing(SP_SM)

        icon_path = (Path(__file__).resolve().parent.parent
                     / "app" / "static" / "img" / "logo_icon_sand.png")
        icon_lbl  = QLabel()
        if icon_path.exists():
            pix = QPixmap(str(icon_path))
            icon_lbl.setPixmap(pix.scaled(22, 22,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            icon_lbl.setText("◈")
            icon_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            icon_lbl.setStyleSheet(f"color:{CY_ACCENT};")
        lay.addWidget(icon_lbl)

        self.title_lbl = QLabel("Eikon — Central Hub")
        self.title_lbl.setObjectName("TitleText")
        lay.addWidget(self.title_lbl)
        lay.addStretch()

        self.clock_lbl = QLabel()
        self.clock_lbl.setObjectName("TitleClock")
        lay.addWidget(self.clock_lbl)
        lay.addSpacing(SP_MD)

        for obj, sym, tip, slot in (
            ("WinBtn",      "⎯",  "Minimize",        self._win.showMinimized),
            ("WinBtn",      "□",  "Maximize/Restore", self._toggle_max),
            ("WinBtnClose", "✕",  "Close",            self._win.close),
        ):
            b = QPushButton(sym)
            b.setObjectName(obj)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            if tip == "Maximize/Restore":
                self._btn_max = b

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
            if self._btn_max: self._btn_max.setText("□")
        else:
            self._win.showMaximized()
            if self._btn_max: self._btn_max.setText("❐")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.pos()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
                if self._btn_max: self._btn_max.setText("□")
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, _e):
        self._toggle_max()


# ══════════════════════════════════════════════════════════════════════════════
#  DIALOGS
# ══════════════════════════════════════════════════════════════════════════════

def _dlg_qss(dark: bool) -> str:
    CARD = "#132B29" if dark else "#FDFCFA"
    BORD = "#1F4240" if dark else "#C8C3BB"
    TEXT = "#EDE9E1" if dark else "#1C2221"
    MUT  = "#6B9C9A" if dark else "#5C5C55"
    BG   = "#0D2120" if dark else "#F5F2EB"
    INP  = "#0A1918" if dark else "#E3DFDA"
    return f"""
        QDialog   {{ background: {BG}; }}
        QLabel    {{ color: {TEXT}; font-size: 12px; font-family: "Segoe UI"; }}
        QLineEdit {{
            background: {INP}; color: {TEXT};
            border: 1px solid {BORD}; border-radius: 7px;
            padding: 9px 12px; font-size: 13px;
        }}
        QLineEdit:focus {{ border-color: {CY_ACCENT}; }}
        QPushButton {{
            border-radius: 7px; padding: 10px 16px;
            font-weight: bold; font-size: 12px;
        }}
        #MutedLbl  {{ color: {MUT}; font-size: 11px; }}
        #CancelBtn {{ background: {CARD}; color: {MUT}; border: 1px solid {BORD}; }}
        #SubmitBtn {{ background: {CY_DEEP}; color: {SD_WARM}; border: none; }}
        #SubmitBtn:hover {{ background: {CY_BRIGHT}; color: #fff; }}
    """


class RegisterDialog(QDialog):
    def __init__(self, parent=None, is_dark=True):
        super().__init__(parent)
        self.setWindowTitle("Register New Student")
        self.setFixedSize(430, 330)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.result_data = None
        self.setStyleSheet(_dlg_qss(is_dark))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SP_XL, SP_XL, SP_XL, SP_XL)
        lay.setSpacing(SP_MD)

        h = QLabel("New Student Registration")
        h.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); lay.addWidget(h)
        sub = QLabel("Enter student details to begin guided face capture.")
        sub.setObjectName("MutedLbl"); lay.addWidget(sub)
        lay.addSpacing(SP_SM)
        lay.addWidget(QLabel("Registration Number  *"))
        self.reg_entry = QLineEdit()
        self.reg_entry.setPlaceholderText("e.g.  L1F22BSCS0001")
        lay.addWidget(self.reg_entry)
        lay.addWidget(QLabel("Full Name  *"))
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("e.g.  Fahad Gujjar")
        lay.addWidget(self.name_entry)
        lay.addSpacing(SP_MD)
        btn_row = QHBoxLayout()
        c = QPushButton("Cancel"); c.setObjectName("CancelBtn"); c.clicked.connect(self.reject)
        btn_row.addWidget(c)
        ok = QPushButton("Start Capture  →"); ok.setObjectName("SubmitBtn")
        ok.clicked.connect(self._submit); btn_row.addWidget(ok)
        lay.addLayout(btn_row)
        self.reg_entry.setFocus()

    def _submit(self):
        r, n = self.reg_entry.text().strip(), self.name_entry.text().strip()
        if r and n:
            self.result_data = (r, n); self.accept()


class SubjectDialog(QDialog):
    def __init__(self, parent=None, is_dark=True):
        super().__init__(parent)
        self.setWindowTitle("Select Subject")
        self.setFixedSize(360, 220)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.result_id = "1"
        self.setStyleSheet(_dlg_qss(is_dark))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SP_XL, SP_XL, SP_XL, SP_XL); lay.setSpacing(SP_MD)
        h = QLabel("Subject ID"); h.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lay.addWidget(h)
        sub = QLabel("Enter the subject database ID for attendance logs.")
        sub.setObjectName("MutedLbl"); lay.addWidget(sub)
        lay.addSpacing(SP_SM)
        self.entry = QLineEdit(); self.entry.setText("1")
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(self.entry)
        lay.addSpacing(SP_SM)
        ok = QPushButton("Start Recognition"); ok.setObjectName("SubmitBtn")
        ok.clicked.connect(self._submit); lay.addWidget(ok)
        self.entry.selectAll(); self.entry.setFocus()

    def _submit(self):
        v = self.entry.text().strip()
        self.result_id = v if v.isdigit() else "1"; self.accept()


class DemoDialog(QDialog):
    def __init__(self, parent=None, log_fn=None, is_dark=True):
        super().__init__(parent)
        self.setWindowTitle("Demo Data Manager")
        self.setFixedSize(420, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._log_fn = log_fn
        self.setStyleSheet(_dlg_qss(is_dark))
        self._build(is_dark)

    def _build(self, dark: bool):
        CARD = "#132B29" if dark else "#FDFCFA"
        BORD = "#1F4240" if dark else "#C8C3BB"
        MUT  = "#6B9C9A" if dark else "#5C5C55"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SP_XL, SP_XL, SP_XL, SP_XL); lay.setSpacing(SP_MD)
        h = QLabel("Demo Data Manager")
        h.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); lay.addWidget(h)
        sub = QLabel("Seed or clear demo records for live testing and reviews.")
        sub.setObjectName("MutedLbl"); lay.addWidget(sub)
        self.status_lbl = QLabel("Checking database status…")
        self.status_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.status_lbl.setStyleSheet(f"color:{MUT};")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(self.status_lbl)
        lay.addSpacing(SP_SM)
        seed = QPushButton("  ✚  Seed 50 Students + 14-Day Logs")
        seed.setStyleSheet(
            "background:#16A34A;color:white;border:none;border-radius:7px;"
            "padding:10px 16px;font-weight:bold;font-size:12px;")
        seed.clicked.connect(self._seed); lay.addWidget(seed)
        clr = QPushButton("  ✕  Clear All Demo Records")
        clr.setStyleSheet(
            "background:#DC2626;color:white;border:none;border-radius:7px;"
            "padding:10px 16px;font-weight:bold;font-size:12px;")
        clr.clicked.connect(self._clear); lay.addWidget(clr)
        close = QPushButton("Close")
        close.setStyleSheet(
            f"background:{CARD};color:{MUT};border:1px solid {BORD};"
            "border-radius:7px;padding:10px 16px;font-size:12px;")
        close.clicked.connect(self.accept); lay.addWidget(close)
        self._check_status()

    def _check_status(self):
        def _t():
            try:
                from db.connection import db_session
                from db.models import Student
                with db_session() as s:
                    n = s.query(Student).filter(Student.reg_number.like("DEMO-%")).count()
                msg   = f"Demo records: {n} loaded" if n else "No active demo records"
                color = C_SUCCESS_LED if n else "#6B8180"
            except Exception as e:
                msg, color = f"DB error: {e}", C_ERROR_LED
            self.status_lbl.setText(msg)
            self.status_lbl.setStyleSheet(f"color:{color};font-weight:bold;")
        threading.Thread(target=_t, daemon=True).start()

    def _seed(self):
        self.status_lbl.setText("Seeding…")
        self.status_lbl.setStyleSheet(f"color:{C_WARNING_LED};font-weight:bold;")
        def _t():
            try:
                from app.routes.demo import _seed_demo_data
                from db.connection import db_session
                with db_session() as s:
                    n = _seed_demo_data(s)
                msg = f"Seeded {n} students + attendance logs"
                self.status_lbl.setText(msg)
                self.status_lbl.setStyleSheet(f"color:{C_SUCCESS_LED};font-weight:bold;")
                if self._log_fn: self._log_fn(msg, "SUCCESS")
            except Exception as e:
                self.status_lbl.setText(f"Seed failed: {e}")
                self.status_lbl.setStyleSheet(f"color:{C_ERROR_LED};font-weight:bold;")
        threading.Thread(target=_t, daemon=True).start()

    def _clear(self):
        self.status_lbl.setText("Clearing…")
        self.status_lbl.setStyleSheet(f"color:{C_WARNING_LED};font-weight:bold;")
        def _t():
            try:
                from app.routes.demo import _clear_demo_data
                from db.connection import db_session
                with db_session() as s:
                    n = _clear_demo_data(s)
                msg = f"Cleared {n} demo records"
                self.status_lbl.setText(msg)
                self.status_lbl.setStyleSheet(f"color:{C_SUCCESS_LED};font-weight:bold;")
                if self._log_fn: self._log_fn(msg, "SUCCESS")
            except Exception as e:
                self.status_lbl.setText(f"Clear failed: {e}")
                self.status_lbl.setStyleSheet(f"color:{C_ERROR_LED};font-weight:bold;")
        threading.Thread(target=_t, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN HUB WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class EikonHub(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Eikon — Central Hub")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(860, 580)

        # ── FIX 5: compute DPI scale once, use for all manual pixel values ───
        screen = QApplication.primaryScreen()
        self._dpi = max(1.0, (screen.logicalDotsPerInch() / 96.0) if screen else 1.0)

        self._dark_mode       = True
        self._backend_process = None
        self._active_worker   = None
        self._camera_sources  = []
        self._selected_camera = None
        self._last_total = self._last_encoded = self._last_today = 0
        self._session_start   = time.time()
        self._session_scans   = 0
        self._initial_today   = None

        # Pre-allocated metric label references (populated in _build_tabs)
        self._metric_labels: dict[str, QLabel]  = {}
        self._metric_rows:   dict[str, QWidget] = {}

        self._build_ui()
        self._apply_styles()
        self._restore_geometry()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._backend_timer = QTimer(self)
        self._backend_timer.timeout.connect(self._poll_backend)
        self._backend_timer.start(3000)

        self._detect_cameras()
        self._poll_backend()

    # ── FIX 5: DPI-aware pixel helper ────────────────────────────────────────

    def _dp(self, n: int) -> int:
        """Scale a base-96-DPI logical value to this screen's logical pixels."""
        return max(1, round(n * self._dpi))

    # ── FIX 1: DWM shadow on FramelessWindowHint window (Windows only) ────────

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_dwm_shadow()

    def _apply_dwm_shadow(self):
        """
        Extend the DWM frame 1 px into the client area.
        Restores the OS drop-shadow without making any part of the window
        background transparent (margins of -1 would enable Aero glass).
        Safe no-op on non-Windows platforms.
        """
        if sys.platform != "win32":
            return
        try:
            class MARGINS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                             ("t", ctypes.c_int), ("b", ctypes.c_int)]
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                int(self.winId()), ctypes.byref(MARGINS(1, 1, 1, 1)))
        except Exception as exc:
            logger.debug("DWM shadow skipped: %s", exc)

    # ── Mode-aware semantic colour properties ─────────────────────────────────

    @property
    def _cs(self) -> str:   # success text colour for current theme
        return C_SUCCESS_DARK if self._dark_mode else C_SUCCESS_LIGHT

    @property
    def _cw(self) -> str:   # warning text colour
        return C_WARNING_DARK if self._dark_mode else C_WARNING_LIGHT

    @property
    def _ce(self) -> str:   # error text colour
        return C_ERROR_DARK if self._dark_mode else C_ERROR_LIGHT

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(self); self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self._title_bar = TitleBar(self); rl.addWidget(self._title_bar)

        self._task_bar = QProgressBar()
        self._task_bar.setObjectName("TaskBar")
        self._task_bar.setRange(0, 0)
        self._task_bar.setTextVisible(False)
        self._task_bar.setFixedHeight(2)
        self._task_bar.hide()
        rl.addWidget(self._task_bar)

        content = QWidget()
        cl = QHBoxLayout(content); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        rl.addWidget(content, 1)
        cl.addWidget(self._build_sidebar())
        cl.addWidget(self._build_main_panel(), 1)

        # Resize grip row
        gb = QWidget(); gb.setFixedHeight(14); gb.setStyleSheet("background:transparent;")
        gbl = QHBoxLayout(gb); gbl.setContentsMargins(0, 0, 0, 0); gbl.addStretch()
        grip = QSizeGrip(self); grip.setStyleSheet("background:transparent;")
        gbl.addWidget(grip)
        rl.addWidget(gb)

        self._log("Eikon Hub initialized  ·  Ready.", "SUCCESS")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sb = QWidget(self); sb.setObjectName("Sidebar")
        sb.setFixedWidth(self._dp(220))
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(SP_LG, SP_XL, SP_LG, SP_LG); lay.setSpacing(SP_SM)

        # Brand
        br = QHBoxLayout(); br.setSpacing(SP_SM)
        ip = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "logo_icon_sand.png"
        logo = QLabel()
        if ip.exists():
            pix = QPixmap(str(ip))
            logo.setPixmap(pix.scaled(self._dp(36), self._dp(36),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("◈"); logo.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            logo.setStyleSheet(f"color:{CY_ACCENT};")
        br.addWidget(logo)
        txt = QVBoxLayout(); txt.setSpacing(2)
        bn = QLabel("Eikon"); bn.setObjectName("BrandTitle")
        bn.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold)); txt.addWidget(bn)
        bs = QLabel("YOUR FACE IS YOUR ID"); bs.setObjectName("BrandSub")
        bs.setFont(QFont("Segoe UI", 9)); txt.addWidget(bs)
        br.addLayout(txt); lay.addLayout(br)
        div = QFrame(); div.setObjectName("SidebarDivider")
        div.setFrameShape(QFrame.Shape.HLine); lay.addWidget(div)
        lay.addSpacing(SP_XS)

        # ── Live statistics ───────────────────────────────────────────────────
        sl = QLabel("LIVE STATS"); sl.setObjectName("SidebarSection")
        lay.addWidget(sl)

        stats_card = QFrame(); stats_card.setObjectName("SidebarStatusCard")
        scl = QVBoxLayout(stats_card)
        scl.setContentsMargins(SP_MD, SP_MD, SP_MD, SP_MD); scl.setSpacing(SP_XS)

        def _add_stat(parent_lay, val_text, label_text):
            v = QLabel(val_text); v.setObjectName("SidebarStatVal")
            l = QLabel(label_text); l.setObjectName("SidebarStatLabel")
            parent_lay.addWidget(v); parent_lay.addWidget(l)
            return v

        def _add_sep(parent_lay):
            s = QFrame(); s.setObjectName("SidebarDivider")
            s.setFrameShape(QFrame.Shape.HLine); parent_lay.addWidget(s)

        self._sb_uptime  = _add_stat(scl, "00:00:00", "SESSION")
        _add_sep(scl)
        self._sb_scans   = _add_stat(scl, "0",        "SCANS")
        _add_sep(scl)
        self._sb_ai      = _add_stat(scl, "—",        "AI MODEL")
        _add_sep(scl)
        self._sb_today   = _add_stat(scl, "—",        "TODAY")
        _add_sep(scl)
        self._sb_rate    = _add_stat(scl, "—",        "RATE")

        lay.addWidget(stats_card)
        lay.addSpacing(SP_SM)

        # ── Backend status indicator ──────────────────────────────────────────
        self._sb_backend_led = PulsingLED(C_WARNING_LED)
        self._sb_backend_label = QLabel("Backend: Checking…")
        self._sb_backend_label.setStyleSheet(f"color:{CY_ACCENT};font-size:11px;font-weight:600;")
        bl_row = QHBoxLayout(); bl_row.setSpacing(SP_SM)
        bl_row.addWidget(self._sb_backend_led)
        bl_row.addWidget(self._sb_backend_label, 1)
        lay.addLayout(bl_row)
        lay.addSpacing(SP_SM)

        # ── Camera source picker ──────────────────────────────────────────────
        cl = QLabel("CAMERA SOURCE"); cl.setObjectName("CamLabel")
        cl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold)); lay.addWidget(cl)
        self.cam_combo = QComboBox(); self.cam_combo.setObjectName("CamCombo")
        self.cam_combo.addItem("Scanning…")
        self.cam_combo.currentIndexChanged.connect(self._on_camera_select)
        lay.addWidget(self.cam_combo)

        lay.addStretch()

        # ── Utility buttons ───────────────────────────────────────────────────
        ur = QHBoxLayout(); ur.setSpacing(SP_XS)
        self.btn_demo = QPushButton("⚗ Demo"); self.btn_demo.setObjectName("UtilBtn")
        self.btn_demo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_demo.clicked.connect(self._do_demo); ur.addWidget(self.btn_demo)
        self.btn_theme = QPushButton("☀ Light"); self.btn_theme.setObjectName("UtilBtn")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self._toggle_theme); ur.addWidget(self.btn_theme)
        lay.addLayout(ur)
        ver = QLabel("Eikon  v1.0.0"); ver.setObjectName("VersionLabel")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(ver)
        return sb

    # ── Main panel ────────────────────────────────────────────────────────────

    def _build_main_panel(self) -> QWidget:
        panel = QWidget(self); panel.setObjectName("MainPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(SP_XL, SP_LG, SP_XL, SP_SM); pl.setSpacing(SP_MD)

        lbl = QLabel("QUICK ACTIONS"); lbl.setObjectName("SectionLabel")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold)); pl.addWidget(lbl)
        pl.addLayout(self._build_action_grid())
        pl.addWidget(self._build_tabs(), 1)
        return panel

    # ── Action card grid ──────────────────────────────────────────────────────

    def _build_action_grid(self) -> QGridLayout:
        grid = QGridLayout(); grid.setSpacing(SP_MD)
        for c in range(5): grid.setColumnStretch(c, 1)

        cards_data = (
            ("Register",     "Guided face\ncapture",       "📷", self._do_register,  0),
            ("Train",        "Generate\nencodings",       "🧠", self._do_train,     1),
            ("Recognize",    "Attendance\nscanning",       "👁", self._do_recognize, 2),
            ("Kiosk",        "Fullscreen\nkiosk mode",     "🖥", self._do_kiosk,     3),
            ("Dashboard",    "Web admin\nportal",          "🌐", self._do_dashboard, 4),
        )
        for title, desc, icon, slot, col in cards_data:
            card = HoverCard()
            card.setMinimumHeight(130)
            card.setMaximumHeight(160)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(SP_MD, SP_MD, SP_MD, SP_MD); cl.setSpacing(6)

            # Emoji icon circle — mode-aware background via QSS
            icon_bg = QFrame(); icon_bg.setObjectName("IconCircle")
            icon_lay = QVBoxLayout(icon_bg)
            icon_lay.setContentsMargins(0, 0, 0, 0)
            ic = QLabel(icon); ic.setFont(QFont("Segoe UI Emoji", 20))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet("background:transparent;")
            icon_lay.addWidget(ic)
            cl.addWidget(icon_bg)

            t = QLabel(title); t.setObjectName("CardTitle")
            t.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold)); cl.addWidget(t)
            d = QLabel(desc); d.setObjectName("CardDesc")
            d.setFont(QFont("Segoe UI", 10)); cl.addWidget(d)
            cl.addStretch()
            btn = QPushButton("Launch"); btn.setObjectName("CardBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor); btn.clicked.connect(slot)
            cl.addWidget(btn)
            grid.addWidget(card, 0, col)
        return grid

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget(); self.tab_widget = tabs

        # ── Tab 1: System overview ────────────────────────────────────────────
        t1 = QWidget(); t1l = QVBoxLayout(t1)
        t1l.setContentsMargins(0, SP_MD, 0, 0); t1l.setSpacing(SP_MD)

        # Backend toggle in tab header
        ov_hdr = QHBoxLayout()
        ov_title = QLabel("Service Health")
        ov_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ov_title.setObjectName("ConsoleTitle")
        ov_hdr.addWidget(ov_title); ov_hdr.addStretch()
        self.btn_toggle_backend = QPushButton("Start Backend")
        self.btn_toggle_backend.setObjectName("CardBtn")
        self.btn_toggle_backend.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_backend.clicked.connect(self._toggle_backend)
        ov_hdr.addWidget(self.btn_toggle_backend)
        t1l.addLayout(ov_hdr)

        sr = QHBoxLayout(); sr.setSpacing(SP_MD)
        self.web_card, self.web_led, self.web_state = self._make_status_card(
            "Web Portal", "◎", "Dashboard interface")
        self.db_card,  self.db_led,  self.db_state  = self._make_status_card(
            "Database",  "◈", "MySQL storage engine")
        self.ai_card,  self.ai_led,  self.ai_state  = self._make_status_card(
            "AI Engine", "⬤", "buffalo_sc network")
        self.cam_card, self.cam_led, self.cam_state = self._make_status_card(
            "Webcam",    "▣", "Direct stream source")
        for c in (self.web_card, self.db_card, self.ai_card, self.cam_card):
            c.setGraphicsEffect(_new_shadow(12, 0, 2, 20)); sr.addWidget(c)
        t1l.addLayout(sr)

        # Metrics card
        self.metrics_card = QFrame(); self.metrics_card.setObjectName("MetricsCard")
        self.metrics_card.setGraphicsEffect(_new_shadow(12, 0, 2, 18))
        mc = QVBoxLayout(self.metrics_card)
        mc.setContentsMargins(SP_LG, SP_LG, SP_LG, SP_LG); mc.setSpacing(SP_SM)
        mct = QLabel("System Spec & Health Metrics")
        mct.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold)); mc.addWidget(mct)
        self.metrics_inner = QVBoxLayout(); self.metrics_inner.setSpacing(4)
        mc.addLayout(self.metrics_inner)

        # ── FIX 3: pre-build all rows — _refresh_metrics only calls setText ──
        for key, display in (
            ("ai",        "AI Detection Engine"),
            ("database",  "Database Engine"),
            ("platform",  "Host Platform"),
            ("python",    "Python Version"),
            ("students",  "Total Students"),
            ("encodings", "Trained Encodings"),
            ("today",     "Attendance Today"),
        ):
            row = QWidget()
            rl  = QHBoxLayout(row); rl.setContentsMargins(0, 3, 0, 3)
            k = QLabel(display); k.setObjectName("MetricKey")
            k.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold)); rl.addWidget(k)
            rl.addStretch()
            v = QLabel("—"); v.setObjectName("MetricVal"); rl.addWidget(v)
            self.metrics_inner.addWidget(row)
            self._metric_labels[key] = v
            self._metric_rows[key]   = row

        t1l.addWidget(self.metrics_card)
        tabs.addTab(t1, "  System Overview  ")

        # ── Tab 2: Developer console ──────────────────────────────────────────
        t2 = QWidget(); t2l = QVBoxLayout(t2)
        t2l.setContentsMargins(0, SP_MD, 0, 0); t2l.setSpacing(SP_SM)
        hdr = QHBoxLayout()
        cll = QLabel("System Log Console")
        cll.setObjectName("ConsoleTitle")
        cll.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr.addWidget(cll); hdr.addStretch()
        clr = QPushButton("Clear")
        clr.setObjectName("ConsoleClearBtn")
        clr.clicked.connect(self._clear_log); hdr.addWidget(clr)
        t2l.addLayout(hdr)
        self.log_box = QTextEdit(); self.log_box.setObjectName("Console")
        self.log_box.setReadOnly(True); t2l.addWidget(self.log_box)
        tabs.addTab(t2, "  Developer Console  ")
        return tabs

    def _make_status_card(self, title: str, icon: str, desc: str):
        card = QFrame(); card.setObjectName("StatusCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(SP_LG, SP_MD, SP_LG, SP_MD); lay.setSpacing(SP_SM)
        hdr = QHBoxLayout(); hdr.setSpacing(SP_SM)
        ic = QLabel(icon); ic.setFont(QFont("Segoe UI", 16))
        ic.setStyleSheet(f"color:{CY_ACCENT};"); hdr.addWidget(ic)
        tl = QLabel(title); tl.setObjectName("StatusTitle")
        tl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold)); hdr.addWidget(tl)
        hdr.addStretch()
        led = PulsingLED(C_WARNING_LED); hdr.addWidget(led)
        lay.addLayout(hdr)
        state = QLabel("Checking…"); state.setObjectName("StatusState")
        state.setStyleSheet(f"color:{C_WARNING_DARK};"); lay.addWidget(state)
        dl = QLabel(desc); dl.setObjectName("StatusDesc"); lay.addWidget(dl)
        return card, led, state

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_styles(self):
        self.setStyleSheet(build_qss(self._dark_mode))

    def update_styles(self):
        self._apply_styles()

    def _apply_card_shadow(self, widget):   # kept for compatibility
        widget.setGraphicsEffect(_new_shadow())

    # ── Clock & theme ─────────────────────────────────────────────────────────

    def _update_clock(self):
        self._title_bar.clock_lbl.setText(
            datetime.now().strftime("%a %d %b  ·  %H:%M:%S"))
        elapsed = int(time.time() - self._session_start)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        self._sb_uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._apply_styles()
        self.btn_theme.setText("☀ Light" if self._dark_mode else "☾ Dark")
        self._log(f"Theme → {'Dark' if self._dark_mode else 'Light'}", "INFO")
        # Re-poll so all status colours update with new mode-aware values
        self._poll_backend()

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "INFO"):
        ts    = datetime.now().strftime("%H:%M:%S")
        _colors = LOG_COLORS_DARK if self._dark_mode else LOG_COLORS_LIGHT
        color = _colors.get(tag, _colors["INFO"])
        html  = (f'<span style="color:{color};font-family:Consolas,monospace;">'
                 f'<b>[{ts}]</b>&nbsp;{tag}:&nbsp;</span>'
                 f'<span style="color:{color};">{msg}</span>')
        self.log_box.append(html)
        self.log_box.ensureCursorVisible()

    def _clear_log(self):
        self.log_box.clear()

    # ── Task progress ─────────────────────────────────────────────────────────

    def _start_task(self):
        self._task_bar.setRange(0, 0); self._task_bar.show()

    def _stop_task(self):
        self._task_bar.hide()

    def _toast(self, msg: str, level: str = "info"):
        ToastNotification(self, msg, level)

    # ── Camera detection ──────────────────────────────────────────────────────

    def _detect_cameras(self):
        self._is_populating_cameras = True
        self._log("Scanning camera hardware…")
        self._scanner = CameraScanner()
        self._scanner.finished_signal.connect(self._on_cameras_detected)
        self._scanner.start()

    def _on_cameras_detected(self, sources):
        self._camera_sources = sources
        self.cam_combo.clear()
        if not sources:
            self.cam_combo.addItem("No cameras found")
            self._is_populating_cameras = False
            self._log("No camera devices detected.", "WARN"); return
        for idx, label in sources:
            self.cam_combo.addItem(label, idx)
        try:
            from config import CAMERA_SOURCE
            for i in range(self.cam_combo.count()):
                if self.cam_combo.itemData(i) == CAMERA_SOURCE:
                    self.cam_combo.setCurrentIndex(i); break
        except Exception:
            pass
        self._is_populating_cameras = False
        self._log(f"Detected {len(sources)} camera source(s).", "SUCCESS")

    def _on_camera_select(self, index):
        if index < 0 or not self._camera_sources: return
        idx = self.cam_combo.itemData(index)
        if idx is not None and idx != self._selected_camera:
            self._selected_camera = idx
            if getattr(self, "_is_populating_cameras", False):
                return
            env = Path(__file__).resolve().parent.parent / ".env"
            if env.exists():
                content = env.read_text(encoding="utf-8")
                env.write_text(
                    re.sub(r"CAMERA_SOURCE=.*", f"CAMERA_SOURCE={idx}", content),
                    encoding="utf-8")
                self._log(f"Camera → index {idx}  (restart to apply)", "SUCCESS")

    # ── Subprocess runner ─────────────────────────────────────────────────────

    def _get_venv_python(self) -> str:
        root = Path(__file__).resolve().parent.parent
        for p in (root / "venv"  / "Scripts" / "python.exe",
                  root / "venv"  / "bin"     / "python",
                  root / ".venv" / "Scripts" / "python.exe",
                  root / ".venv" / "bin"     / "python"):
            if p.exists(): return str(p)
        return sys.executable

    def _run_subprocess(self, cmd, on_done=None, stream_output=False, is_gui=False):
        if self._active_worker and self._active_worker.isRunning():
            self._log("A task is already running — please wait.", "WARN")
            self._toast("A task is already running.", "warn"); return
        self._start_task()
        self._log(f"Launching:  {' '.join(str(c) for c in cmd)}")
        self._active_worker = SubprocessWorker(cmd, stream_output, is_gui)
        self._active_worker.line_received.connect(lambda m, t: self._log(m, t))
        def _done(code):
            self._stop_task()
            if on_done: on_done(code)
        self._active_worker.finished_signal.connect(_done)
        self._active_worker.start()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_register(self):
        dlg = RegisterDialog(self, is_dark=self._dark_mode)
        if dlg.exec():
            reg, name = dlg.result_data
            self._title_bar.title_lbl.setText(f"Registering: {name}")
            self._run_subprocess(
                [self._get_venv_python(), "gui/kiosk.py",
                 "--mode", "register", "--reg", reg, "--name", name],
                on_done=lambda c: self._on_reg_done(c, name), is_gui=True)

    def _on_reg_done(self, code, name):
        if code == 0:
            self._log(f"Registration complete for {name}.", "SUCCESS")
            self._toast(f"{name} registered.", "success")
            self._log("Run 'Train Encodings' to generate face encodings.")
        else:
            self._log("Registration session closed.", "WARN")
        self._title_bar.title_lbl.setText("Eikon — Central Hub")
        self._poll_backend()

    def _do_train(self):
        self._title_bar.title_lbl.setText("Training face profiles…")
        self._run_subprocess(
            [self._get_venv_python(), "core/train.py"],
            on_done=self._on_train_done, stream_output=True)

    def _on_train_done(self, code):
        if code == 0:
            self._log("Training finished successfully.", "SUCCESS")
            self._toast("Face profiles trained.", "success")
        else:
            self._log("Training process failed.", "ERROR")
            self._toast("Training failed — check console.", "error")
        self._title_bar.title_lbl.setText("Eikon — Central Hub")
        self._poll_backend()

    def _do_recognize(self):
        dlg = SubjectDialog(self, is_dark=self._dark_mode)
        if dlg.exec():
            self._title_bar.title_lbl.setText("Recognition Session Active")
            self._run_subprocess(
                [self._get_venv_python(), "gui/kiosk.py",
                 "--mode", "attendance", "--subject", dlg.result_id],
                on_done=lambda c: (
                    self._log("Recognition session ended."),
                    self._title_bar.title_lbl.setText("Eikon — Central Hub"),
                    self._poll_backend()),
                is_gui=True)

    def _do_kiosk(self):
        self._run_subprocess(
            [self._get_venv_python(), "gui/kiosk.py",
             "--mode", "attendance", "--subject", "1"],
            on_done=lambda c: self._log("Kiosk closed."), is_gui=True)

    def _do_dashboard(self):
        import webbrowser
        try: from config import PORT
        except: PORT = 5000
        def _open():
            for _ in range(6):
                try:
                    with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                        webbrowser.open(f"http://localhost:{PORT}"); return
                except OSError: time.sleep(0.5)
            self._log("Server did not respond in time.", "WARN")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                webbrowser.open(f"http://localhost:{PORT}"); return
        except OSError: pass
        self._log("Starting backend…"); self._start_backend()
        threading.Thread(target=_open, daemon=True).start()

    def _do_demo(self):
        DemoDialog(self, log_fn=self._log, is_dark=self._dark_mode).exec()
        self._poll_backend()

    # ── Backend service ───────────────────────────────────────────────────────

    def _start_backend(self):
        if self._backend_process: return
        root = Path(__file__).resolve().parent.parent
        self._log("Starting Eikon web backend…")
        self._backend_process = subprocess.Popen(
            [self._get_venv_python(), "run.py", "--backend"], cwd=str(root),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

    def _stop_backend(self):
        if self._backend_process:
            self._log("Stopping backend…")
            self._backend_process.terminate(); self._backend_process = None

    def _toggle_backend(self):
        try: from config import PORT
        except: PORT = 5000
        up = False
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5): up = True
        except OSError: pass
        if up: self._stop_backend(); self._log("Backend stopped.", "SUCCESS")
        else:  self._start_backend()

    def _poll_backend(self):
        self._poller = BackendPoller()
        self._poller.finished_signal.connect(self._on_poll_done)
        self._poller.start()

    # ── FIX 2: mode-aware LED states ─────────────────────────────────────────
    # ── FIX 3: in-place metric text update  ───────────────────────────────────

    def _on_poll_done(self, is_up: bool, stats: dict):
        try: from config import PORT, ENCODINGS_FILE
        except: PORT = 5000; ENCODINGS_FILE = "encodings.pkl"

        self._last_total   = stats["total"]
        self._last_encoded = stats["encoded"]
        self._last_today   = stats["today"]
        cs, cw, ce         = self._cs, self._cw, self._ce

        # ── Backend toggle button (System Overview header) ────────────────────
        if is_up:
            self.btn_toggle_backend.setText("Stop Backend")
            self.btn_toggle_backend.setStyleSheet(
                "background:#7F1D1D;color:white;border:none;"
                "border-radius:6px;padding:7px 14px;font-size:11px;font-weight:700;")
            # LEDs solid green
            self.web_led.set_color(C_SUCCESS_LED); self.web_led.set_pulsing(False)
            self.web_state.setText(f"Online ({PORT})"); self.web_state.setStyleSheet(f"color:{cs};")
            self.db_led.set_color(C_SUCCESS_LED);  self.db_led.set_pulsing(False)
            self.db_state.setText("Connected (MySQL)"); self.db_state.setStyleSheet(f"color:{cs};")
            # Sidebar backend indicator
            self._sb_backend_led.set_color(C_SUCCESS_LED); self._sb_backend_led.set_pulsing(False)
            self._sb_backend_label.setText(f"Backend: Online ({PORT})")
            self._sb_backend_label.setStyleSheet(f"color:{CY_ACCENT};font-size:11px;font-weight:600;")
        else:
            self.btn_toggle_backend.setText("Start Backend")
            self.btn_toggle_backend.setStyleSheet(
                f"background:{CY_DEEP};color:{SD_WARM};border:none;"
                "border-radius:6px;padding:7px 14px;font-size:11px;font-weight:700;")
            # LEDs pulsing red
            self.web_led.set_color(C_ERROR_LED); self.web_led.set_pulsing(True)
            self.web_state.setText("Offline"); self.web_state.setStyleSheet(f"color:{ce};")
            self.db_led.set_color(C_ERROR_LED);  self.db_led.set_pulsing(True)
            self.db_state.setText("Offline");    self.db_state.setStyleSheet(f"color:{ce};")
            # Sidebar backend indicator
            self._sb_backend_led.set_color(C_ERROR_LED); self._sb_backend_led.set_pulsing(True)
            self._sb_backend_label.setText("Backend: Offline")
            self._sb_backend_label.setStyleSheet("color:#6B8E8A;font-size:11px;font-weight:600;")

        # AI engine
        enc_ok = bool(ENCODINGS_FILE) and Path(str(ENCODINGS_FILE)).exists()
        if enc_ok:
            self.ai_led.set_color(C_SUCCESS_LED); self.ai_led.set_pulsing(False)
            self.ai_state.setText("Ready & Armed"); self.ai_state.setStyleSheet(f"color:{cs};")
            self._sb_ai.setText("Ready")
        else:
            self.ai_led.set_color(C_WARNING_LED); self.ai_led.set_pulsing(True)
            self.ai_state.setText("Needs Training"); self.ai_state.setStyleSheet(f"color:{cw};")
            self._sb_ai.setText("Need Train")

        # Camera
        if self._camera_sources:
            self.cam_led.set_color(C_SUCCESS_LED); self.cam_led.set_pulsing(False)
            self.cam_state.setText("Ready");            self.cam_state.setStyleSheet(f"color:{cs};")
        else:
            self.cam_led.set_color(C_ERROR_LED); self.cam_led.set_pulsing(True)
            self.cam_state.setText("No cameras found"); self.cam_state.setStyleSheet(f"color:{ce};")

        self._refresh_metrics(is_up)

    def _refresh_metrics(self, is_up: bool):
        """Update metric labels and sidebar stats in-place."""
        self._metric_labels["ai"].setText("buffalo_sc · InsightFace 320×320")
        self._metric_labels["platform"].setText(sys.platform.upper())
        self._metric_labels["python"].setText(sys.version.split()[0])
        self._metric_labels["database"].setText(
            "MySQL / PyMySQL" if is_up else "OFFLINE — backend down")

        if is_up:
            self._metric_labels["students"].setText(f"{self._last_total} active profiles")
            self._metric_labels["encodings"].setText(f"{self._last_encoded} registered")
            self._metric_labels["today"].setText(f"{self._last_today} logs")

            # Initialize initial today baseline
            if self._initial_today is None:
                self._initial_today = self._last_today
            self._session_scans = max(0, self._last_today - self._initial_today)

            # Sidebar live stats
            self._sb_scans.setText(str(self._session_scans))
            self._sb_today.setText(str(self._last_today))
            rate = int((self._last_today / self._last_total * 100)) if self._last_total > 0 else 0
            self._sb_rate.setText(f"{rate}%")
        else:
            self._metric_labels["students"].setText("—")
            self._metric_labels["encodings"].setText("—")
            self._metric_labels["today"].setText("—")
            self._sb_scans.setText("—")
            self._sb_today.setText("—")
            self._sb_rate.setText("—")

    # ── Geometry persistence ──────────────────────────────────────────────────

    def _save_geometry(self):
        QSettings("Eikon", "EikonHub").setValue("geometry", self.saveGeometry())

    def _restore_geometry(self):
        geo = QSettings("Eikon", "EikonHub").value("geometry")
        if geo: self.restoreGeometry(geo)
        else:   self.resize(self._dp(1040), self._dp(700))

    def closeEvent(self, event):
        self._log("Eikon Hub closing — cleaning up…")
        self._save_geometry()
        self._stop_backend()
        if self._active_worker: self._active_worker.terminate_proc()
        event.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── FIX 5: HiDPI env vars must be set before QApplication is created ──────
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING",       "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR",     "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    app = QApplication(sys.argv)

    # PassThrough preserves fractional DPI (e.g. 125 %, 150 %) without rounding
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app.setFont(QFont(
        "Segoe UI, Inter, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue", 10))

    win = EikonHub()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()