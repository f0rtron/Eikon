"""
app/routes/demo.py — Demo data management for presentations

Provides:
  POST /api/demo/seed   → insert 50 sample students + 14 days of attendance
  POST /api/demo/clear  → remove all demo data (tagged with 'DEMO-' prefix)
  GET  /api/demo/status → check if demo data exists
  GET  /api/demo/stats  → full dashboard stats (NO AUTH required) for Flutter demo mode

Demo students use reg numbers prefixed with "DEMO-" so they can be
cleanly identified and removed without affecting real data.
"""

import random
import logging
from datetime import date, datetime, timedelta, time
from flask import Blueprint, jsonify
from db.connection import db_session
from db.models import Student, Subject, Attendance, User

logger = logging.getLogger(__name__)
demo_bp = Blueprint("demo", __name__)

# ── Sample data — 50 students, 4 classes, 5 attendance profiles ──────────────

DEMO_STUDENTS = [
    # (reg, name, email, class, profile)
    # "regular"=95%, "good"=82%, "average"=68%, "irregular"=50%, "chronic"=25%
    ("DEMO-001", "Ahmed Khan",        "ahmed@eikon.demo",    "BSCS-8A", "regular"),
    ("DEMO-002", "Sara Malik",        "sara@eikon.demo",     "BSCS-8A", "regular"),
    ("DEMO-003", "Muhammad Ali",      "mali@eikon.demo",     "BSCS-8A", "good"),
    ("DEMO-004", "Fatima Zahra",      "fatima@eikon.demo",   "BSCS-8B", "regular"),
    ("DEMO-005", "Usman Tariq",       "usman@eikon.demo",    "BSCS-8B", "average"),
    ("DEMO-006", "Ayesha Siddiqui",   "ayesha@eikon.demo",   "BSCS-8A", "good"),
    ("DEMO-007", "Hassan Raza",       "hassan@eikon.demo",   "BSCS-8B", "irregular"),
    ("DEMO-008", "Zainab Noor",       "zainab@eikon.demo",   "BSCS-8A", "regular"),
    ("DEMO-009", "Bilal Ahmed",       "bilal@eikon.demo",    "BSCS-8B", "chronic"),
    ("DEMO-010", "Madiha Iqbal",      "madiha@eikon.demo",   "BSCS-8A", "good"),
    ("DEMO-011", "Faisal Nawaz",      "faisal@eikon.demo",   "BSCS-8B", "average"),
    ("DEMO-012", "Hira Batool",       "hira@eikon.demo",     "BSCS-8A", "regular"),
    ("DEMO-013", "Kamran Shah",       "kamran@eikon.demo",   "BSCS-8B", "irregular"),
    ("DEMO-014", "Nadia Pervez",      "nadia@eikon.demo",    "BSCS-8C", "good"),
    ("DEMO-015", "Owais Siddiq",      "owais@eikon.demo",    "BSCS-8C", "average"),
    ("DEMO-016", "Rabia Aslam",       "rabia@eikon.demo",    "BSCS-8C", "regular"),
    ("DEMO-017", "Saad Ullah",        "saad@eikon.demo",     "BSCS-8C", "chronic"),
    ("DEMO-018", "Tania Karim",       "tania@eikon.demo",    "BSCS-8A", "good"),
    ("DEMO-019", "Waqar Hussain",     "waqar@eikon.demo",    "BSCS-8B", "irregular"),
    ("DEMO-020", "Yasmin Fateh",      "yasmin@eikon.demo",   "BSCS-8A", "regular"),
    ("DEMO-021", "Zain Ul Abideen",   "zain@eikon.demo",     "BSCS-8C", "good"),
    ("DEMO-022", "Amna Riaz",         "amna@eikon.demo",     "BSCS-8A", "average"),
    ("DEMO-023", "Hamza Mehmood",     "hamza@eikon.demo",    "BSCS-8B", "regular"),
    ("DEMO-024", "Iqra Shaheen",      "iqra@eikon.demo",     "BSCS-8C", "good"),
    ("DEMO-025", "Junaid Akhtar",     "junaid@eikon.demo",   "BSCS-8D", "chronic"),
    ("DEMO-026", "Kiran Asghar",      "kiran@eikon.demo",    "BSCS-8D", "regular"),
    ("DEMO-027", "Luqman Haider",     "luqman@eikon.demo",   "BSCS-8D", "average"),
    ("DEMO-028", "Maryam Bibi",       "maryam@eikon.demo",   "BSCS-8A", "good"),
    ("DEMO-029", "Nabeel Qureshi",    "nabeel@eikon.demo",   "BSCS-8B", "irregular"),
    ("DEMO-030", "Omair Farooq",      "omair@eikon.demo",    "BSCS-8C", "regular"),
    ("DEMO-031", "Palwasha Gul",      "palwasha@eikon.demo", "BSCS-8D", "good"),
    ("DEMO-032", "Qasim Abbas",       "qasim@eikon.demo",    "BSCS-8A", "chronic"),
    ("DEMO-033", "Rimsha Kanwal",     "rimsha@eikon.demo",   "BSCS-8B", "regular"),
    ("DEMO-034", "Shahid Mehmood",    "shahid@eikon.demo",   "BSCS-8C", "average"),
    ("DEMO-035", "Tayyaba Naz",       "tayyaba@eikon.demo",  "BSCS-8D", "good"),
    ("DEMO-036", "Umer Farooq",       "umer@eikon.demo",     "BSCS-8A", "irregular"),
    ("DEMO-037", "Varda Asif",        "varda@eikon.demo",    "BSCS-8B", "regular"),
    ("DEMO-038", "Waseem Asghar",     "waseem@eikon.demo",   "BSCS-8C", "average"),
    ("DEMO-039", "Xenia Bukhari",     "xenia@eikon.demo",    "BSCS-8D", "good"),
    ("DEMO-040", "Yousaf Rind",       "yousaf@eikon.demo",   "BSCS-8A", "chronic"),
    ("DEMO-041", "Zoha Imran",        "zoha@eikon.demo",     "BSCS-8B", "regular"),
    ("DEMO-042", "Adeel Safdar",      "adeel@eikon.demo",    "BSCS-8C", "good"),
    ("DEMO-043", "Bushra Tahir",      "bushra@eikon.demo",   "BSCS-8D", "average"),
    ("DEMO-044", "Danish Latif",      "danish@eikon.demo",   "BSCS-8A", "irregular"),
    ("DEMO-045", "Eisha Noman",       "eisha@eikon.demo",    "BSCS-8B", "regular"),
    ("DEMO-046", "Farhan Javed",      "farhan@eikon.demo",   "BSCS-8C", "good"),
    ("DEMO-047", "Ghazala Parveen",   "ghazala@eikon.demo",  "BSCS-8D", "chronic"),
    ("DEMO-048", "Haroon Rashid",     "haroon@eikon.demo",   "BSCS-8A", "regular"),
    ("DEMO-049", "Irfan Sadiq",       "irfan@eikon.demo",    "BSCS-8B", "average"),
    ("DEMO-050", "Javeria Mumtaz",    "javeria@eikon.demo",  "BSCS-8C", "good"),
]

# Per-profile attendance probability: how likely each day's outcome is
PROFILE_PROBS = {
    #                present   late    absent (must sum to 1.0)
    "regular":   {"present": 0.82, "late": 0.13, "absent": 0.05},
    "good":      {"present": 0.68, "late": 0.14, "absent": 0.18},
    "average":   {"present": 0.50, "late": 0.18, "absent": 0.32},
    "irregular": {"present": 0.30, "late": 0.20, "absent": 0.50},
    "chronic":   {"present": 0.10, "late": 0.15, "absent": 0.75},
}

# Per-profile confidence ranges
PROFILE_CONFIDENCE = {
    "regular":   (0.87, 0.98),
    "good":      (0.80, 0.95),
    "average":   (0.72, 0.90),
    "irregular": (0.65, 0.85),
    "chronic":   (0.55, 0.78),
}

DEMO_SUBJECTS = [
    ("DEMO-CS101", "Introduction to AI",     "08:00", "09:30"),
    ("DEMO-CS201", "Data Structures",         "10:00", "11:30"),
    ("DEMO-CS301", "Database Systems",        "13:00", "14:30"),
]


def _ensure_demo_subjects(session):
    """Get or create all demo subjects."""
    subjects = []
    for code, name, start, end in DEMO_SUBJECTS:
        subj = session.query(Subject).filter_by(code=code).first()
        if not subj:
            h1, m1 = map(int, start.split(":"))
            h2, m2 = map(int, end.split(":"))
            subj = Subject(
                name=name, code=code,
                class_start_time=time(h1, m1),
                class_end_time=time(h2, m2),
            )
            session.add(subj)
            session.flush()
        subjects.append(subj)
    return subjects


def _seed_demo_data(session):
    """Insert 50 demo students with 14 days of diverse attendance across 3 subjects."""
    subjects = _ensure_demo_subjects(session)

    # Insert students
    student_data = []  # list of (db_id, profile)
    for reg, name, email, cls, profile in DEMO_STUDENTS:
        existing = session.query(Student).filter_by(reg_number=reg).first()
        if existing:
            student_data.append((existing.id, profile))
            continue

        s = Student(
            reg_number=reg, name=name, email=email,
            class_name=cls, is_encoded=True, is_active=True,
            needs_reregistration=(profile == "chronic"),
        )
        session.add(s)
        session.flush()
        student_data.append((s.id, profile))

    # Generate 14 days of attendance
    today = date.today()
    rng = random.Random(42)  # isolated RNG — reproducible

    for day_offset in range(13, -1, -1):
        d = today - timedelta(days=day_offset)

        # Skip weekends
        if d.weekday() >= 5:
            continue

        for idx, (sid, profile) in enumerate(student_data):
            probs = PROFILE_PROBS[profile]
            conf_lo, conf_hi = PROFILE_CONFIDENCE[profile]

            # Each student rolls independently per day
            roll = rng.random()

            if roll < probs["absent"]:
                continue  # absent today

            is_late = roll < (probs["absent"] + probs["late"])
            status = "late" if is_late else "present"

            # Assign 1-2 subjects per day (more diversity)
            k = 2 if rng.random() < 0.6 else 1
            day_subjects = rng.sample(subjects, k=min(k, len(subjects)))

            for subj in day_subjects:
                # Skip if already exists
                existing = session.query(Attendance).filter_by(
                    student_id=sid, subject_id=subj.id, marked_date=d
                ).first()
                if existing:
                    continue

                conf = round(rng.uniform(conf_lo, conf_hi), 4)

                base_hour = subj.class_start_time.hour if subj.class_start_time else 8
                if status == "present":
                    minute = rng.randint(0, 20)
                else:
                    minute = rng.randint(30, 55)

                marked_at = datetime.combine(d, time(base_hour, minute, rng.randint(0, 59)))

                session.add(Attendance(
                    student_id=sid, subject_id=subj.id,
                    marked_date=d, marked_at=marked_at,
                    confidence=conf, status=status,
                ))

    session.flush()
    return len(student_data)


def _clear_demo_data(session):
    """Remove all DEMO- prefixed students and their attendance."""
    demo_students = session.query(Student).filter(
        Student.reg_number.like("DEMO-%")
    ).all()

    count = len(demo_students)
    for s in demo_students:
        session.query(Attendance).filter_by(student_id=s.id).delete()
        session.delete(s)

    # Remove demo subjects
    for code, _, _, _ in DEMO_SUBJECTS:
        session.query(Subject).filter_by(code=code).delete()
    return count


# ── Routes ────────────────────────────────────────────────────────────────────

@demo_bp.route("/demo/seed", methods=["POST"])
def seed():
    """Seed sample demo data for presentation purposes."""
    try:
        with db_session() as session:
            count = _seed_demo_data(session)
        logger.info(f"Demo data seeded: {count} students")
        return jsonify({"success": True, "message": f"Seeded {count} demo students with 14 days of attendance across 3 subjects"})
    except Exception as e:
        logger.error(f"Demo seed failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@demo_bp.route("/demo/clear", methods=["POST"])
def clear():
    """Remove all demo data."""
    try:
        with db_session() as session:
            count = _clear_demo_data(session)
        logger.info(f"Demo data cleared: {count} students removed")
        return jsonify({"success": True, "message": f"Removed {count} demo students and all related data"})
    except Exception as e:
        logger.error(f"Demo clear failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@demo_bp.route("/demo/status")
def status():
    """Check if demo data exists."""
    with db_session() as session:
        count = session.query(Student).filter(
            Student.reg_number.like("DEMO-%")
        ).count()
    return jsonify({"exists": count > 0, "count": count})


@demo_bp.route("/demo/stats")
def demo_stats():
    """
    Full dashboard stats — NO AUTH required.
    For Flutter demo mode: returns same format as /api/dashboard/stats.
    """
    from sqlalchemy import func

    today = date.today()

    with db_session() as session:
        total_students = session.query(Student).filter_by(is_active=True).count()

        present_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date == today, Attendance.status == "present")\
            .scalar() or 0

        late_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date == today, Attendance.status == "late")\
            .scalar() or 0

        absent_today = total_students - present_today - late_today
        attendance_pct = round((present_today + late_today) / total_students * 100) if total_students else 0

        # Weekly data
        weekly_labels, weekly_present, weekly_late = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            p = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date == d, Attendance.status == "present").scalar() or 0
            l = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date == d, Attendance.status == "late").scalar() or 0
            weekly_labels.append(d.strftime("%a %d"))
            weekly_present.append(p)
            weekly_late.append(l)

        # Recent
        recent = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id == Student.id)
            .join(Subject, Attendance.subject_id == Subject.id)
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


# ── No-auth endpoints for Flutter demo: attendance, students, reports ─────────

@demo_bp.route("/demo/attendance")
def demo_attendance():
    """Attendance data — same format as /api/attendance/data, no auth."""
    from sqlalchemy import func

    today = date.today()
    with db_session() as session:
        records = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id == Student.id)
            .join(Subject, Attendance.subject_id == Subject.id)
            .filter(Attendance.marked_date == today)
            .order_by(Attendance.marked_at).all()
        )
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


@demo_bp.route("/demo/students")
def demo_students():
    """Students list — same format as /api/students/all, no auth."""
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


@demo_bp.route("/demo/reports")
def demo_reports():
    """Reports — same format as /api/reports/flutter, no auth."""
    from sqlalchemy import func

    with db_session() as session:
        total_days = session.query(func.count(func.distinct(Attendance.marked_date))).scalar() or 1
        students = session.query(Student).filter_by(is_active=True).all()
        summary = []
        for s in students:
            attended = session.query(func.count(Attendance.id)).filter_by(student_id=s.id).scalar() or 0
            pct = round(attended / total_days * 100)
            summary.append({
                "name": s.name, "reg": s.reg_number, "class_name": s.class_name,
                "attended": attended, "total": total_days,
                "pct": pct, "defaulter": pct < 75,
            })
        summary.sort(key=lambda x: x["pct"])
        return jsonify({"total_days": total_days, "summary": summary})


@demo_bp.route("/demo/subjects")
def demo_subjects():
    """Subjects list — no auth."""
    with db_session() as session:
        subs = session.query(Subject).filter_by(is_active=True).all()
        return jsonify([{"id": s.id, "name": s.name, "code": s.code} for s in subs])
