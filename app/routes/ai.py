"""
app/routes/ai.py — Nixa AI assistant for Eikon attendance queries

The AI receives live attendance data from MySQL as context,
so it answers questions about actual records — not hallucinations.

Endpoints:
    POST /ai/chat       — web dashboard (streaming)
    POST /api/ai/chat   — Flutter app (non-streaming JSON)
"""

import json
import logging
import requests
from datetime import date, timedelta
from flask import Blueprint, request, Response, jsonify, stream_with_context
from flask_login import login_required
from sqlalchemy import func

from config import GROQ_API_KEY, GROQ_MODEL
from db.connection import db_session
from db.models import Student, Subject, Attendance

logger = logging.getLogger(__name__)
ai_bp  = Blueprint("ai", __name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ─── Context builder ──────────────────────────────────────────────────────────

def _build_context() -> str:
    """
    Pull live attendance data from MySQL and format it as
    a context string injected into every Groq prompt.
    """
    today = date.today()

    with db_session() as session:
        total_students = session.query(Student).filter_by(is_active=True).count()

        present_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date==today, Attendance.status=="present")\
            .scalar() or 0

        late_today = session.query(func.count(func.distinct(Attendance.student_id)))\
            .filter(Attendance.marked_date==today, Attendance.status=="late")\
            .scalar() or 0

        absent_today = total_students - present_today - late_today

        # weekly summary
        weekly = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            p = session.query(func.count(func.distinct(Attendance.student_id)))\
                .filter(Attendance.marked_date==d).scalar() or 0
            weekly.append(f"{d.strftime('%A %d %b')}: {p}/{total_students} present")

        # defaulters
        total_days = session.query(
            func.count(func.distinct(Attendance.marked_date))
        ).scalar() or 1

        defaulters = []
        for st in session.query(Student).filter_by(is_active=True).all():
            attended = session.query(func.count(Attendance.id))\
                .filter_by(student_id=st.id).scalar() or 0
            pct = round(attended / total_days * 100)
            if pct < 75:
                defaulters.append(f"{st.name} ({st.reg_number}): {pct}%")

        # re-registration needed
        rereg = [
            f"{st.name} ({st.reg_number})"
            for st in session.query(Student)
            .filter_by(is_active=True, needs_reregistration=True).all()
        ]

        # subjects
        subjects = [
            f"{s.code}: {s.name}"
            for s in session.query(Subject).filter_by(is_active=True).all()
        ]

        # recent 10 records
        recent = (
            session.query(Attendance, Student, Subject)
            .join(Student, Attendance.student_id==Student.id)
            .join(Subject, Attendance.subject_id==Subject.id)
            .order_by(Attendance.marked_at.desc()).limit(10).all()
        )
        recent_lines = [
            f"- {s.name} ({s.reg_number}) → {sub.code} at "
            f"{a.marked_at.strftime('%H:%M')} [{a.status}] conf={a.confidence:.2f}"
            for a, s, sub in recent
        ]

    context = f"""
You are Nixa, the AI assistant for Eikon — a face recognition attendance system.
You have access to LIVE attendance data. Answer questions accurately using this data.

=== TODAY ({today.strftime('%A, %d %B %Y')}) ===
Total Students: {total_students}
Present: {present_today}
Late: {late_today}
Absent: {absent_today}
Attendance Rate: {round((present_today + late_today) / total_students * 100) if total_students else 0}%

=== WEEKLY SUMMARY (last 7 days) ===
{chr(10).join(weekly)}

=== SUBJECTS ===
{chr(10).join(subjects) or 'No subjects configured'}

=== DEFAULTERS (below 75%) ===
{chr(10).join(defaulters) if defaulters else 'No defaulters — all students above 75%'}

=== STUDENTS NEEDING FACE RE-REGISTRATION ===
{chr(10).join(rereg) if rereg else 'None — all face encodings are healthy'}

=== RECENT ATTENDANCE RECORDS ===
{chr(10).join(recent_lines) if recent_lines else 'No records yet'}

=== INSTRUCTIONS ===
- Answer in a helpful, professional tone
- Be concise but complete
- If asked about a specific student not in the data, say you don't have that record
- Do not make up attendance numbers — only use the data above
- You can suggest actions (e.g. "contact the student", "check manually")
- Keep responses under 200 words unless detailed analysis is requested
"""
    return context.strip()


# ─── Web dashboard — streaming ────────────────────────────────────────────────

@ai_bp.route("/ai/chat", methods=["POST"])
@login_required
def chat_stream():
    """
    Streaming endpoint for web dashboard.
    Returns Server-Sent Events — text streams word by word like ChatGPT.
    """
    if not GROQ_API_KEY:
        return jsonify({"error": "AI service not configured. Add GROQ_API_KEY to .env"}), 503

    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])   # list of {role, content} dicts

    if not message:
        return jsonify({"error": "Message required"}), 400

    context   = _build_context()
    messages  = [{"role": "system", "content": context}]
    messages += [{"role": m["role"], "content": m["content"]}
                 for m in history[-6:]]   # last 6 messages for context
    messages += [{"role": "user", "content": message}]

    def generate():
        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    messages,
                    "max_tokens":  400,
                    "temperature": 0.4,
                    "stream":      True,
                },
                stream=True,
                timeout=30,
            )

            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    chunk = json.loads(line)
                    token = chunk["choices"][0]["delta"].get("content", "")
                    if token:
                        yield f"data: {json.dumps({'token': token})}\n\n"
                except (json.JSONDecodeError, KeyError):
                    continue

        except requests.Timeout:
            yield f"data: {json.dumps({'error': 'AI service timeout — please try again'})}\n\n"
        except Exception as e:
            logger.error(f"Groq stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ─── Flutter app — non-streaming JSON ─────────────────────────────────────────

@ai_bp.route("/api/ai/chat", methods=["POST"])
def flutter_chat():
    """Non-streaming endpoint for Flutter app."""
    if not GROQ_API_KEY:
        return jsonify({"error": "AI service not configured"}), 503

    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message required"}), 400

    context  = _build_context()
    messages = [{"role": "system", "content": context}]
    messages += [{"role": m["role"], "content": m["content"]}
                 for m in history[-6:]]
    messages += [{"role": "user", "content": message}]

    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    messages,
                "max_tokens":  400,
                "temperature": 0.4,
                "stream":      False,
            },
            timeout=30,
        )
        result = resp.json()
        reply  = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except requests.Timeout:
        return jsonify({"error": "AI service timeout — try again"}), 504
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return jsonify({"error": str(e)}), 500
