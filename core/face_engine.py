"""
core/face_engine.py — InsightFace model singleton

Loads the InsightFace model ONCE and keeps it in memory.
train.py, recognize.py, and anti_spoof.py all import from here.
Loading once saves ~3-4 seconds on every script run.

Usage:
    from core.face_engine import get_engine
    engine = get_engine()
    faces  = engine.get(frame)   # returns list of Face objects
"""

import logging
import threading
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

_engine   = None
_lock     = threading.Lock()


def get_engine():
    """
    Return the shared InsightFace FaceAnalysis instance.
    Creates it on first call, returns cached instance after that.
    Thread-safe via lock.
    """
    global _engine
    if _engine is not None:
        return _engine

    with _lock:
        if _engine is not None:   # double-check inside lock
            return _engine

        try:
            import insightface
            from insightface.app import FaceAnalysis
            from config import MODEL_NAME
        except ImportError as e:
            logger.critical(f"InsightFace not installed: {e}")
            raise SystemExit(
                "\nInsightFace is not installed.\n"
                "Run:  pip install insightface onnxruntime\n"
            )

        logger.info(f"Loading InsightFace model: {MODEL_NAME}  (first load ~5s) ...")

        app = FaceAnalysis(
            name       = MODEL_NAME,
            providers  = ["CPUExecutionProvider"],   # CPU only — works on Pi and laptop
        )
        # det_size: detection resolution. 320x320 is faster and perfectly fine for
        # close-range attendance scanning. 640x640 only needed for detecting small
        # faces across a large room. Lower = faster FPS.
        app.prepare(ctx_id=0, det_size=(320, 320))

        _engine = app
        logger.info("InsightFace model loaded and ready.")

    return _engine


def get_embedding(frame: np.ndarray) -> tuple[np.ndarray | None, tuple | None]:
    """
    Detect the largest face in frame and return its 512D embedding + bounding box.

    Args:
        frame: BGR numpy array from camera.

    Returns:
        (embedding, bbox) where embedding is shape (512,) float32
        and bbox is (x1, y1, x2, y2), or (None, None) if no face found.
    """
    engine = get_engine()
    faces  = engine.get(frame)

    if not faces:
        return None, None

    # pick the largest face by bounding box area
    face = max(faces, key=lambda f: (
        (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
    ))

    embedding = face.normed_embedding   # already L2-normalised, shape (512,)
    bbox      = tuple(int(v) for v in face.bbox)   # (x1, y1, x2, y2)
    return embedding, bbox


def get_all_faces(frame: np.ndarray) -> list:
    """
    Return ALL detected Face objects in the frame.
    Used in recognize.py for multi-face classrooms.
    """
    engine = get_engine()
    return engine.get(frame)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two normalised embeddings.
    Since InsightFace returns normed_embedding (already L2-normalised),
    this is just the dot product.

    Returns value between -1 and 1.
    Threshold: > 0.55 = same person (configurable in config.py).
    """
    return float(np.dot(a, b))
