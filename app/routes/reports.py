"""
app/routes/reports.py — Attendance reports and exports
CSV and PDF export for attendance records.
"""

import io
import csv
import logging
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, Response, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import func

from db.connection import db_session
from db.models import Attendance, Student, Subject

logger     = logging.getLogger(__name__)
reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports")
@login_required
def index():
    with db_session() as session:
        subjects = [
            {"id": s.id, "name": s.name, "code": s.code}
            for s in session.query(Subject).filter_by(is_active=True).all()
        ]

        # summary: total sessions and attendance per student
        students = session.query(Student).filter_by(is_active=True).all()
        total_days = session.query(
            func.count(func.distinct(Attendance.marked_date))
        ).scalar() or 1

        summary = []
        for s in students:
            attended = session.query(func.count(Attendance.id))\
                .filter_by(student_id=s.id).scalar() or 0
            pct = round(attended / total_days * 100) if total_days else 0
            summary.append({
                "name":       s.name,
                "reg":        s.reg_number,
                "class_name": s.class_name or "—",
                "attended":   attended,
                "total":      total_days,
                "pct":        pct,
                "defaulter":  pct < 75,
            })

        summary.sort(key=lambda x: x["pct"])

    return render_template("reports/index.html", subjects=subjects, summary=summary,
                           total_days=total_days)


@reports_bp.route("/reports/export/csv")
@login_required
def export_csv():
    from_date = request.args.get("from", (date.today() - timedelta(days=30)).isoformat())
    to_date   = request.args.get("to",   date.today().isoformat())
    subj_id   = request.args.get("subject_id", "all")

    try:
        d_from = datetime.strptime(from_date, "%Y-%m-%d").date()
        d_to   = datetime.strptime(to_date,   "%Y-%m-%d").date()
    except ValueError:
        d_from = date.today() - timedelta(days=30)
        d_to   = date.today()

    with db_session() as session:
        query = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id == Student.id)
            .join(Subject, Attendance.subject_id == Subject.id)
            .filter(Attendance.marked_date >= d_from)
            .filter(Attendance.marked_date <= d_to)
        )
        if subj_id != "all":
            query = query.filter(Attendance.subject_id == int(subj_id))

        rows = query.order_by(Attendance.marked_date, Student.name).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Reg Number", "Name", "Class", "Subject", "Time", "Confidence", "Status"])
        for a, s, sub in rows:
            writer.writerow([
                a.marked_date.isoformat(),
                s.reg_number,
                s.name,
                s.class_name or "",
                sub.code,
                a.marked_at.strftime("%H:%M:%S"),
                f"{a.confidence:.3f}",
                a.status,
            ])

    filename = f"attendance_{d_from}_{d_to}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
