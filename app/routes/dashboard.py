"""
app/routes/dashboard.py v2 — includes late arrivals, photo paths, weekly late data
"""

import logging
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from db.connection import db_session
from db.models import Student, Subject, Attendance

logger       = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
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

        # recent 10
        recent = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id==Student.id)
            .join(Subject, Attendance.subject_id==Subject.id)
            .order_by(Attendance.marked_at.desc())
            .limit(10).all()
        )
        recent_list = [
            {
                "name":       s.name,
                "reg":        s.reg_number,
                "subject":    sub.code,
                "time":       a.marked_at.strftime("%H:%M:%S"),
                "confidence": f"{a.confidence:.2f}",
                "status":     a.status,
                "photo_path": a.photo_path or "",
            }
            for a,s,sub in recent
        ]

        # weekly chart — present + late stacked
        weekly_labels, weekly_present, weekly_late = [], [], []
        for i in range(6,-1,-1):
            d = today - timedelta(days=i)
            p = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date==d, Attendance.status=="present")\
                .scalar() or 0
            l = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date==d, Attendance.status=="late")\
                .scalar() or 0
            weekly_labels.append(d.strftime("%a %d"))
            weekly_present.append(p)
            weekly_late.append(l)

        subjects = [{"id":s.id,"name":s.name,"code":s.code}
                    for s in session.query(Subject).filter_by(is_active=True).all()]

        total_days = session.query(func.count(func.distinct(Attendance.marked_date))).scalar() or 1
        defaulters_count = 0
        for st in session.query(Student).filter_by(is_active=True).all():
            attended = session.query(func.count(Attendance.id))\
                .filter_by(student_id=st.id).scalar() or 0
            if (attended/total_days*100) < 75:
                defaulters_count += 1

    return render_template(
        "dashboard/index.html",
        total_students   = total_students,
        present_today    = present_today,
        late_today       = late_today,
        absent_today     = absent_today,
        attendance_pct   = attendance_pct,
        recent_list      = recent_list,
        weekly_labels    = weekly_labels,
        weekly_present   = weekly_present,
        weekly_late      = weekly_late,
        subjects         = subjects,
        defaulters_count = defaulters_count,
        today            = today.strftime("%A, %d %B %Y"),
    )
