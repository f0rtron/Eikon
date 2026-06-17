"""
app/routes/api.py — JSON API endpoints
Used by the kiosk terminal and recognition engine to mark attendance
and fetch live data without page reloads.
"""

import logging
from datetime import date, datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required

from db.connection import db_session
from db.models import Attendance, Student, Subject

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    """Health check — used by kiosk to verify server is reachable."""
    from db.connection import test_connection
    db_ok = test_connection()
    return jsonify({"status": "ok" if db_ok else "db_error", "db": db_ok})


@api_bp.route("/mark", methods=["POST"])
def mark_attendance():
    """
    Mark attendance from the kiosk terminal.
    Called by recognize.py / kiosk.py after a successful recognition.

    POST JSON:
        {
            "reg_number":  "L1F22BSCS001",
            "subject_id":  1,
            "confidence":  0.82
        }

    Returns:
        {
            "success": true,
            "message": "Marked Present",
            "student_name": "Fahad Gujjar"
        }
    """
    data       = request.get_json(silent=True) or {}
    reg_number = data.get("reg_number", "").strip()
    subject_id = data.get("subject_id")
    confidence = float(data.get("confidence", 0.0))

    if not reg_number or not subject_id:
        return jsonify({"success": False, "message": "Missing reg_number or subject_id"}), 400

    today = date.today()

    with db_session() as session:
        student = session.query(Student).filter_by(
            reg_number=reg_number, is_active=True
        ).first()

        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404

        # check duplicate
        existing = session.query(Attendance).filter_by(
            student_id  = student.id,
            subject_id  = int(subject_id),
            marked_date = today,
        ).first()

        if existing:
            return jsonify({
                "success":      False,
                "message":      "Already marked today",
                "student_name": student.name,
                "duplicate":    True,
            })

        record = Attendance(
            student_id  = student.id,
            subject_id  = int(subject_id),
            marked_date = today,
            confidence  = round(confidence, 4),
            status      = "present",
        )
        session.add(record)
        name = student.name
        logger.info(f"API mark: {reg_number} — {name} (conf={confidence:.3f})")

    return jsonify({
        "success":      True,
        "message":      "Marked Present",
        "student_name": name,
    })


@api_bp.route("/attendance_event", methods=["POST"])
def attendance_event():
    """
    Receives attendance events and broadcasts them in real-time via WebSockets.
    """
    data       = request.get_json(silent=True) or {}
    reg_number = data.get("reg_number")
    name       = data.get("name")
    subject_id = data.get("subject_id")
    confidence = data.get("confidence", 0.0)
    status     = data.get("status", "present")
    photo_path = data.get("photo_path", "")

    # Resolve subject code
    subject_code = "—"
    if subject_id:
        try:
            with db_session() as session:
                sub = session.get(Subject, int(subject_id))
                if sub:
                    subject_code = sub.code
        except Exception:
            pass

    # Emit the real-time event via socketio
    from app import socketio
    socketio.emit("attendance_marked", {
        "reg_number": reg_number,
        "name":       name,
        "subject":    subject_code,
        "time":       datetime.now().strftime("%H:%M:%S"),
        "confidence": f"{float(confidence):.2f}",
        "status":     status,
        "photo_path": photo_path
    })

    return jsonify({"success": True})


@api_bp.route("/today")
def today_stats():
    """Return today's attendance counts — used by kiosk display."""
    today = date.today()
    with db_session() as session:
        from sqlalchemy import func
        present = session.query(
            func.count(func.distinct(Attendance.student_id))
        ).filter(Attendance.marked_date == today).scalar() or 0

        total = session.query(Student).filter_by(is_active=True).count()

    return jsonify({
        "date":    today.isoformat(),
        "present": present,
        "total":   total,
        "absent":  total - present,
    })


@api_bp.route("/subjects")
def subjects():
    """Return active subjects list."""
    with db_session() as session:
        subs = session.query(Subject).filter_by(is_active=True).all()
        return jsonify([
            {"id": s.id, "name": s.name, "code": s.code}
            for s in subs
        ])


@api_bp.route("/students/recent")
def recent_marked():
    """Return last 5 students marked present today — for kiosk ticker."""
    today = date.today()
    with db_session() as session:
        rows = (
            session.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .filter(Attendance.marked_date == today)
            .order_by(Attendance.marked_at.desc())
            .limit(5)
            .all()
        )
        return jsonify([
            {
                "name":       s.name,
                "reg":        s.reg_number,
                "time":       a.marked_at.strftime("%H:%M"),
                "confidence": f"{a.confidence:.2f}",
            }
            for a, s in rows
        ])


# ─── Live camera stream ───────────────────────────────────────────────────────

def _generate_stream():
    """
    MJPEG generator — reads shared frame from recognition engine.
    Dashboard embeds this as <img src="/api/camera/stream">.
    Recognition engine must be running for frames to appear.
    """
    import cv2
    from core.recognize import get_shared_frame
    import time

    blank = None   # shown when no frame available yet

    while True:
        frame = get_shared_frame()

        if frame is None:
            # send a placeholder black frame
            if blank is None:
                import numpy as np
                blank = np.zeros((480, 640, 3), dtype="uint8")
                cv2.putText(blank, "Recognition engine not running",
                            (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100,100,100), 2)
            frame = blank

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg.tobytes()
            + b"\r\n"
        )
        time.sleep(0.05)   # ~20 FPS stream


@api_bp.route("/camera/stream")
def camera_stream():
    """Live MJPEG stream from recognition camera."""
    from flask import Response
    return Response(
        _generate_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ─── Student confidence history ───────────────────────────────────────────────

@api_bp.route("/students/<int:student_id>/confidence")
@login_required
def student_confidence(student_id):
    """Return confidence history for Chart.js line graph."""
    from db.models import Student
    with db_session() as session:
        student = session.get(Student, student_id)
        if not student:
            return jsonify({"error": "Not found"}), 404

        records = (
            session.query(Attendance.marked_date, Attendance.confidence)
            .filter_by(student_id=student_id)
            .filter(Attendance.status.in_(["present","late"]))
            .order_by(Attendance.marked_date)
            .all()
        )
        from config import REREG_CONFIDENCE_THRESHOLD
        return jsonify({
            "name":      student.name,
            "threshold": REREG_CONFIDENCE_THRESHOLD,
            "needs_reregistration": student.needs_reregistration,
            "history": [
                {"date": r.marked_date.isoformat(), "confidence": round(r.confidence, 3)}
                for r in records
            ]
        })


# ══════════════════════════════════════════════════════════════════════════════
# Flutter-specific endpoints
# ══════════════════════════════════════════════════════════════════════════════

# ─── Auth ─────────────────────────────────────────────────────────────────────

@api_bp.route("/auth/login", methods=["POST"])
def flutter_login():
    """JWT-free login — uses Flask session, returns user info."""
    from flask import session
    from app.routes.auth import check_password
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "message": "Missing credentials"}), 400

    with db_session() as db:
        from db.models import User
        user = db.query(User).filter_by(username=username, is_active=True).first()
        if not user or not check_password(password, user.password_hash):
            return jsonify({"success": False, "message": "Invalid credentials"}), 401

        from flask_login import login_user
        login_user(user, remember=True)
        return jsonify({
            "success":  True,
            "id":       user.id,
            "username": user.username,
            "role":     user.role,
        })


@api_bp.route("/auth/logout", methods=["POST"])
def flutter_logout():
    from flask_login import logout_user
    logout_user()
    return jsonify({"success": True})


@api_bp.route("/auth/me")
@login_required
def flutter_me():
    from flask_login import current_user
    return jsonify({
        "id":       current_user.id,
        "username": current_user.username,
        "role":     current_user.role,
    })


# ─── Dashboard stats (Flutter format) ─────────────────────────────────────────

@api_bp.route("/dashboard/stats")
@login_required
def flutter_dashboard_stats():
    """All dashboard data in one call for Flutter."""
    from datetime import date, timedelta
    from sqlalchemy import func
    from db.models import Student, Subject, Attendance

    today = date.today()

    with db_session() as session:
        total_students = session.query(Student).filter_by(is_active=True).count()

        present_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date==today, Attendance.status=="present")\
            .scalar() or 0

        late_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date==today, Attendance.status=="late")\
            .scalar() or 0

        absent_today   = total_students - present_today - late_today
        attendance_pct = round((present_today+late_today)/total_students*100) if total_students else 0

        # weekly
        weekly_labels, weekly_present, weekly_late = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            p = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date==d, Attendance.status=="present").scalar() or 0
            l = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date==d, Attendance.status=="late").scalar() or 0
            weekly_labels.append(d.strftime("%a %d"))
            weekly_present.append(p)
            weekly_late.append(l)

        # recent
        recent = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id==Student.id)
            .join(Subject, Attendance.subject_id==Subject.id)
            .order_by(Attendance.marked_at.desc()).limit(10).all()
        )
        recent_list = [{
            "name": s.name, "reg": s.reg_number, "subject": sub.code,
            "time": a.marked_at.strftime("%H:%M:%S"),
            "confidence": f"{a.confidence:.2f}",
            "status": a.status,
            "photo_path": a.photo_path or "",
        } for a, s, sub in recent]

        total_days = session.query(func.count(func.distinct(Attendance.marked_date))).scalar() or 1
        defaulters = sum(1 for st in session.query(Student).filter_by(is_active=True).all()
            if (session.query(func.count(Attendance.id)).filter_by(student_id=st.id).scalar() or 0)
               / total_days * 100 < 75)

    return jsonify({
        "total_students":   total_students,
        "present_today":    present_today,
        "late_today":       late_today,
        "absent_today":     absent_today,
        "attendance_pct":   attendance_pct,
        "defaulters_count": defaulters,
        "today":            today.strftime("%A, %d %B %Y"),
        "weekly_labels":    weekly_labels,
        "weekly_present":   weekly_present,
        "weekly_late":      weekly_late,
        "recent_list":      recent_list,
    })


# ─── Attendance data (Flutter) ─────────────────────────────────────────────────

@api_bp.route("/attendance/data")
@login_required
def flutter_attendance_data():
    from datetime import datetime, date
    from db.models import Attendance, Student, Subject

    filter_date = request.args.get("date", date.today().isoformat())
    filter_subj = request.args.get("subject_id", "all")

    try:
        sel_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
    except ValueError:
        sel_date = date.today()

    with db_session() as session:
        query = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id==Student.id)
            .join(Subject, Attendance.subject_id==Subject.id)
            .filter(Attendance.marked_date==sel_date)
        )
        if filter_subj != "all":
            query = query.filter(Attendance.subject_id==int(filter_subj))

        records = query.order_by(Attendance.marked_at).all()
        present_ids = {a.student_id for a, s, sub in records}
        all_students = session.query(Student).filter_by(is_active=True).all()

        return jsonify({
            "records": [{
                "id": a.id, "name": s.name, "reg": s.reg_number,
                "subject": sub.name, "subject_code": sub.code,
                "time": a.marked_at.strftime("%H:%M:%S"),
                "confidence": f"{a.confidence:.2f}", "status": a.status,
            } for a, s, sub in records],
            "absent": [{"name": s.name, "reg": s.reg_number}
                       for s in all_students if s.id not in present_ids],
        })


# ─── Students (Flutter) ────────────────────────────────────────────────────────

@api_bp.route("/students/all")
@login_required
def flutter_students_all():
    from db.models import Student, Attendance
    from sqlalchemy import func

    with db_session() as session:
        students = session.query(Student).filter_by(is_active=True).order_by(Student.name).all()
        result = []
        for s in students:
            count = session.query(func.count(Attendance.id)).filter_by(student_id=s.id).scalar() or 0
            result.append({
                "id": s.id, "reg_number": s.reg_number, "name": s.name,
                "email": s.email, "class_name": s.class_name,
                "is_encoded": s.is_encoded,
                "needs_reregistration": s.needs_reregistration,
                "attendance": count,
                "created_at": s.created_at.strftime("%d %b %Y"),
            })
        return jsonify(result)


@api_bp.route("/students/add", methods=["POST"])
@login_required
def flutter_add_student():
    from db.models import Student
    data = request.get_json(silent=True) or {}
    reg  = data.get("reg_number", "").strip()
    name = data.get("name", "").strip()
    if not reg or not name:
        return jsonify({"success": False, "message": "reg_number and name required"}), 400

    with db_session() as session:
        if session.query(Student).filter_by(reg_number=reg).first():
            return jsonify({"success": False, "message": f"{reg} already exists"}), 409
        session.add(Student(
            reg_number=reg, name=name,
            email=data.get("email") or None,
            class_name=data.get("class_name") or None,
        ))
    return jsonify({"success": True, "message": f"{name} added"})


@api_bp.route("/students/<int:student_id>/deactivate", methods=["POST"])
@login_required
def flutter_deactivate_student(student_id):
    from db.models import Student
    with db_session() as session:
        student = session.get(Student, student_id)
        if not student:
            return jsonify({"success": False, "message": "Not found"}), 404
        student.is_active = False
    return jsonify({"success": True})


# ─── Reports (Flutter) ─────────────────────────────────────────────────────────

@api_bp.route("/reports/flutter")
@login_required
def flutter_reports():
    from db.models import Student, Attendance
    from sqlalchemy import func

    with db_session() as session:
        total_days = session.query(func.count(func.distinct(Attendance.marked_date))).scalar() or 1
        students   = session.query(Student).filter_by(is_active=True).all()
        summary = []
        for s in students:
            attended = session.query(func.count(Attendance.id)).filter_by(student_id=s.id).scalar() or 0
            pct      = round(attended / total_days * 100)
            summary.append({
                "name": s.name, "reg": s.reg_number, "class_name": s.class_name,
                "attended": attended, "total": total_days,
                "pct": pct, "defaulter": pct < 75,
            })
        summary.sort(key=lambda x: x["pct"])
        return jsonify({"total_days": total_days, "summary": summary})
