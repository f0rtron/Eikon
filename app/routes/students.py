"""
app/routes/students.py v3 — Student management + detail + heatmap + bulk import
"""

import logging, csv, io
from datetime import date, timedelta, datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, Response)
from flask_login import login_required
from sqlalchemy import func

from db.connection import db_session
from db.models import Student, Attendance
from config import REREG_CONFIDENCE_THRESHOLD, SEMESTER_START, SEMESTER_END

logger      = logging.getLogger(__name__)
students_bp = Blueprint("students", __name__)


def _get_semester_range():
    """
    Return (start_date, end_date) for the current semester.
    Uses SEMESTER_START / SEMESTER_END from .env if set,
    otherwise defaults to a 16-week window ending today.
    """
    today = date.today()
    start = None
    end   = None

    if SEMESTER_START:
        try:
            start = datetime.strptime(SEMESTER_START, "%Y-%m-%d").date()
        except ValueError:
            pass
    if SEMESTER_END:
        try:
            end = datetime.strptime(SEMESTER_END, "%Y-%m-%d").date()
        except ValueError:
            pass

    if not start or not end:
        # Default: 16 weeks ending today
        end   = today
        start = today - timedelta(weeks=16)

    return start, end


def _build_heatmap(student_id, start_date, end_date):
    """
    Build a GitHub-style heatmap data list for a student.
    Returns a list of {date, status, level} dicts for each day
    from start_date to end_date (Mon-Sat only, skipping Sundays).
    """
    # Query all attendance for this student in the range
    with db_session() as session:
        records = (
            session.query(Attendance.marked_date, Attendance.status)
            .filter(
                Attendance.student_id == student_id,
                Attendance.marked_date >= start_date,
                Attendance.marked_date <= end_date,
            )
            .all()
        )

    # Build lookup: date -> status
    date_status = {}
    for r in records:
        # If multiple records on same day, prefer 'present' over 'late'
        existing = date_status.get(r.marked_date)
        if existing != "present":
            date_status[r.marked_date] = r.status

    # Generate grid: align to Monday start
    # Find the Monday on or before start_date
    days_since_monday = start_date.weekday()  # 0=Mon
    grid_start = start_date - timedelta(days=days_since_monday)

    heatmap = []
    current = grid_start
    while current <= end_date:
        dow = current.weekday()
        if dow < 6:  # Mon-Sat only (skip Sunday)
            if current < start_date or current > end_date:
                status = "empty"
                level = 0
            elif current in date_status:
                s = date_status[current]
                if s == "present":
                    level = 4
                    status = "Present"
                elif s == "late":
                    level = 2
                    status = "Late"
                else:
                    level = 1
                    status = s.capitalize()
            elif current <= date.today():
                status = "Absent"
                level = 0
            else:
                status = "Upcoming"
                level = 0

            heatmap.append({
                "date": current.strftime("%d %b %Y"),
                "status": status,
                "level": level,
            })
        current += timedelta(days=1)

    return heatmap


def _heatmap_week_labels(start_date, end_date):
    """Generate week number labels for the heatmap columns."""
    days_since_monday = start_date.weekday()
    grid_start = start_date - timedelta(days=days_since_monday)
    labels = []
    current = grid_start
    week = 1
    while current <= end_date:
        if week % 2 == 1:
            labels.append(f"W{week}")
        else:
            labels.append("")
        current += timedelta(weeks=1)
        week += 1
    return labels


@students_bp.route("/students")
@login_required
def index():
    with db_session() as session:
        students = session.query(Student).filter_by(is_active=True).order_by(Student.name).all()
        students_list = []
        for s in students:
            count = session.query(func.count(Attendance.id)).filter_by(student_id=s.id).scalar() or 0
            students_list.append({
                "id": s.id, "reg_number": s.reg_number, "name": s.name,
                "class_name": s.class_name or "—", "email": s.email or "—",
                "is_encoded": s.is_encoded,
                "needs_reregistration": s.needs_reregistration,
                "attendance": count,
                "created_at": s.created_at.strftime("%d %b %Y"),
            })
    rereg_count = sum(1 for s in students_list if s["needs_reregistration"])
    return render_template("students/index.html", students=students_list, rereg_count=rereg_count)


@students_bp.route("/students/<int:student_id>")
@login_required
def detail(student_id):
    with db_session() as session:
        student = session.get(Student, student_id)
        if not student or not student.is_active:
            flash("Student not found.", "danger")
            return redirect(url_for("students.index"))

        records = (session.query(Attendance).filter_by(student_id=student_id)
                   .order_by(Attendance.marked_date.desc()).limit(30).all())

        conf_history = [
            {"date": r.marked_date.isoformat(), "confidence": round(r.confidence, 3)}
            for r in reversed(records) if r.status in ("present", "late")
        ]
        present_cnt = sum(1 for r in records if r.status == "present")
        late_cnt    = sum(1 for r in records if r.status == "late")
        avg_conf    = round(
            sum(r.confidence for r in records if r.status in ("present","late"))
            / max(present_cnt + late_cnt, 1), 3
        )
        student_data = {
            "id": student.id, "reg_number": student.reg_number,
            "name": student.name, "email": student.email or "—",
            "class_name": student.class_name or "—",
            "is_encoded": student.is_encoded,
            "needs_reregistration": student.needs_reregistration,
            "created_at": student.created_at.strftime("%d %b %Y"),
        }
        records_list = [{
            "date": r.marked_date.isoformat(), "status": r.status,
            "confidence": round(r.confidence, 3), "photo_path": r.photo_path or "",
        } for r in records]

    # Build heatmap data
    sem_start, sem_end = _get_semester_range()
    heatmap_data = _build_heatmap(student_id, sem_start, sem_end)
    heatmap_week_labels = _heatmap_week_labels(sem_start, sem_end)
    heatmap_semester_label = f"{sem_start.strftime('%d %b %Y')} — {sem_end.strftime('%d %b %Y')}"

    return render_template("students/detail.html",
        student=student_data, conf_history=conf_history, records=records_list,
        total_marked=len(records), present_cnt=present_cnt, late_cnt=late_cnt,
        avg_conf=avg_conf, rereg_threshold=REREG_CONFIDENCE_THRESHOLD,
        heatmap_data=heatmap_data,
        heatmap_week_labels=heatmap_week_labels,
        heatmap_semester_label=heatmap_semester_label)


@students_bp.route("/students/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        reg_number = request.form.get("reg_number", "").strip()
        name       = request.form.get("name", "").strip()
        email      = request.form.get("email", "").strip()
        class_name = request.form.get("class_name", "").strip()
        if not reg_number or not name:
            flash("Registration number and name are required.", "danger")
            return render_template("students/add.html")
        with db_session() as session:
            if session.query(Student).filter_by(reg_number=reg_number).first():
                flash(f"Student {reg_number} already exists.", "warning")
                return render_template("students/add.html")
            session.add(Student(reg_number=reg_number, name=name,
                                email=email or None, class_name=class_name or None))
        flash(f"Student {name} added successfully.", "success")
        return redirect(url_for("students.index"))
    return render_template("students/add.html")


@students_bp.route("/students/import", methods=["GET", "POST"])
@login_required
def bulk_import():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename.endswith(".csv"):
            flash("Please upload a valid CSV file.", "danger")
            return render_template("students/import.html")
        content = file.read().decode("utf-8")
        reader  = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or not {"reg_number","name"}.issubset(set(reader.fieldnames)):
            flash("CSV must have columns: reg_number, name (email and class_name optional).", "danger")
            return render_template("students/import.html")
        added=0; skipped=0; errors=[]
        with db_session() as session:
            for i, row in enumerate(reader, start=2):
                reg  = row.get("reg_number","").strip()
                name = row.get("name","").strip()
                if not reg or not name:
                    errors.append(f"Row {i}: missing fields"); continue
                if session.query(Student).filter_by(reg_number=reg).first():
                    skipped+=1; continue
                session.add(Student(reg_number=reg, name=name,
                    email=row.get("email","").strip() or None,
                    class_name=row.get("class_name","").strip() or None))
                added+=1
        msg = f"Import complete: {added} added, {skipped} skipped."
        if errors: msg += f" {len(errors)} error(s)."
        flash(msg, "success" if not errors else "warning")
        return redirect(url_for("students.index"))
    return render_template("students/import.html")


@students_bp.route("/students/import/template")
@login_required
def import_template():
    content = "reg_number,name,email,class_name\nL1F22BSCS001,Fahad Gujjar,fahad@example.com,BSCS-6A\n"
    return Response(content, mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=students_template.csv"})


@students_bp.route("/students/<int:student_id>/deactivate", methods=["POST"])
@login_required
def deactivate(student_id):
    with db_session() as session:
        student = session.get(Student, student_id)
        if student:
            student.is_active = False; name = student.name
        else:
            flash("Student not found.", "danger")
            return redirect(url_for("students.index"))
    flash(f"{name} has been deactivated.", "info")
    return redirect(url_for("students.index"))
