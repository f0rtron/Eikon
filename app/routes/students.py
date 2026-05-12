"""
app/routes/students.py v2 — Student management + detail + bulk import
"""

import logging, csv, io
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, Response)
from flask_login import login_required
from sqlalchemy import func

from db.connection import db_session
from db.models import Student, Attendance
from config import REREG_CONFIDENCE_THRESHOLD

logger      = logging.getLogger(__name__)
students_bp = Blueprint("students", __name__)


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

    return render_template("students/detail.html",
        student=student_data, conf_history=conf_history, records=records_list,
        total_marked=len(records), present_cnt=present_cnt, late_cnt=late_cnt,
        avg_conf=avg_conf, rereg_threshold=REREG_CONFIDENCE_THRESHOLD)


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
