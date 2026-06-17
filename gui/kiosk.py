"""
gui/kiosk.py — Premium windowed terminal for Eikon

Supports two modes:
1. Attendance Mode (default)
2. Registration Mode (guided face capture)

Run Attendance:
    python gui/kiosk.py --subject 1

Run Registration:
    python gui/kiosk.py --mode register --reg "L1F22BSCS001" --name "Fahad"
"""

import sys
import cv2
import time
import logging
import threading
import argparse
import math
from pathlib import Path
from datetime import datetime
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk
from PIL import Image, ImageTk

from core.recognize import RecognitionEngine, draw_overlay
from core.register import RegistrationSession
from utils.camera import Camera
from config import CAMERA_SOURCE

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Eikon Premium Palette ──────────────────────────────────────────────────────
BG          = "#0B1120"
BG_CARD     = "#111827"
BG_SURFACE  = "#1E293B"
CYPRUS      = "#004643"
CYPRUS_LIGHT= "#006B66"
SAND        = "#F0EDE5"
TEXT_DIM    = "#64748B"
TEXT_MID    = "#94A3B8"
TEXT_BRIGHT = "#E2E8F0"
SUCCESS     = "#22C55E"
SUCCESS_DIM = "#14532D"
WARNING     = "#F59E0B"
WARNING_DIM = "#78350F"
DANGER      = "#EF4444"
DANGER_DIM  = "#7F1D1D"
BLUE        = "#3B82F6"
BLUE_DIM    = "#1E3A5F"
BORDER      = "#1E293B"

_CONFIRM_FRAMES = 8
_RESET_DELAY    = 2.5


class KioskApp(ctk.CTk):
    def __init__(self, mode="attendance", subject_id=1, reg_number=None, name=None):
        super().__init__()

        self.mode = mode
        self.subject_id = subject_id
        self.reg_number = reg_number
        self.student_name = name

        self.engine = None
        self.reg_session = None
        self.camera = None

        self._state = "idle" if mode == "attendance" else "register"
        self._confirm_count = 0
        self._confirm_reg = None
        self._reset_timer = None
        self._pulse_angle = 0
        self._running = True
        self._latest_frame = None
        self._raw_frame = None
        self._new_frame_available = False
        self._frame_lock = threading.Lock()
        self._engine_ready = False

        self._latest_results = []
        self._latest_reg_state = None
        self._latest_reg_display = None
        self._results_lock = threading.Lock()

        # ── Window config — polished windowed mode ──────────────────────────
        mode_title = "Attendance Recognition" if mode == "attendance" else "Student Registration"
        self.title(f"Eikon — {mode_title}")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=BG)
        self.bind("<Escape>", lambda e: self._shutdown())

        self._build_ui()
        self._start_engine_thread()
        self._start_inference_thread()
        self._start_camera_thread()
        self._update_ui_loop()

    # ── UI Build ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ─────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=BG_CARD, height=52, corner_radius=0,
                           border_width=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        # Logo
        logo_path = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "logo_icon_sand.png"
        if logo_path.exists():
            try:
                img = Image.open(logo_path)
                logo = ctk.CTkImage(light_image=img, dark_image=img, size=(28, 28))
                ctk.CTkLabel(top, image=logo, text="").pack(side="left", padx=(16, 6), pady=12)
            except Exception:
                pass

        mode_text = "Attendance" if self.mode == "attendance" else "Registration"
        ctk.CTkLabel(
            top, text=f"Eikon  ·  {mode_text}",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=SAND
        ).pack(side="left", padx=4, pady=14)

        # Status badge
        self.status_badge = ctk.CTkLabel(
            top, text="  LOADING  ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=BG, fg_color=WARNING, corner_radius=4,
            height=22
        )
        self.status_badge.pack(side="left", padx=12)

        # Time
        self.time_label = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_MID
        )
        self.time_label.pack(side="right", padx=16)

        self.date_label = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color=TEXT_DIM
        )
        self.date_label.pack(side="right", padx=4)

        # Close button
        ctk.CTkButton(
            top, text="✕", width=36, height=36,
            fg_color="transparent", hover_color=DANGER_DIM,
            text_color=TEXT_DIM, font=ctk.CTkFont(size=16),
            command=self._shutdown
        ).pack(side="right", padx=4)

        # ── Main body ───────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        # Camera panel (left)
        cam_container = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=14,
                                     border_width=1, border_color=BORDER)
        cam_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        cam_header = ctk.CTkFrame(cam_container, fg_color="transparent", height=36)
        cam_header.pack(fill="x", padx=16, pady=(12, 0))
        cam_header.pack_propagate(False)
        ctk.CTkLabel(
            cam_header, text="📷  Live Camera Feed",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MID
        ).pack(side="left")

        self.fps_label = ctk.CTkLabel(
            cam_header, text="", font=ctk.CTkFont(size=10), text_color=TEXT_DIM
        )
        self.fps_label.pack(side="right")

        self.camera_label = ctk.CTkLabel(
            cam_container, text="", fg_color=BG_SURFACE, corner_radius=10
        )
        self.camera_label.pack(fill="both", expand=True, padx=12, pady=12)

        self.loading_label = ctk.CTkLabel(
            cam_container, text="⏳  Initializing AI engine...",
            font=ctk.CTkFont(size=13), text_color=TEXT_DIM
        )
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")

        # Info panel (right)
        info_panel = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=14,
                                  border_width=1, border_color=BORDER, width=320)
        info_panel.pack(side="right", fill="y")
        info_panel.pack_propagate(False)

        # Status canvas (animated)
        self.canvas = ctk.CTkCanvas(
            info_panel, width=160, height=160,
            bg=BG_CARD, highlightthickness=0
        )
        self.canvas.pack(pady=(30, 16))

        self.status_name = ctk.CTkLabel(
            info_panel, text="Eikon",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT_BRIGHT, wraplength=280
        )
        self.status_name.pack(pady=(0, 6))

        self.status_msg = ctk.CTkLabel(
            info_panel, text="Waiting for camera...",
            font=ctk.CTkFont(size=13), text_color=TEXT_MID, wraplength=280
        )
        self.status_msg.pack(pady=(0, 16))

        # Progress
        self.progress_bar = ctk.CTkProgressBar(
            info_panel, width=240, height=6,
            fg_color=BG_SURFACE, progress_color=BLUE, corner_radius=3
        )
        self.progress_bar.set(0)

        # Separator
        ctk.CTkFrame(info_panel, height=1, fg_color=BORDER).pack(fill="x", padx=20, pady=16)

        # Mode-specific info section
        if self.mode == "attendance":
            info_grid = ctk.CTkFrame(info_panel, fg_color="transparent")
            info_grid.pack(fill="x", padx=20)

            self.subject_label = ctk.CTkLabel(
                info_grid, text="Subject: Loading...",
                font=ctk.CTkFont(size=12), text_color=TEXT_DIM,
                anchor="w"
            )
            self.subject_label.pack(anchor="w", pady=2)

            self.count_label = ctk.CTkLabel(
                info_grid, text="Today: 0 marked",
                font=ctk.CTkFont(size=12), text_color=TEXT_DIM,
                anchor="w"
            )
            self.count_label.pack(anchor="w", pady=2)
        else:
            self.quality_label = ctk.CTkLabel(
                info_panel, text="",
                font=ctk.CTkFont(size=13, weight="bold"), text_color=WARNING
            )
            self.quality_label.pack(pady=(0, 12))

        # Spacer
        ctk.CTkFrame(info_panel, fg_color="transparent").pack(fill="both", expand=True)

        # Bottom hint
        ctk.CTkLabel(
            info_panel, text="Press ESC to close",
            font=ctk.CTkFont(size=10), text_color=TEXT_DIM
        ).pack(side="bottom", pady=12)

    # ── Engine thread (heavy AI load — off main thread) ────────────────────────

    def _start_engine_thread(self):
        def _load():
            try:
                if self.mode == "attendance":
                    self.engine = RecognitionEngine(subject_id=self.subject_id)
                    self.after(0, self._update_subject_label)
                else:
                    self.reg_session = RegistrationSession(self.reg_number, self.student_name)

                self._engine_ready = True
                self.after(0, lambda: self.status_badge.configure(
                    text="  READY  ", fg_color=SUCCESS
                ))
                self.after(0, lambda: self.loading_label.configure(text=""))
                self.after(0, lambda: self.status_msg.configure(text="Please look at the camera"))
                logger.info(f"Kiosk engine ready in {self.mode} mode.")
            except Exception as e:
                logger.error(f"Engine load failed: {e}")
                self.after(0, lambda: self.status_badge.configure(
                    text="  ERROR  ", fg_color=DANGER
                ))
                self.after(0, lambda: self.loading_label.configure(
                    text=f"❌  {e}"
                ))

        threading.Thread(target=_load, daemon=True).start()

    # ── Camera thread (reads frames in background — never blocks UI) ───────────

    def _start_inference_thread(self):
        def _inference_loop():
            logger.info("Inference thread started.")
            while self._running:
                if not self._engine_ready:
                    time.sleep(0.1)
                    continue

                frame = None
                with self._frame_lock:
                    if self._new_frame_available:
                        frame = self._raw_frame.copy() if self._raw_frame is not None else None
                        self._new_frame_available = False

                if frame is None:
                    time.sleep(0.01)
                    continue

                try:
                    if self.mode == "attendance" and self.engine:
                        results = self.engine.process_frame(frame)
                        with self._results_lock:
                            self._latest_results = results
                        self.after(0, lambda r=results: self._handle_attendance_results(r))

                    elif self.mode == "register" and self.reg_session:
                        state, display = self.reg_session.process_frame(frame)
                        with self._results_lock:
                            self._latest_reg_state = state
                            self._latest_reg_display = display
                        self.after(0, lambda s=state: self._handle_register_state(s))
                except Exception as e:
                    logger.error(f"Inference error: {e}")
                    time.sleep(0.05)

        threading.Thread(target=_inference_loop, daemon=True).start()

    def _start_camera_thread(self):
        def _cam_loop():
            try:
                from config import CAMERA_WIDTH, CAMERA_HEIGHT
                cam = Camera(source=CAMERA_SOURCE, width=CAMERA_WIDTH, height=CAMERA_HEIGHT)
                cam.start()
                self.camera = cam
                logger.info("Camera started successfully.")
            except Exception as e:
                logger.error(f"Camera failed: {e}")
                self.after(0, lambda: self.loading_label.configure(
                    text=f"❌  Camera error: {e}"
                ))
                return

            frame_times = deque(maxlen=30)
            while self._running:
                t0 = time.perf_counter()
                frame = cam.read()
                if frame is not None:
                    # 1. Update raw frame for inference thread
                    with self._frame_lock:
                        self._raw_frame = frame
                        self._new_frame_available = True

                    # 2. Draw overlay on the frame to display in the UI
                    display = frame.copy()
                    if self._engine_ready:
                        if self.mode == "attendance":
                            with self._results_lock:
                                results = self._latest_results
                            if results:
                                draw_overlay(display, results)
                        elif self.mode == "register":
                            with self._results_lock:
                                reg_display = self._latest_reg_display
                            if reg_display is not None:
                                display = reg_display

                    with self._frame_lock:
                        self._latest_frame = display

                    dt = time.perf_counter() - t0
                    frame_times.append(dt)
                    if len(frame_times) > 2:
                        fps = len(frame_times) / sum(frame_times)
                        self.after(0, lambda f=fps: self.fps_label.configure(
                            text=f"{f:.0f} FPS"
                        ))
                else:
                    time.sleep(0.01)

            cam.release()

        threading.Thread(target=_cam_loop, daemon=True).start()

    # ── UI update loop (only touches display — never blocks) ───────────────────

    def _update_ui_loop(self):
        if not self._running:
            return

        now = datetime.now()
        self.time_label.configure(text=now.strftime("%H:%M:%S"))
        self.date_label.configure(text=now.strftime("%A, %d %B %Y"))

        # Display latest processed frame
        with self._frame_lock:
            frame = self._latest_frame
            self._latest_frame = None

        if frame is not None:
            self._show_frame(frame)

        self._animate_canvas()
        self.after(33, self._update_ui_loop)

    # ── Attendance logic (called from camera thread via after()) ───────────────

    def _handle_attendance_results(self, results):
        if self._state in ("present", "late", "duplicate", "unknown", "spoof"):
            return

        if not results:
            self._set_state("idle")
            self._confirm_count = 0
            self._confirm_reg = None
            return

        r = results[0]

        if r.status == "spoof":
            self._set_state("spoof", name="Spoof Detected", msg="Please present your actual face")
            self._schedule_reset()
            return
        if r.status == "unknown":
            self._set_state("scanning")
            return
        if r.status == "duplicate":
            self._set_state("duplicate", name=r.name, msg="Already marked present today")
            self._schedule_reset()
            return

        if r.reg_number == self._confirm_reg:
            self._confirm_count += 1
        else:
            self._confirm_reg = r.reg_number
            self._confirm_count = 1

        progress = self._confirm_count / _CONFIRM_FRAMES
        self._set_state("scanning", progress=progress, name=r.name, msg="Verifying...")

        if self._confirm_count >= _CONFIRM_FRAMES:
            if r.marked:
                final_state = r.status
                msg = "✓ Attendance Marked!" if final_state == "present" else "⚠ Marked — Late"
            else:
                final_state = "duplicate"
                msg = "Already marked today"

            self._set_state(final_state, name=r.name, msg=msg)
            self._update_count_label()
            self._confirm_count = 0
            self._confirm_reg = None
            self._schedule_reset()

    def _handle_register_state(self, state):
        if state["status"] == "complete":
            self._set_state(
                "complete", name="Registration Complete",
                msg=f"Captured faces for {self.student_name}",
                progress=1.0
            )
            self.quality_label.configure(
                text="✓ Run Train Encodings from Hub next",
                text_color=SUCCESS
            )
            self.after(3000, self._shutdown)
            return

        self._set_state(
            "register", name=state["pose"],
            msg=state["instruction"], progress=state["progress"]
        )

        quality = state.get("quality", 0)
        if quality > 0:
            col = SUCCESS if quality > 70 else WARNING
            self.quality_label.configure(text=f"Quality: {int(quality)}%", text_color=col)
        else:
            self.quality_label.configure(text=state["instruction"], text_color=DANGER)

    # ── Frame rendering ────────────────────────────────────────────────────────

    def _show_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            w = self.camera_label.winfo_width() or 640
            h = self.camera_label.winfo_height() or 480
            if w < 10 or h < 10:
                return
            img = img.resize((w, h), Image.LANCZOS)
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self.camera_label.configure(image=photo, text="")
            self.camera_label._image = photo
        except Exception:
            pass

    # ── State management ───────────────────────────────────────────────────────

    def _set_state(self, state, name="", msg="", progress=0.0):
        self._state = state

        if state == "idle":
            self.status_name.configure(
                text="Eikon", text_color=TEXT_BRIGHT,
                font=ctk.CTkFont(size=20, weight="bold")
            )
            self.status_msg.configure(text="Please look at the camera", text_color=TEXT_MID)
            self.progress_bar.pack_forget()
        elif state == "scanning":
            self.status_name.configure(
                text=name or "Scanning...", text_color=BLUE,
                font=ctk.CTkFont(size=20, weight="bold")
            )
            self.status_msg.configure(text=msg or "Hold still...", text_color=TEXT_MID)
            self.progress_bar.pack(pady=(0, 16))
            self.progress_bar.set(progress)
            self.progress_bar.configure(progress_color=BLUE)
        elif state in ("present", "late", "complete"):
            col = SUCCESS if state in ("present", "complete") else WARNING
            self.status_name.configure(
                text=name, text_color=col,
                font=ctk.CTkFont(size=22, weight="bold")
            )
            self.status_msg.configure(text=msg, text_color=col)
            self.progress_bar.pack(pady=(0, 16))
            self.progress_bar.set(1.0)
            self.progress_bar.configure(progress_color=col)
        elif state == "register":
            self.status_name.configure(
                text=name, text_color=SAND,
                font=ctk.CTkFont(size=20, weight="bold")
            )
            self.status_msg.configure(text=msg, text_color=TEXT_MID)
            self.progress_bar.pack(pady=(0, 16))
            self.progress_bar.set(progress)
            self.progress_bar.configure(progress_color=CYPRUS_LIGHT)
        else:
            txt_col = DANGER if state in ("unknown", "spoof") else BLUE
            self.status_name.configure(
                text=name or state.capitalize(), text_color=txt_col,
                font=ctk.CTkFont(size=20, weight="bold")
            )
            self.status_msg.configure(text=msg, text_color=txt_col)
            self.progress_bar.pack_forget()

    def _schedule_reset(self):
        if self._reset_timer:
            self.after_cancel(self._reset_timer)
        self._reset_timer = self.after(
            int(_RESET_DELAY * 1000), lambda: self._set_state("idle")
        )

    def _update_count_label(self):
        if self.mode != "attendance":
            return
        def _count():
            try:
                from db.connection import db_session
                from db.models import Attendance
                from datetime import date
                from sqlalchemy import func
                with db_session() as session:
                    count = session.query(func.count(Attendance.id)).filter(
                        Attendance.subject_id == self.subject_id,
                        Attendance.marked_date == date.today()
                    ).scalar() or 0
                self.after(0, lambda: self.count_label.configure(
                    text=f"Today: {count} marked"
                ))
            except Exception:
                pass
        threading.Thread(target=_count, daemon=True).start()

    def _update_subject_label(self):
        def _load():
            try:
                from db.connection import db_session
                from db.models import Subject
                with db_session() as session:
                    s = session.get(Subject, self.subject_id)
                    if s:
                        self.after(0, lambda: self.subject_label.configure(
                            text=f"Subject: {s.code} — {s.name}"
                        ))
            except Exception:
                pass
        threading.Thread(target=_load, daemon=True).start()

    # ── Canvas animation ───────────────────────────────────────────────────────

    def _animate_canvas(self):
        self.canvas.delete("all")
        cx, cy, r = 80, 80, 55

        if self._state == "idle":
            self._pulse_angle = (self._pulse_angle + 3) % 360
            pulse = 0.5 + 0.5 * math.sin(math.radians(self._pulse_angle))
            alpha = int(80 + 100 * pulse)
            col = f"#{alpha:02x}{alpha:02x}ff"
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=col, width=2, fill="")
            # Face icon
            self.canvas.create_oval(cx-16, cy-16, cx+16, cy+16, outline=TEXT_DIM, fill=BG_SURFACE, width=2)
            self.canvas.create_oval(cx-7, cy-6, cx-3, cy-2, fill=TEXT_DIM, outline="")
            self.canvas.create_oval(cx+3, cy-6, cx+7, cy-2, fill=TEXT_DIM, outline="")
            self.canvas.create_arc(cx-8, cy+2, cx+8, cy+10, start=200, extent=140, style="arc", outline=TEXT_DIM, width=2)

        elif self._state == "scanning":
            self._pulse_angle = (self._pulse_angle + 6) % 360
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=BG_SURFACE, width=3, fill="")
            extent = int(360 * (self._confirm_count / _CONFIRM_FRAMES))
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-extent, outline=BLUE, width=3, style="arc")
            pct = int(self._confirm_count / _CONFIRM_FRAMES * 100)
            self.canvas.create_text(cx, cy, text=f"{pct}%", fill=BLUE, font=("Inter", 16, "bold"))

        elif self._state in ("present", "complete"):
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=SUCCESS, width=3, fill=SUCCESS_DIM)
            self.canvas.create_text(cx, cy, text="✓", fill=SUCCESS, font=("Inter", 36, "bold"))

        elif self._state == "late":
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=WARNING, width=3, fill=WARNING_DIM)
            self.canvas.create_text(cx, cy, text="!", fill=WARNING, font=("Inter", 36, "bold"))

        elif self._state in ("unknown", "spoof"):
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=DANGER, width=3, fill=DANGER_DIM)
            self.canvas.create_text(cx, cy, text="✗", fill=DANGER, font=("Inter", 36, "bold"))

        elif self._state == "duplicate":
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=BLUE, width=3, fill=BLUE_DIM)
            self.canvas.create_text(cx, cy, text="↩", fill=BLUE, font=("Inter", 32, "bold"))

        elif self._state == "register":
            self._pulse_angle = (self._pulse_angle + 4) % 360
            pulse = 0.5 + 0.5 * math.sin(math.radians(self._pulse_angle))
            w = 2 + pulse
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=CYPRUS_LIGHT, width=int(w), fill="")
            self.canvas.create_text(cx, cy, text="◉", fill=CYPRUS_LIGHT, font=("Inter", 28))

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def _shutdown(self):
        self._running = False
        self.after(100, self.destroy)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eikon Attendance Kiosk")
    parser.add_argument("--mode", type=str, default="attendance", choices=["attendance", "register"], help="Mode to run the kiosk in")
    parser.add_argument("--subject", type=int, default=1, help="Subject ID (for attendance mode)")
    parser.add_argument("--reg", type=str, help="Registration Number (for register mode)")
    parser.add_argument("--name", type=str, help="Student Name (for register mode)")
    args = parser.parse_args()

    if args.mode == "register" and (not args.reg or not args.name):
        print("Error: --reg and --name are required for registration mode.")
        sys.exit(1)

    app = KioskApp(mode=args.mode, subject_id=args.subject, reg_number=args.reg, name=args.name)
    app.mainloop()
