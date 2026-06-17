"""
utils/camera.py — Hardware-agnostic camera abstraction

Auto-detects whether it is running on a Raspberry Pi or a laptop/desktop.
Every other module in the project calls Camera() — nothing else ever
touches VideoCapture or PiCamera2 directly.

Optimised for network cameras (DroidCam, IP cam):
  - Uses MJPEG backend for faster decoding when available
  - Threaded frame reader to prevent recognition loop from blocking
  - Buffer size = 1 to always get the freshest frame

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
import threading
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


def _is_network_source(source) -> bool:
    """
    Detect whether the camera source is a network stream (DroidCam, IP cam)
    vs a local USB/built-in webcam.
    """
    if isinstance(source, str):
        return source.startswith(("http://", "https://", "rtsp://"))
    return False


class _ThreadedReader:
    """
    Reads frames from a VideoCapture in a background thread.
    Always holds the LATEST frame — recognition loop never blocks waiting
    for the slow network camera to deliver the next frame.
    """

    def __init__(self, cap: cv2.VideoCapture):
        self._cap   = cap
        self._frame = None
        self._lock  = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame

    def read(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)


class Camera:
    """
    Unified camera interface for both laptop (OpenCV) and
    Raspberry Pi (PiCamera2). Returns standard BGR frames regardless
    of hardware — all downstream code stays identical.
    """

    def __init__(self, source = None, width: int = None, height: int = None, fps: int = 30):
        """
        Args:
            source: Camera index or stream URL for OpenCV (ignored on Pi — Pi has one camera).
                    Defaults to CAMERA_SOURCE from config.py if None.
            width:  Capture width in pixels. Defaults to CAMERA_WIDTH from config.py if None.
            height: Capture height in pixels. Defaults to CAMERA_HEIGHT from config.py if None.
            fps:    Target frames per second.
        """
        try:
            from config import CAMERA_SOURCE, CAMERA_WIDTH, CAMERA_HEIGHT
        except ImportError:
            CAMERA_SOURCE = 0
            CAMERA_WIDTH = 640
            CAMERA_HEIGHT = 480

        if source is None:
            source = CAMERA_SOURCE
        if width is None:
            width = CAMERA_WIDTH
        if height is None:
            height = CAMERA_HEIGHT

        self.source  = source
        self.width   = width
        self.height  = height
        self.fps     = fps
        self._cap    = None          # OpenCV VideoCapture object
        self._picam  = None          # PiCamera2 object
        self._reader = None          # Threaded reader for network cameras
        self._is_pi  = _is_raspberry_pi()
        self._is_network = _is_network_source(source)
        self._active = False

        logger.info(
            f"Camera init — platform: {'Raspberry Pi' if self._is_pi else 'laptop/desktop'} "
            f"| source: {self.source} | resolution: {width}x{height} | fps: {fps}"
            f"{'  [NETWORK STREAM]' if self._is_network else ''}"
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
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
            logger.info("Threaded frame reader stopped.")
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
        elif self._reader is not None:
            return self._reader.read()
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

    # ─── Internal — OpenCV (laptop / USB webcam / DroidCam) ───────────────────

    def _start_opencv(self):
        logger.info(f"Opening OpenCV VideoCapture(source={self.source})")

        if self._is_network:
            # Network streams (DroidCam URL, IP cam): use MJPEG backend
            # for faster decoding than the default FFMPEG
            logger.info("Network source detected — using CAP_ANY with MJPEG optimisations")
            self._cap = cv2.VideoCapture(self.source, cv2.CAP_ANY)
        else:
            # Local webcam / DroidCam virtual device
            self._cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)

        if not self._cap.isOpened():
            # Fallback without specific backend
            logger.warning("Primary backend failed, trying default...")
            self._cap = cv2.VideoCapture(self.source)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at source '{self.source}'. "
                "Check that a webcam is connected and not in use by another app."
            )

        # Force MJPEG codec for DroidCam virtual devices — much faster than YUY2
        # DroidCam devices appear as local webcams (integer index) but stream MJPEG
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS,          self.fps)
        
        if not self._is_network:
            # Force MJPEG codec for higher FPS on HD webcams.
            # Must be set AFTER width/height/fps on some OpenCV DSHOW versions
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            self._cap.set(cv2.CAP_PROP_FOURCC, fourcc)

        # Buffer size = 1: always grab the freshest frame, discard stale ones.
        # Without this, OpenCV queues up to 5 frames — you see ~200ms old video.
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fourcc = int(self._cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((actual_fourcc >> 8*i) & 0xFF) for i in range(4)])
        logger.info(f"OpenCV camera opened — resolution: {actual_w}x{actual_h} codec: {fourcc_str}")

        # Start threaded reader for network sources (non-blocking reads)
        if self._is_network:
            logger.info("Starting threaded frame reader for network stream...")
            self._reader = _ThreadedReader(self._cap)

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
        net = " [NET]" if self._is_network else ""
        return f"<Camera [{hw}{net}] {self.width}x{self.height} active={self._active}>"
