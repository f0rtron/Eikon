"""
utils/email_alert.py — Email alerts via SMTP

Sends alerts when:
1. A student is absent for ALERT_ABSENT_DAYS consecutive days
2. A student drops below 75% attendance
3. A student needs face re-registration

Usage:
    from utils.email_alert import send_absence_alert, send_defaulter_report
    send_absence_alert(student_name, student_email, absent_days)
    send_defaulter_report(admin_email, defaulters_list)
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str) -> bool:
    """Core send function. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured — email not sent.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Smart Attendance <{SMTP_USER}>"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to, msg.as_string())

        logger.info(f"Email sent to {to}: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD in .env")
        return False
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


# ─── Alert templates ──────────────────────────────────────────────────────────

def send_absence_alert(
    student_name: str,
    student_email: str,
    absent_days: int,
    subject_name: str = "",
) -> bool:
    """Alert a student they have been absent too many consecutive days."""
    subject = f"Attendance Alert — {absent_days} Consecutive Absences"
    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:auto">
      <div style="background:#2563EB;padding:24px;border-radius:12px 12px 0 0">
        <h2 style="color:#fff;margin:0">Smart Attendance System</h2>
        <p style="color:#BFDBFE;margin:4px 0 0">Attendance Alert</p>
      </div>
      <div style="background:#F8FAFC;padding:28px;border-radius:0 0 12px 12px;border:1px solid #E2E8F0">
        <p style="color:#1E293B;font-size:15px">Dear <strong>{student_name}</strong>,</p>
        <p style="color:#475569">This is an automated alert from your institution's
           Smart Attendance System.</p>
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:16px;margin:20px 0">
          <p style="color:#DC2626;font-weight:600;margin:0 0 6px">
            ⚠ You have been absent for <strong>{absent_days} consecutive day(s)</strong>
            {f"in {subject_name}" if subject_name else ""}.
          </p>
          <p style="color:#7F1D1D;margin:0;font-size:13px">
            Continued absence may result in you being marked as a defaulter
            (below 75% attendance threshold).
          </p>
        </div>
        <p style="color:#475569;font-size:13px">
          Please contact your teacher or administration if you have a valid reason
          for your absence so that manual attendance can be recorded.
        </p>
        <p style="color:#94A3B8;font-size:12px;margin-top:24px">
          This is an automated message from Smart Attendance System.<br>
          Date: {date.today().strftime("%d %B %Y")}
        </p>
      </div>
    </div>
    """
    return _send(student_email, subject, html)


def send_defaulter_report(admin_email: str, defaulters: list[dict]) -> bool:
    """
    Send weekly defaulter report to admin.

    defaulters: list of dicts with keys: name, reg_number, pct, email
    """
    if not defaulters:
        logger.info("No defaulters — skipping report email.")
        return True

    rows = "".join(f"""
        <tr style="border-bottom:1px solid #E2E8F0">
          <td style="padding:10px 12px;color:#1E293B">{d['name']}</td>
          <td style="padding:10px 12px;color:#64748B;font-family:monospace">{d['reg_number']}</td>
          <td style="padding:10px 12px">
            <span style="background:#FEE2E2;color:#DC2626;padding:2px 8px;
                         border-radius:12px;font-size:12px;font-weight:600">
              {d['pct']}%
            </span>
          </td>
        </tr>
    """ for d in defaulters)

    subject = f"Defaulter Report — {date.today().strftime('%d %B %Y')}"
    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:640px;margin:auto">
      <div style="background:#2563EB;padding:24px;border-radius:12px 12px 0 0">
        <h2 style="color:#fff;margin:0">Smart Attendance System</h2>
        <p style="color:#BFDBFE;margin:4px 0 0">Weekly Defaulter Report</p>
      </div>
      <div style="background:#F8FAFC;padding:28px;border-radius:0 0 12px 12px;border:1px solid #E2E8F0">
        <p style="color:#1E293B">
          The following <strong>{len(defaulters)} student(s)</strong> are below the
          75% attendance threshold as of {date.today().strftime("%d %B %Y")}:
        </p>
        <table style="width:100%;border-collapse:collapse;background:#fff;
                      border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">
          <thead>
            <tr style="background:#F1F5F9">
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Name</th>
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Reg Number</th>
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Attendance</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="color:#94A3B8;font-size:12px;margin-top:24px">
          Generated automatically by Smart Attendance System.<br>
          Login to the dashboard to view full details and export CSV.
        </p>
      </div>
    </div>
    """
    return _send(admin_email, subject, html)


def send_reregistration_alert(admin_email: str, students: list[dict]) -> bool:
    """
    Alert admin that certain students need face re-registration.
    students: list of dicts with name, reg_number
    """
    if not students:
        return True

    rows = "".join(f"""
        <tr style="border-bottom:1px solid #E2E8F0">
          <td style="padding:10px 12px;color:#1E293B">{s['name']}</td>
          <td style="padding:10px 12px;color:#64748B;font-family:monospace">{s['reg_number']}</td>
          <td style="padding:10px 12px">
            <span style="background:#FEF3C7;color:#D97706;padding:2px 8px;
                         border-radius:12px;font-size:12px;font-weight:600">
              Needs Re-registration
            </span>
          </td>
        </tr>
    """ for s in students)

    subject = f"Face Re-registration Required — {len(students)} Student(s)"
    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:640px;margin:auto">
      <div style="background:#D97706;padding:24px;border-radius:12px 12px 0 0">
        <h2 style="color:#fff;margin:0">Smart Attendance System</h2>
        <p style="color:#FEF3C7;margin:4px 0 0">Face Re-registration Alert</p>
      </div>
      <div style="background:#F8FAFC;padding:28px;border-radius:0 0 12px 12px;border:1px solid #E2E8F0">
        <p style="color:#1E293B">
          The recognition confidence for the following students has dropped below
          the acceptable threshold. Their face data needs to be updated.
        </p>
        <table style="width:100%;border-collapse:collapse;background:#fff;
                      border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">
          <thead>
            <tr style="background:#F1F5F9">
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Name</th>
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Reg Number</th>
              <th style="padding:10px 12px;text-align:left;color:#64748B;font-size:12px">Status</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="color:#475569;font-size:13px;margin-top:16px">
          Ask these students to visit the registration kiosk and run
          <code>python core/register.py</code> followed by <code>python core/train.py</code>.
        </p>
      </div>
    </div>
    """
    return _send(admin_email, subject, html)
