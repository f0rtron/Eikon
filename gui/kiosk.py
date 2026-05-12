"""
gui/kiosk.py — Fullscreen door-mount kiosk terminal

Single-student flow:
  IDLE → face detected → SCANNING (8 frames) → MARKED / LATE / REJECTED → IDLE

States:
  idle      — pulsing circle, "Please look at the camera"
  scanning  — progress bar filling over 0.5s
  present   — full green screen, student name
  late      — full amber screen, student name + LATE
  duplicate — blue screen, already marked today
  unknown   — red screen, face not registered
  spoof     — red screen, present your real face

Run:
    python gui/kiosk.py --subject 1
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk
from PIL import Image, ImageTk

from core.recognize import RecognitionEngine, draw_overlay
from utils.camera import Camera

logger = logging.getLogger(__name__)

# ─── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# State colours (R, G, B) as hex strings
_STATE_COLOURS = {
    "idle":      "#0F172A",   # dark slate
    "scanning":  "#1E3A5F",   # dark blue
    "present":   "#14532D",   # dark green
    "late":      "#78350F",   # dark amber
    "duplicate": "#1E3A5F",   # dark blue
    "unknown":   "#7F1D1D",   # dark red
    "spoof":     "#450A0A",   # very dark red
}

_STATE_TEXT_COLOUR = {
    "idle":      "#94A3B8",
    "scanning":  "#93C5FD",
    "present":   "#4ADE80",
    "late":      "#FCD34D",
    "duplicate": "#93C5FD",
    "unknown":   "#FCA5A5",
    "spoof":     "#FCA5A5",
}

_CONFIRM_FRAMES = 8      # frames needed before marking
_RESET_DELAY    = 2.5    # seconds before returning to idle after result


class KioskApp(ctk.CTk):
    def __init__(self, subject_id: int):
        super().__init__()

        self.subject_id = subject_id
        self.engine     = None   # loaded in background thread
        self.camera     = None

        # ── state machine ─────────────────────────────────────────────────────
        self._state         = "idle"
        self._confirm_count = 0
        self._confirm_reg   = None    # reg_number being confirmed
        self._reset_timer   = None
        self._pulse_angle   = 0
        self._frame_lock    = threading.Lock()
        self._latest_frame  = None
        self._running       = True

        # ── window ────────────────────────────────────────────────────────────
        self.title("Smart Attendance — Kiosk")
        self.attributes("-fullscreen", True)
        self.configure(fg_color=_STATE_COLOURS["idle"])
        self.bind("<Escape>", lambda e: self._shutdown())
        self.bind("<F11>",    lambda e: self.attributes("-fullscreen",
                              not self.attributes("-fullscreen")))

        self._build_ui()
        self._start_engine_thread()
        self._update_loop()

    # ─── UI build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # main frame
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        # top bar
        top = ctk.CTkFrame(self.main_frame, fg_color="#0F172A", height=56, corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="🎓  Smart Attendance System",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#E2E8F0").pack(side="left", padx=20, pady=14)

        self.time_label = ctk.CTkLabel(top, text="",
                                       font=ctk.CTkFont(size=16),
                                       text_color="#94A3B8")
        self.time_label.pack(side="right", padx=20)

        self.date_label = ctk.CTkLabel(top, text="",
                                       font=ctk.CTkFont(size=13),
                                       text_color="#64748B")
        self.date_label.pack(side="right", padx=4)

        # centre content
        centre = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        centre.pack(fill="both", expand=True, padx=40, pady=20)

        # left — camera feed
        left = ctk.CTkFrame(centre, fg_color="#1E293B", corner_radius=16)
        left.pack(side="left", fill="both", expand=True, padx=(0,20))

        self.camera_label = ctk.CTkLabel(left, text="", fg_color="#1E293B", corner_radius=12)
        self.camera_label.pack(fill="both", expand=True, padx=12, pady=12)

        self.loading_label = ctk.CTkLabel(
            left, text="Loading recognition model...",
            font=ctk.CTkFont(size=14), text_color="#64748B"
        )
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")

        # right — status panel
        right = ctk.CTkFrame(centre, fg_color="#1E293B", corner_radius=16, width=380)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # canvas for animated circle
        self.canvas = ctk.CTkCanvas(right, width=200, height=200,
                                    bg="#1E293B", highlightthickness=0)
        self.canvas.pack(pady=(40, 20))

        self.status_name = ctk.CTkLabel(
            right, text="Smart Attendance",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#E2E8F0", wraplength=340
        )
        self.status_name.pack(pady=(0, 8))

        self.status_msg = ctk.CTkLabel(
            right, text="Please look at the camera",
            font=ctk.CTkFont(size=15),
            text_color="#94A3B8", wraplength=340
        )
        self.status_msg.pack(pady=(0, 20))

        # progress bar (shown during scanning)
        self.progress_bar = ctk.CTkProgressBar(right, width=280, height=8,
                                               fg_color="#334155",
                                               progress_color="#3B82F6")
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0, 20))
        self.progress_bar.pack_forget()   # hidden initially

        # subject + today count
        self.subject_label = ctk.CTkLabel(
            right, text=f"Subject: CS-101",
            font=ctk.CTkFont(size=12), text_color="#475569"
        )
        self.subject_label.pack(side="bottom", pady=(0, 8))

        self.count_label = ctk.CTkLabel(
            right, text="Today: 0 marked",
            font=ctk.CTkFont(size=12), text_color="#475569"
        )
        self.count_label.pack(side="bottom", pady=(0, 4))

        # bottom info bar
        bottom = ctk.CTkFrame(self.main_frame, fg_color="#0F172A", height=36, corner_radius=0)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        ctk.CTkLabel(bottom, text="Press ESC to exit  |  F11 to toggle fullscreen",
                     font=ctk.CTkFont(size=11), text_color="#334155").pack(pady=8)

    # ─── Engine startup (background thread) ───────────────────────────────────

    def _start_engine_thread(self):
        def _load():
            try:
                self.engine = RecognitionEngine(subject_id=self.subject_id)
                self.camera = Camera(source=0)
                self.camera.start()
                self.loading_label.configure(text="")
                logger.info("Kiosk engine loaded.")
                self._update_subject_label()
            except Exception as e:
                logger.error(f"Engine load failed: {e}")
                self.loading_label.configure(text=f"Error: {e}")

        threading.Thread(target=_load, daemon=True).start()

    def _update_subject_label(self):
        from db.connection import db_session
        from db.models import Subject
        with db_session() as session:
            s = session.get(Subject, self.subject_id)
            if s:
                self.subject_label.configure(text=f"Subject: {s.code} — {s.name}")

    # ─── Main update loop ─────────────────────────────────────────────────────

    def _update_loop(self):
        if not self._running:
            return

        now = datetime.now()
        self.time_label.configure(text=now.strftime("%H:%M:%S"))
        self.date_label.configure(text=now.strftime("%A, %d %B %Y"))

        if self.engine and self.camera:
            self._process_frame()

        self._animate_canvas()
        self.after(33, self._update_loop)   # ~30 FPS

    def _process_frame(self):
        frame = self.camera.read()
        if frame is None:
            return

        # run recognition
        results = self.engine.process_frame(frame)

        # draw overlay on frame copy for camera display
        display = frame.copy()
        draw_overlay(display, results)

        # show frame in camera label
        self._show_frame(display)

        # state machine
        if self._state in ("present", "late", "duplicate", "unknown", "spoof"):
            return   # waiting for reset timer

        if not results:
            self._set_state("idle")
            self._confirm_count = 0
            self._confirm_reg   = None
            return

        # take the first (largest) face result
        r = results[0]

        if r.status == "spoof":
            self._set_state("spoof", name="⚠ Spoof Detected",
                            msg="Please present your actual face")
            self._schedule_reset()
            return

        if r.status == "unknown":
            self._set_state("scanning")
            return

        if r.status == "duplicate":
            self._set_state("duplicate", name=r.name,
                            msg="Already marked present today")
            self._schedule_reset()
            return

        # known face — accumulate confirmation frames
        if r.reg_number == self._confirm_reg:
            self._confirm_count += 1
        else:
            self._confirm_reg   = r.reg_number
            self._confirm_count = 1

        progress = self._confirm_count / _CONFIRM_FRAMES
        self._set_state("scanning", progress=progress,
                        name=r.name, msg="Verifying...")

        if self._confirm_count >= _CONFIRM_FRAMES:
            # confirmed — check if already marked or just marked
            if r.marked:
                final_state = r.status   # "present" or "late"
                msg = "✓ Attendance Marked!" if final_state == "present" else "⚠ Marked — Late Arrival"
            else:
                final_state = "duplicate"
                msg = "Already marked today"

            self._set_state(final_state, name=r.name, msg=msg)
            self._update_count_label()
            self._confirm_count = 0
            self._confirm_reg   = None
            self._schedule_reset()

    def _show_frame(self, frame):
        try:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(rgb)
            # scale to fit label
            w     = self.camera_label.winfo_width()  or 640
            h     = self.camera_label.winfo_height() or 480
            img   = img.resize((w, h), Image.LANCZOS)
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self.camera_label.configure(image=photo, text="")
            self.camera_label._image = photo   # prevent GC
        except Exception:
            pass

    # ─── State machine ────────────────────────────────────────────────────────

    def _set_state(self, state, name="", msg="", progress=0.0):
        self._state = state
        bg = _STATE_COLOURS.get(state, "#0F172A")
        tc = _STATE_TEXT_COLOUR.get(state, "#E2E8F0")

        self.configure(fg_color=bg)
        self.main_frame.configure(fg_color=bg)

        if state == "idle":
            self.status_name.configure(text="Smart Attendance", text_color="#E2E8F0")
            self.status_msg.configure(text="Please look at the camera", text_color="#94A3B8")
            self.progress_bar.pack_forget()
        elif state == "scanning":
            self.status_name.configure(text=name or "Scanning...", text_color="#93C5FD")
            self.status_msg.configure(text=msg or "Hold still...", text_color="#CBD5E1")
            self.progress_bar.pack(pady=(0, 20))
            self.progress_bar.set(progress)
            self.progress_bar.configure(progress_color="#3B82F6")
        elif state in ("present", "late"):
            self.status_name.configure(text=name, text_color=tc, font=ctk.CTkFont(size=28, weight="bold"))
            self.status_msg.configure(text=msg, text_color=tc)
            self.progress_bar.pack(pady=(0, 20))
            self.progress_bar.set(1.0)
            colour = "#22C55E" if state == "present" else "#F59E0B"
            self.progress_bar.configure(progress_color=colour)
        else:
            self.status_name.configure(text=name or state.capitalize(),
                                       text_color=tc, font=ctk.CTkFont(size=22, weight="bold"))
            self.status_msg.configure(text=msg, text_color=tc)
            self.progress_bar.pack_forget()

    def _schedule_reset(self):
        if self._reset_timer:
            self.after_cancel(self._reset_timer)
        self._reset_timer = self.after(
            int(_RESET_DELAY * 1000),
            lambda: self._set_state("idle")
        )

    def _update_count_label(self):
        try:
            from db.connection import db_session
            from db.models import Attendance
            from datetime import date
            from sqlalchemy import func
            with db_session() as session:
                count = session.query(func.count(Attendance.id))\
                    .filter(Attendance.subject_id==self.subject_id,
                            Attendance.marked_date==date.today()).scalar() or 0
            self.count_label.configure(text=f"Today: {count} marked")
        except Exception:
            pass

    # ─── Canvas animation ─────────────────────────────────────────────────────

    def _animate_canvas(self):
        self.canvas.delete("all")
        cx, cy, r = 100, 100, 70

        if self._state == "idle":
            # pulsing ring
            self._pulse_angle = (self._pulse_angle + 3) % 360
            pulse = 0.5 + 0.5 * math.sin(math.radians(self._pulse_angle))
            alpha = int(80 + 100 * pulse)
            col   = f"#{alpha:02x}{alpha:02x}ff"
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline=col, width=3, fill="")
            self.canvas.create_oval(cx-20, cy-20, cx+20, cy+20,
                                    outline="#475569", fill="#1E293B", width=2)
            # face icon dots
            self.canvas.create_oval(cx-8, cy-8, cx-2, cy-2, fill="#64748B", outline="")
            self.canvas.create_oval(cx+2, cy-8, cx+8, cy-2, fill="#64748B", outline="")
            self.canvas.create_arc(cx-10, cy, cx+10, cy+10,
                                   start=200, extent=140, style="arc",
                                   outline="#64748B", width=2)

        elif self._state == "scanning":
            self._pulse_angle = (self._pulse_angle + 6) % 360
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#1E40AF", width=4, fill="")
            extent = int(360 * (self._confirm_count / _CONFIRM_FRAMES))
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r,
                                   start=90, extent=-extent,
                                   outline="#3B82F6", width=4, style="arc")
            self.canvas.create_text(cx, cy, text=f"{int(extent/3.6)}%",
                                    fill="#93C5FD", font=("Inter", 18, "bold"))

        elif self._state == "present":
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#22C55E", width=4, fill="#14532D")
            self.canvas.create_text(cx, cy, text="✓",
                                    fill="#4ADE80", font=("Inter", 48, "bold"))

        elif self._state == "late":
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#F59E0B", width=4, fill="#78350F")
            self.canvas.create_text(cx, cy, text="⚠",
                                    fill="#FCD34D", font=("Inter", 40, "bold"))

        elif self._state in ("unknown", "spoof"):
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#EF4444", width=4, fill="#7F1D1D")
            self.canvas.create_text(cx, cy, text="✗",
                                    fill="#FCA5A5", font=("Inter", 48, "bold"))

        elif self._state == "duplicate":
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#3B82F6", width=4, fill="#1E3A5F")
            self.canvas.create_text(cx, cy, text="↩",
                                    fill="#93C5FD", font=("Inter", 40, "bold"))

    # ─── Cleanup ──────────────────────────────────────────────────────────────

    def _shutdown(self):
        self._running = False
        if self.camera:
            self.camera.release()
        self.destroy()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Attendance Kiosk")
    parser.add_argument("--subject", type=int, default=1,
                        help="Subject ID to mark attendance for")
    args = parser.parse_args()

    app = KioskApp(subject_id=args.subject)
    app.mainloop()
