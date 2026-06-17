"""
core/register.py — Professional Guided Student Registration

Handles real-time guided face capture with:
  - Quality checks (blur, brightness, centering)
  - Pose guidance (Straight, Left, Right, Up, Down)
  - Kiosk-ready state machine (RegistrationSession)
"""

import cv2
import logging
import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATASET_DIR, IMAGES_PER_STUDENT
from db.connection import db_session
from db.models import Student
from utils.camera import Camera

logger = logging.getLogger(__name__)

# Fast Haar cascade for registration
_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_detector = cv2.CascadeClassifier(_CASCADE_PATH)


class RegistrationQuality:
    """Helper to check face frame quality."""
    
    @staticmethod
    def check(frame, face_box):
        x, y, w, h = face_box
        fh, fw = frame.shape[:2]
        
        # 1. Centering
        face_center_x, face_center_y = x + w/2, y + h/2
        frame_center_x, frame_center_y = fw/2, fh/2
        dist_x = abs(face_center_x - frame_center_x) / fw
        dist_y = abs(face_center_y - frame_center_y) / fh
        
        if dist_x > 0.25 or dist_y > 0.25:
            return 0.0, "Please center your face in the oval"
            
        # 2. Size
        area_ratio = (w * h) / (fw * fh)
        if area_ratio < 0.05:
            return 0.0, "Move closer to the camera"
        if area_ratio > 0.5:
            return 0.0, "Move slightly back"
            
        # 3. Blur
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_crop = gray[y:y+h, x:x+w]
        blur_score = cv2.Laplacian(face_crop, cv2.CV_64F).var()
        if blur_score < 30:  # Relaxed from 80 for cheaper webcams
            return 0.0, "Hold still (blurry)"
            
        # 4. Brightness
        brightness = np.mean(face_crop)
        if brightness < 40:
            return 0.0, "Too dark — improve lighting"
        if brightness > 240:
            return 0.0, "Too bright — avoid harsh light"
            
        # Quality score based on blur and brightness (0-100)
        score = min(100, (blur_score / 300) * 50 + (1 - abs(140 - brightness)/140) * 50)
        return score, "Perfect"


class RegistrationSession:
    """
    State machine for guided registration. Designed to be consumed frame-by-frame
    by a GUI (like the Kiosk) or the CLI fallback.
    """
    POSES = [
        ("Look Straight", 10),
        ("Turn slightly Left", 5),
        ("Turn slightly Right", 5),
        ("Look slightly Up", 5),
        ("Look slightly Down", 5)
    ]
    
    def __init__(self, reg_number: str, name: str):
        self.reg_number = reg_number
        self.name = name
        self.student_dir = DATASET_DIR / reg_number
        self.student_dir.mkdir(parents=True, exist_ok=True)
        
        self.pose_idx = 0
        self.frames_saved_current_pose = 0
        self.total_saved = 0
        self.target_total = sum(count for _, count in self.POSES)
        
        self.last_capture_time = 0.0
        self.is_complete = False
        
    def get_current_instruction(self):
        if self.is_complete:
            return "Registration Complete"
        pose_name, target = self.POSES[self.pose_idx]
        return f"{pose_name} ({self.frames_saved_current_pose}/{target})"

    def process_frame(self, frame):
        """
        Processes a single frame.
        Returns: (state_dict, modified_frame_for_display)
        """
        if self.is_complete:
            return {"status": "complete", "progress": 1.0}, frame

        display = frame.copy()
        h, w = display.shape[:2]
        
        # Draw guidance oval
        center_x, center_y = w // 2, h // 2
        oval_w, oval_h = int(w * 0.25), int(h * 0.35)
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = _face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
        
        state = {
            "status": "scanning",
            "instruction": "Position face in the oval",
            "quality": 0,
            "progress": self.total_saved / self.target_total,
            "pose": self.POSES[self.pose_idx][0]
        }
        
        oval_color = (0, 0, 255) # Red by default

        if len(faces) > 0:
            # Largest face
            face_box = max(faces, key=lambda f: f[2] * f[3])
            score, msg = RegistrationQuality.check(frame, face_box)
            
            if score > 0:
                oval_color = (0, 255, 0) # Green = good
                state["instruction"] = self.POSES[self.pose_idx][0]
                state["quality"] = score
                
                # Auto-capture logic
                now = time.time()
                if now - self.last_capture_time > 0.3: # 300ms between captures
                    self._save_frame(frame, face_box)
                    self.last_capture_time = now
                    oval_color = (255, 255, 0) # Cyan flash on capture
            else:
                oval_color = (0, 165, 255) # Orange = face found, poor quality
                state["instruction"] = msg
                
            # Draw face box lightly
            fx, fy, fw, fh = face_box
            cv2.rectangle(display, (fx, fy), (fx+fw, fy+fh), oval_color, 1)

        cv2.ellipse(display, (center_x, center_y), (oval_w, oval_h), 0, 0, 360, oval_color, 2)
        
        return state, display

    def _save_frame(self, frame, face_box):
        x, y, fw, fh = face_box
        pad = int(max(fw, fh) * 0.2)
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(frame.shape[1], x + fw + pad), min(frame.shape[0], y + fh + pad)
        
        img_path = self.student_dir / f"{self.total_saved + 1:03d}.jpg"
        cv2.imwrite(str(img_path), frame[y1:y2, x1:x2])
        
        self.frames_saved_current_pose += 1
        self.total_saved += 1
        
        pose_target = self.POSES[self.pose_idx][1]
        if self.frames_saved_current_pose >= pose_target:
            self.pose_idx += 1
            self.frames_saved_current_pose = 0
            if self.pose_idx >= len(self.POSES):
                self.is_complete = True


def register_student(
    reg_number: str,
    name: str,
    email: str = "",
    class_name: str = "",
    capture: bool = True,
) -> Student | None:
    
    logger.info(f"Starting registration: {reg_number} — {name}")

    with db_session() as session:
        existing = session.query(Student).filter_by(reg_number=reg_number).first()
        if existing:
            print(f"\n  Student {reg_number} already exists in the database.")
            return existing

    dataset_path = str(DATASET_DIR / reg_number)
    
    if capture:
        session_obj = RegistrationSession(reg_number, name)
        with Camera() as cam:
            cv2.namedWindow("Eikon Registration", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Eikon Registration", 800, 600)
            
            while not session_obj.is_complete:
                frame = cam.read()
                if frame is None: continue
                
                state, display = session_obj.process_frame(frame)
                
                # CLI Overlay
                h, w = display.shape[:2]
                cv2.rectangle(display, (0, h-60), (w, h), (0,0,0), -1)
                cv2.putText(display, f"Instruction: {state['instruction']}", (20, h-35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
                cv2.putText(display, f"Progress: {int(state['progress']*100)}%", (20, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 1)
                
                cv2.imshow("Eikon Registration", display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n  Registration cancelled by user.")
                    break
            
            cv2.destroyAllWindows()
            
        if not session_obj.is_complete:
            return None

    with db_session() as session:
        student = Student(
            reg_number   = reg_number,
            name         = name,
            email        = email or None,
            class_name   = class_name or None,
            dataset_path = dataset_path,
            is_encoded   = False,
        )
        session.add(student)
        session.flush()
        student_id = student.id

    print(f"\n  Registration complete for {name}!")
    
    with db_session() as session:
        return session.query(Student).get(student_id)


def _cli():
    print("\n=== Eikon — Student Registration ===\n")
    reg_number = input("  Registration number: ").strip()
    name       = input("  Full name: ").strip()
    
    if not reg_number or not name:
        sys.exit(1)
        
    register_student(reg_number=reg_number, name=name)


if __name__ == "__main__":
    _cli()
