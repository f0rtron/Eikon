"""
core/recognize.py v2 — Real-time recognition with:
  - Photo capture on attendance mark
  - Late arrival detection
  - Shared frame buffer for live dashboard stream
  - Face re-registration alert check
"""

import cv2
import time
import logging
import threading
import argparse
import sys
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    RECOGNITION_THRESHOLD, DUPLICATE_WINDOW_SECS,
    PHOTOS_DIR, LATE_GRACE_MINUTES,
    REREG_CONFIDENCE_THRESHOLD, REREG_CHECK_LAST_N
)
from core.face_engine import get_all_faces, cosine_similarity
from core.train import load_encodings
from core.anti_spoof import get_spoof_checker
from db.connection import db_session
from db.models import Attendance, Student, Subject
from utils.camera import Camera

logger = logging.getLogger(__name__)

# ─── Shared frame buffer for dashboard live stream ────────────────────────────
_shared_frame = None
_frame_lock   = threading.Lock()

def get_shared_frame():
    with _frame_lock:
        return _shared_frame.copy() if _shared_frame is not None else None

def _set_shared_frame(frame):
    global _shared_frame
    with _frame_lock:
        _shared_frame = frame.copy()


# ─── FaceResult ───────────────────────────────────────────────────────────────

class FaceResult:
    __slots__ = ["bbox","name","reg_number","confidence","is_live","spoof_score","status","marked"]
    def __init__(self, bbox, name, reg_number, confidence, is_live, spoof_score, status, marked=False):
        self.bbox=bbox; self.name=name; self.reg_number=reg_number
        self.confidence=confidence; self.is_live=is_live; self.spoof_score=spoof_score
        self.status=status; self.marked=marked


# ─── Photo capture ────────────────────────────────────────────────────────────

def save_face_photo(frame, bbox, reg_number):
    try:
        x1,y1,x2,y2 = bbox
        pad=20
        x1=max(0,x1-pad); y1=max(0,y1-pad)
        x2=min(frame.shape[1],x2+pad); y2=min(frame.shape[0],y2+pad)
        crop = frame[y1:y2, x1:x2]
        today_dir = PHOTOS_DIR / date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)
        filename  = f"{reg_number}_{datetime.now().strftime('%H%M%S')}.jpg"
        cv2.imwrite(str(today_dir/filename), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return f"photos/{date.today().isoformat()}/{filename}"
    except Exception as e:
        logger.error(f"Photo save failed: {e}")
        return None


# ─── Re-registration check ────────────────────────────────────────────────────

def check_reregistration(student_id, session):
    recent = (
        session.query(Attendance.confidence)
        .filter_by(student_id=student_id)
        .filter(Attendance.status.in_(["present","late"]))
        .order_by(Attendance.marked_at.desc())
        .limit(REREG_CHECK_LAST_N).all()
    )
    if len(recent) < REREG_CHECK_LAST_N:
        return False
    avg = sum(r.confidence for r in recent) / len(recent)
    return avg < REREG_CONFIDENCE_THRESHOLD


# ─── Late arrival detection ───────────────────────────────────────────────────

def determine_status(subject_id, session):
    subject = session.get(Subject, subject_id)
    if not subject or not subject.class_start_time:
        return "present"
    now       = datetime.now().time()
    grace_end = (datetime.combine(date.today(), subject.class_start_time)
                 + timedelta(minutes=LATE_GRACE_MINUTES)).time()
    return "late" if now > grace_end else "present"


# ─── Attendance marker ────────────────────────────────────────────────────────

class AttendanceMarker:
    def __init__(self, subject_id):
        self.subject_id = subject_id
        self._marked_today = {}
        self._lock = threading.Lock()
        self._load_todays_records()

    def _load_todays_records(self):
        with db_session() as session:
            records = session.query(Attendance).filter(
                Attendance.subject_id==self.subject_id,
                Attendance.marked_date==date.today()
            ).all()
            for r in records:
                self._marked_today[r.student_id] = time.time()

    def try_mark(self, reg_number, confidence, frame, bbox):
        with self._lock:
            now = time.time()
            with db_session() as session:
                student = session.query(Student).filter_by(reg_number=reg_number).first()
                if not student:
                    return False, "not_found", "present"
                if student.id in self._marked_today:
                    if now - self._marked_today[student.id] < DUPLICATE_WINDOW_SECS:
                        return False, "duplicate", "present"
                att_status = determine_status(self.subject_id, session)
                photo_path = save_face_photo(frame, bbox, reg_number)
                try:
                    record = Attendance(
                        student_id=student.id, subject_id=self.subject_id,
                        marked_date=date.today(), confidence=round(confidence,4),
                        status=att_status, photo_path=photo_path,
                    )
                    session.add(record)
                    session.flush()
                    if check_reregistration(student.id, session):
                        student.needs_reregistration = True
                    self._marked_today[student.id] = now
                    logger.info(f"Marked {att_status}: {student.name} conf={confidence:.3f}")
                    return True, "marked", att_status
                except Exception as e:
                    logger.warning(f"Duplicate for {reg_number}: {e}")
                    self._marked_today[student.id] = now
                    return False, "duplicate", "present"


# ─── Recognition Engine ───────────────────────────────────────────────────────

class RecognitionEngine:
    def __init__(self, subject_id):
        self.subject_id = subject_id
        self.encodings  = load_encodings()
        self.marker     = AttendanceMarker(subject_id)
        self.spoof      = get_spoof_checker()
        logger.info(f"RecognitionEngine ready — {len(self.encodings)} students.")

    def process_frame(self, frame):
        _set_shared_frame(frame)
        faces = get_all_faces(frame)
        return [r for r in (self._process_one(frame,f) for f in faces) if r]

    def _process_one(self, frame, face):
        x1,y1,x2,y2 = (int(v) for v in face.bbox)
        bbox=(x1,y1,x2,y2)
        crop = frame[max(0,y1):y2, max(0,x1):x2]
        is_live, spoof_score = self.spoof.check(crop)

        if not is_live:
            return FaceResult(bbox=bbox,name="SPOOF",reg_number=None,confidence=0.0,
                              is_live=False,spoof_score=spoof_score,status="spoof")
        if not self.encodings:
            return FaceResult(bbox=bbox,name="No encodings",reg_number=None,confidence=0.0,
                              is_live=True,spoof_score=spoof_score,status="unknown")

        best_score,best_reg = -1.0,None
        for reg,data in self.encodings.items():
            score = cosine_similarity(face.normed_embedding, data["embedding"])
            if score > best_score:
                best_score,best_reg = score,reg

        if best_score < RECOGNITION_THRESHOLD:
            return FaceResult(bbox=bbox,name="Unknown",reg_number=None,confidence=best_score,
                              is_live=True,spoof_score=spoof_score,status="unknown")

        student_name = self.encodings[best_reg]["name"]
        success,reason,att_status = self.marker.try_mark(best_reg,best_score,frame,bbox)
        return FaceResult(bbox=bbox,name=student_name,reg_number=best_reg,
                          confidence=best_score,is_live=True,spoof_score=spoof_score,
                          status=att_status if success else reason,marked=success)

    def reload_encodings(self):
        self.encodings = load_encodings()


# ─── Overlay ──────────────────────────────────────────────────────────────────

_COLOURS = {
    "present":   (0,210,0),
    "late":      (0,165,255),
    "duplicate": (0,180,255),
    "unknown":   (0,0,220),
    "spoof":     (0,0,180),
}
_FLASH_DURATION = 2.0
_last_marked = {}

def draw_overlay(frame, results):
    now = time.time()
    for r in results:
        colour = _COLOURS.get(r.status,(200,200,200))
        x1,y1,x2,y2 = r.bbox
        cv2.rectangle(frame,(x1,y1),(x2,y2),colour,2)
        if r.status=="spoof":     label=f"SPOOF ({r.spoof_score:.2f})"
        elif r.status=="unknown": label=f"Unknown ({r.confidence:.2f})"
        elif r.status=="duplicate": label=f"{r.name}  Already Marked"
        elif r.status=="late":    label=f"{r.name}  LATE ({r.confidence:.2f})"
        else:                     label=f"{r.name}  {r.confidence:.2f}"
        label_y = y1-10 if y1>30 else y2+20
        cv2.putText(frame,label,(x1,label_y),cv2.FONT_HERSHEY_SIMPLEX,0.65,colour,2)
        if r.marked: _last_marked[r.reg_number]=now
        if r.reg_number and r.reg_number in _last_marked:
            if now-_last_marked[r.reg_number]<_FLASH_DURATION:
                h=frame.shape[0]
                banner=f"{'⚠ LATE' if r.status=='late' else '✓'}  {r.name}  Marked!"
                cv2.putText(frame,banner,(20,h-30),cv2.FONT_HERSHEY_SIMPLEX,0.9,colour,2)
    cv2.putText(frame,datetime.now().strftime("%H:%M:%S"),
                (frame.shape[1]-100,25),cv2.FONT_HERSHEY_SIMPLEX,0.6,(180,180,180),1)


# ─── Standalone CLI ───────────────────────────────────────────────────────────

def run_recognition_loop(subject_id):
    engine = RecognitionEngine(subject_id=subject_id)
    with Camera(source=0) as cam:
        print("\nRecognition running — press Q to quit.\n")
        cv2.namedWindow("Smart Attendance",cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Smart Attendance",900,650)
        fps_time,fps,frame_n=time.time(),0,0
        while True:
            frame=cam.read()
            if frame is None: continue
            results=engine.process_frame(frame)
            draw_overlay(frame,results)
            frame_n+=1
            if time.time()-fps_time>=1.0:
                fps=frame_n;frame_n=0;fps_time=time.time()
            cv2.putText(frame,f"FPS:{fps}",(10,25),cv2.FONT_HERSHEY_SIMPLEX,0.65,(180,180,180),1)
            cv2.imshow("Smart Attendance",frame)
            if cv2.waitKey(1)&0xFF==ord("q"): break
    cv2.destroyAllWindows()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--subject",type=int,default=1)
    args=parser.parse_args()
    run_recognition_loop(subject_id=args.subject)
