"""
utils/camera.py — Hardware-agnostic camera abstraction

Auto-detects whether it is running on a Raspberry Pi or a laptop/desktop.
Every other module in the project calls Camera() — nothing else ever
touches VideoCapture or PiCamera2 directly.

Usage:
    from utils.camera import Camera

    cam = Camera()
    cam.start()
    frame = cam.read()   # always returns a standard BGR numpy array
    cam.release()

    # Or as a context manager:
    with Camera() as cam:
        frame = cam.read()
"""

import logging
import platform
import cv2
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_raspberry_pi() -> bool:
    """
    Detect Raspberry Pi by reading /proc/cpuinfo.
    Works on all Pi models (Zero, 3, 4, 5).
    Falls back gracefully on non-Linux systems.
    """
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        return "raspberry pi" in cpuinfo.lower() or "bcm2" in cpuinfo.lower()
    except (FileNotFoundError, PermissionError):
        return False


class Camera:
    """
    Unified camera interface for both laptop (OpenCV) and
    Raspberry Pi (PiCamera2). Returns standard BGR frames regardless
    of hardware — all downstream code stays identical.
    """

    def __init__(self, source: int = 0, width: int = 640, height: int = 480, fps: int = 30):
        """
        Args:
            source: Camera index for OpenCV (ignored on Pi — Pi has one camera).
            width:  Capture width in pixels.
            height: Capture height in pixels.
            fps:    Target frames per second.
        """
        self.source  = source
        self.width   = width
        self.height  = height
        self.fps     = fps
        self._cap    = None          # OpenCV VideoCapture object
        self._picam  = None          # PiCamera2 object
        self._is_pi  = _is_raspberry_pi()
        self._active = False

        logger.info(
            f"Camera init — platform: {'Raspberry Pi' if self._is_pi else 'laptop/desktop'} "
            f"| resolution: {width}x{height} | fps: {fps}"
        )

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> "Camera":
        """Open the camera. Call before read(). Returns self for chaining."""
        if self._is_pi:
            self._start_picamera()
        else:
            self._start_opencv()
        self._active = True
        return self

    def release(self):
        """Release all camera resources. Always call this when done."""
        self._active = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("OpenCV camera released.")
        if self._picam is not None:
            self._picam.stop()
            self._picam.close()
            self._picam = None
            logger.info("PiCamera2 released.")

    # ─── Frame Reading ────────────────────────────────────────────────────────

    def read(self) -> np.ndarray | None:
        """
        Capture one frame.
        Returns a BGR numpy array (H, W, 3) or None on failure.
        InsightFace and OpenCV both expect BGR — no conversion needed.
        """
        if not self._active:
            logger.warning("Camera.read() called before start().")
            return None

        if self._is_pi:
            return self._read_picamera()
        else:
            return self._read_opencv()

    def read_rgb(self) -> np.ndarray | None:
        """
        Capture one frame in RGB (for Tkinter / PIL display).
        Converts BGR → RGB automatically.
        """
        frame = self.read()
        if frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # ─── Internal — OpenCV (laptop / USB webcam) ──────────────────────────────

    def _start_opencv(self):
        logger.info(f"Opening OpenCV VideoCapture(source={self.source})")
        self._cap = cv2.VideoCapture(self.source)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at index {self.source}. "
                "Check that a webcam is connected and not in use by another app."
            )

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS,          self.fps)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"OpenCV camera opened — actual resolution: {actual_w}x{actual_h}")

    def _read_opencv(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning("OpenCV: failed to read frame.")
            return None
        return frame

    # ─── Internal — PiCamera2 (Raspberry Pi) ──────────────────────────────────

    def _start_picamera(self):
        try:
            from picamera2 import Picamera2   # only available on Pi OS
            from libcamera import controls     # noqa: F401

            logger.info("Initialising PiCamera2...")
            self._picam = Picamera2()

            config = self._picam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            self._picam.configure(config)

            # Auto-exposure + auto white balance
            self._picam.set_controls({
                "AeEnable":  True,
                "AwbEnable": True,
            })

            self._picam.start()
            logger.info(f"PiCamera2 started — resolution: {self.width}x{self.height}")

        except ImportError:
            logger.error(
                "picamera2 not found. On Raspberry Pi OS it should be pre-installed. "
                "Try: sudo apt install python3-picamera2"
            )
            raise RuntimeError("PiCamera2 unavailable. See logs for details.")

    def _read_picamera(self) -> np.ndarray | None:
        try:
            # PiCamera2 returns RGB888 — convert to BGR for OpenCV/InsightFace
            rgb_frame = self._picam.capture_array()
            bgr_frame  = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
            return bgr_frame
        except Exception as e:
            logger.error(f"PiCamera2 read error: {e}")
            return None

    # ─── Context Manager ──────────────────────────────────────────────────────

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.release()

    # ─── Properties ───────────────────────────────────────────────────────────

    @property
    def is_pi(self) -> bool:
        return self._is_pi

    @property
    def is_active(self) -> bool:
        return self._active

    def __repr__(self):
        hw = "Pi" if self._is_pi else "laptop"
        return f"<Camera [{hw}] {self.width}x{self.height} active={self._active}>"
