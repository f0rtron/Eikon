"""
app/routes/attendance.py — Attendance viewing and management
"""

import logging
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from db.connection import db_session
from db.models import Attendance, Student, Subject

logger        = logging.getLogger(__name__)
attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/attendance")
@login_required
def index():
    # filters from query params
    filter_date    = request.args.get("date", date.today().isoformat())
    filter_subject = request.args.get("subject_id", "all")

    try:
        selected_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
    except ValueError:
        selected_date = date.today()

    with db_session() as session:
        # build query
        query = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id == Student.id)
            .join(Subject, Attendance.subject_id == Subject.id)
            .filter(Attendance.marked_date == selected_date)
        )

        if filter_subject != "all":
            query = query.filter(Attendance.subject_id == int(filter_subject))

        records = query.order_by(Attendance.marked_at).all()

        records_list = [
            {
                "id":         a.id,
                "name":       s.name,
                "reg":        s.reg_number,
                "subject":    sub.name,
                "subject_code": sub.code,
                "time":       a.marked_at.strftime("%H:%M:%S"),
                "confidence": f"{a.confidence:.2f}",
                "status":     a.status,
            }
            for a, s, sub in records
        ]

        # all students — to show who is absent
        all_students = session.query(Student).filter_by(is_active=True).all()
        present_ids  = {a.student_id for a, s, sub in records}
        absent_list  = [
            {"name": s.name, "reg": s.reg_number}
            for s in all_students
            if s.id not in present_ids
        ]

        subjects = session.query(Subject).filter_by(is_active=True).all()
        subjects_list = [{"id": s.id, "name": s.name, "code": s.code} for s in subjects]

    return render_template(
        "attendance/index.html",
        records       = records_list,
        absent        = absent_list,
        subjects      = subjects_list,
        selected_date = selected_date.isoformat(),
        selected_subj = filter_subject,
        present_count = len(records_list),
        absent_count  = len(absent_list),
    )


@attendance_bp.route("/attendance/manual", methods=["POST"])
@login_required
def manual_mark():
    """Allow admin to manually mark attendance for a student."""
    reg_number = request.form.get("reg_number", "").strip()
    subject_id = request.form.get("subject_id")
    mark_date  = request.form.get("date", date.today().isoformat())

    if not reg_number or not subject_id:
        flash("Registration number and subject are required.", "danger")
        return redirect(url_for("attendance.index"))

    try:
        mark_date = datetime.strptime(mark_date, "%Y-%m-%d").date()
    except ValueError:
        mark_date = date.today()

    with db_session() as session:
        student = session.query(Student).filter_by(reg_number=reg_number).first()
        if not student:
            flash(f"Student {reg_number} not found.", "danger")
            return redirect(url_for("attendance.index"))

        existing = session.query(Attendance).filter_by(
            student_id = student.id,
            subject_id = int(subject_id),
            marked_date = mark_date,
        ).first()

        if existing:
            flash(f"{student.name} is already marked present for this date.", "warning")
            return redirect(url_for("attendance.index"))

        record = Attendance(
            student_id  = student.id,
            subject_id  = int(subject_id),
            marked_date = mark_date,
            confidence  = 1.0,
            status      = "manual",
        )
        session.add(record)

    flash(f"Manually marked {student.name} as present.", "success")
    return redirect(url_for("attendance.index"))
