"""
core/register.py — Student registration and face image capture

Captures IMAGES_PER_STUDENT face images for a new student,
saves them to dataset/<reg_number>/, and creates the student
record in MySQL.

Usage (standalone):
    python core/register.py

Usage (from other code):
    from core.register import register_student
    register_student(reg_number="G1F22UBSCS173", name="Fahad Gujjar")
"""

import cv2
import logging
import sys
import time
from pathlib import Path

# ─── allow running as a standalone script from project root ───────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATASET_DIR, IMAGES_PER_STUDENT
from db.connection import db_session
from db.models import Student
from utils.camera import Camera

logger = logging.getLogger(__name__)


# ─── Face detector (fast Haar cascade — only needed during registration) ──────
_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_detector = cv2.CascadeClassifier(_CASCADE_PATH)


def _detect_face(frame):
    """
    Return the largest face bounding box (x, y, w, h) or None.
    Uses Haar cascade — fast and good enough for controlled registration.
    InsightFace is used for the actual recognition in recognize.py.
    """
    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _face_detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80),
    )
    if len(faces) == 0:
        return None
    # return the largest detected face
    return max(faces, key=lambda f: f[2] * f[3])


def _draw_overlay(frame, count: int, total: int, face_box=None, status: str = ""):
    """
    Draw progress overlay on the live camera feed during registration.
    Green box = face detected, Red box = no face.
    """
    display = frame.copy()
    h, w    = display.shape[:2]

    # ── face bounding box ────────────────────────────────────────────────────
    if face_box is not None:
        x, y, fw, fh = face_box
        color = (0, 200, 0)   # green — face detected
        cv2.rectangle(display, (x, y), (x + fw, y + fh), color, 2)
        label = f"Face detected — {count}/{total} captured"
        cv2.putText(display, label, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    else:
        msg = "No face detected — look at the camera"
        cv2.putText(display, msg, (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)

    # ── progress bar ─────────────────────────────────────────────────────────
    bar_x, bar_y, bar_w, bar_h = 20, h - 40, w - 40, 18
    cv2.rectangle(display, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    filled = int(bar_w * count / total)
    if filled > 0:
        cv2.rectangle(display, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h), (0, 200, 0), -1)
    cv2.putText(display, f"{count}/{total}", (bar_x + bar_w + 8, bar_y + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # ── status text ──────────────────────────────────────────────────────────
    if status:
        cv2.putText(display, status, (20, h - 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 220), 2)

    # ── instructions ─────────────────────────────────────────────────────────
    cv2.putText(display, "Press Q to cancel", (20, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

    return display


def capture_faces(reg_number: str, name: str, target_count: int = None) -> int:
    """
    Open the camera, guide the user to look at different angles,
    and save face images to dataset/<reg_number>/.

    Args:
        reg_number:   Student registration number (used as folder name).
        name:         Student name (shown on screen).
        target_count: Number of images to capture (default from config).

    Returns:
        Number of images actually saved (0 if cancelled or failed).
    """
    if target_count is None:
        target_count = IMAGES_PER_STUDENT

    # ── create student dataset folder ─────────────────────────────────────────
    student_dir = DATASET_DIR / reg_number
    student_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving face images to: {student_dir}")

    saved      = 0
    last_saved = 0.0          # timestamp of last save (enforce spacing)
    MIN_INTERVAL = 0.2        # seconds between captures (avoid near-duplicates)

    # Guidance messages shown in sequence to encourage varied angles
    GUIDANCE = [
        "Look straight at the camera",
        "Tilt head slightly left",
        "Tilt head slightly right",
        "Look slightly up",
        "Look slightly down",
        "Neutral expression",
    ]

    with Camera() as cam:
        logger.info("Camera opened for registration.")
        window_name = f"Registration — {name} ({reg_number})"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 800, 600)

        while saved < target_count:
            frame = cam.read()
            if frame is None:
                logger.warning("Empty frame — skipping.")
                continue

            face_box = _detect_face(frame)
            now      = time.time()
            guidance = GUIDANCE[min(saved // (target_count // len(GUIDANCE)), len(GUIDANCE) - 1)]

            # ── auto-capture when face is detected at intervals ───────────────
            if face_box is not None and (now - last_saved) >= MIN_INTERVAL:
                x, y, fw, fh = face_box
                # add 20% padding around the detected face
                pad   = int(max(fw, fh) * 0.2)
                x1    = max(0, x - pad)
                y1    = max(0, y - pad)
                x2    = min(frame.shape[1], x + fw + pad)
                y2    = min(frame.shape[0], y + fh + pad)
                face_crop = frame[y1:y2, x1:x2]

                img_path = student_dir / f"{saved + 1:03d}.jpg"
                cv2.imwrite(str(img_path), face_crop)
                saved     += 1
                last_saved = now
                logger.debug(f"Saved: {img_path}")

            overlay = _draw_overlay(frame, saved, target_count, face_box, guidance)
            cv2.imshow(window_name, overlay)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Registration cancelled by user.")
                break

        cv2.destroyAllWindows()

    logger.info(f"Registration complete — {saved}/{target_count} images saved for {reg_number}.")
    return saved


def register_student(
    reg_number: str,
    name: str,
    email: str       = "",
    class_name: str  = "",
    capture: bool    = True,
) -> Student | None:
    """
    Full registration flow:
      1. Check if student already exists in DB.
      2. Capture face images (if capture=True).
      3. Save student record to MySQL.

    Args:
        reg_number: Unique registration / roll number.
        name:       Full name.
        email:      Optional email for absence alerts.
        class_name: e.g. "BSCS-6A".
        capture:    If False, skip camera capture (useful for testing).

    Returns:
        Student ORM object on success, None on failure.
    """
    logger.info(f"Starting registration: {reg_number} — {name}")

    # ── check for duplicate ───────────────────────────────────────────────────
    with db_session() as session:
        existing = session.query(Student).filter_by(reg_number=reg_number).first()
        if existing:
            logger.warning(f"Student {reg_number} already registered.")
            print(f"\n  Student {reg_number} already exists in the database.")
            return existing

    # ── capture face images ───────────────────────────────────────────────────
    dataset_path = str(DATASET_DIR / reg_number)
    saved_count  = 0

    if capture:
        print(f"\n  Starting face capture for {name}.")
        print(f"  Please look at the camera. {IMAGES_PER_STUDENT} images will be captured.")
        print(f"  Press Q to cancel.\n")
        saved_count = capture_faces(reg_number, name)

        if saved_count < 10:
            logger.error(f"Only {saved_count} images captured — minimum 10 required.")
            print(f"\n  Registration failed: only {saved_count} images captured.")
            print("  Please try again in better lighting and keep your face visible.")
            return None
    else:
        logger.info("Skipping capture (capture=False).")

    # ── save to database ──────────────────────────────────────────────────────
    with db_session() as session:
        student = Student(
            reg_number   = reg_number,
            name         = name,
            email        = email or None,
            class_name   = class_name or None,
            dataset_path = dataset_path,
            is_encoded   = False,     # set to True after train.py runs
        )
        session.add(student)
        # flush to get the auto-generated id before commit
        session.flush()
        student_id = student.id
        logger.info(f"Student saved to DB — id={student_id}, reg={reg_number}")

    print(f"\n  Registration complete!")
    print(f"  Name:         {name}")
    print(f"  Reg number:   {reg_number}")
    print(f"  Images saved: {saved_count}")
    print(f"  Next step:    run  python core/train.py  to generate face encodings.\n")

    # return a fresh session object
    with db_session() as session:
        return session.query(Student).get(student_id)


# ─── CLI entry point ──────────────────────────────────────────────────────────

def _cli():
    print("\n=== Smart Attendance — Student Registration ===\n")
    reg_number = input("  Registration number (e.g. G1F22UBSCS173): ").strip()
    name       = input("  Full name: ").strip()
    email      = input("  Email (optional, press Enter to skip): ").strip()
    class_name = input("  Class (e.g. BSCS-6A, optional): ").strip()

    if not reg_number or not name:
        print("\n  Error: registration number and name are required.")
        sys.exit(1)

    student = register_student(
        reg_number = reg_number,
        name       = name,
        email      = email,
        class_name = class_name,
        capture    = True,
    )

    if student:
        print("  Student registered successfully.")
    else:
        print("  Registration failed. Check logs/app.log for details.")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
