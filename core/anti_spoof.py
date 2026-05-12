"""
core/anti_spoof.py — Liveness detection (anti-spoofing)

Prevents the system from being fooled by:
  - Printed photographs
  - Photos shown on a phone/tablet screen
  - Videos played back

Uses texture analysis (Local Binary Patterns) as the primary method.
LBP is lightweight, runs fast on Raspberry Pi, and requires no extra models.

For higher security, MiniFASNet model can be plugged in as a drop-in
replacement — the interface stays identical.

Usage:
    from core.anti_spoof import AntiSpoof
    spoof = AntiSpoof()
    is_live, score = spoof.check(face_crop)
    if not is_live:
        print("Spoof detected!")
"""

import cv2
import logging
import numpy as np
from config import ANTI_SPOOF_THRESHOLD

logger = logging.getLogger(__name__)


class AntiSpoof:
    """
    Liveness detector using texture analysis.

    Real faces have micro-texture (skin pores, hair, subtle movement).
    Printed photos and screens look unnaturally smooth or have
    regular grid patterns (halftone dots, pixel grids).

    Score > threshold → real face (live)
    Score < threshold → spoof (reject)
    """

    def __init__(self, threshold: float = None):
        self.threshold   = threshold or ANTI_SPOOF_THRESHOLD
        self._history    = []         # rolling history for temporal smoothing
        self._history_n  = 5         # number of frames to average over

        logger.info(f"AntiSpoof initialised — threshold: {self.threshold}")

    def check(self, face_crop: np.ndarray) -> tuple[bool, float]:
        """
        Check if a face crop is a live face or a spoof attempt.

        Args:
            face_crop: BGR numpy array of the face region.

        Returns:
            (is_live: bool, score: float)
            score is between 0.0 and 1.0 — higher = more likely live.
        """
        if face_crop is None or face_crop.size == 0:
            return False, 0.0

        score = self._compute_score(face_crop)

        # temporal smoothing — average over last N frames
        self._history.append(score)
        if len(self._history) > self._history_n:
            self._history.pop(0)
        smoothed = float(np.mean(self._history))

        is_live = smoothed >= self.threshold
        return is_live, smoothed

    def reset_history(self):
        """Call this when switching to a different face / between recognitions."""
        self._history.clear()

    # ─── Score Computation ────────────────────────────────────────────────────

    def _compute_score(self, face_crop: np.ndarray) -> float:
        """
        Combine multiple texture cues into a single liveness score.
        Each cue returns 0.0–1.0, weighted and averaged.
        """
        # resize to fixed size for consistent computation
        face = cv2.resize(face_crop, (128, 128))

        scores = [
            self._lbp_texture_score(face)   * 0.5,   # strongest signal
            self._frequency_score(face)      * 0.3,   # screens have frequency artifacts
            self._gradient_score(face)       * 0.2,   # printed photos lack sharp gradients
        ]
        return float(np.clip(sum(scores), 0.0, 1.0))

    def _lbp_texture_score(self, face: np.ndarray) -> float:
        """
        Local Binary Pattern texture analysis.
        Real skin has rich, varied texture.
        Printed/screen faces have uniform texture.
        """
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

        # compute LBP manually (no skimage dependency needed)
        lbp     = self._compute_lbp(gray)
        hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
        hist    = hist.astype(float) / (hist.sum() + 1e-7)

        # entropy: higher entropy = richer texture = more likely real
        entropy = -np.sum(hist * np.log2(hist + 1e-7))
        # real faces: entropy typically 6.5–8.0; photos: 4.0–6.0
        score   = np.clip((entropy - 4.0) / 4.0, 0.0, 1.0)
        return float(score)

    def _frequency_score(self, face: np.ndarray) -> float:
        """
        Frequency domain analysis via DFT.
        Screens (monitors, phones) have regular high-frequency patterns.
        Real faces have organic frequency distribution.
        """
        gray    = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY).astype(np.float32)
        dft     = np.fft.fft2(gray)
        dft_mag = np.log(np.abs(np.fft.fftshift(dft)) + 1)

        h, w    = dft_mag.shape
        center  = dft_mag[h//4:3*h//4, w//4:3*w//4]
        outer   = dft_mag.mean() - center.mean()

        # real faces have relatively more energy in centre frequencies
        score = np.clip(0.5 + outer * 0.1, 0.0, 1.0)
        return float(score)

    def _gradient_score(self, face: np.ndarray) -> float:
        """
        Gradient richness check.
        Real faces have natural, complex gradients.
        Printed photos can look flat; phone screens over-sharpen edges.
        """
        gray    = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        gx      = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy      = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        mag     = np.sqrt(gx**2 + gy**2)

        # coefficient of variation: high variation = natural face
        mean    = mag.mean() + 1e-7
        std     = mag.std()
        cv_val  = std / mean
        score   = np.clip(cv_val / 2.0, 0.0, 1.0)
        return float(score)

    @staticmethod
    def _compute_lbp(gray: np.ndarray) -> np.ndarray:
        """
        Fast LBP computation without scikit-image.
        Compares each pixel to its 8 neighbours, builds binary code.
        """
        h, w   = gray.shape
        lbp    = np.zeros((h - 2, w - 2), dtype=np.uint8)
        center = gray[1:-1, 1:-1]

        offsets = [
            gray[0:-2, 0:-2], gray[0:-2, 1:-1], gray[0:-2, 2:],
            gray[1:-1, 2:],
            gray[2:,   2:],   gray[2:,   1:-1], gray[2:,   0:-2],
            gray[1:-1, 0:-2],
        ]

        for bit, neighbour in enumerate(offsets):
            lbp |= ((neighbour >= center).astype(np.uint8) << bit)

        return lbp


# ─── Module-level singleton ───────────────────────────────────────────────────

_spoof_checker = None

def get_spoof_checker() -> AntiSpoof:
    """Return a shared AntiSpoof instance (created once)."""
    global _spoof_checker
    if _spoof_checker is None:
        _spoof_checker = AntiSpoof()
    return _spoof_checker
