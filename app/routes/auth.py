"""
app/routes/auth.py — Authentication routes
Login, logout, and password utilities.
"""

import logging
import bcrypt
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from db.connection import db_session
from db.models import User

logger  = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(12)).decode()

def check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── Routes ───────────────────────────────────────────────────────────────────

@auth_bp.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not username or not password:
            flash("Please enter username and password.", "danger")
            return render_template("auth/login.html")

        with db_session() as session:
            user = session.query(User).filter_by(
                username=username, is_active=True
            ).first()

            if not user or not check_password(password, user.password_hash):
                logger.warning(f"Failed login attempt for username: {username!r}")
                flash("Invalid username or password.", "danger")
                return render_template("auth/login.html")

            # update last login
            user.last_login = datetime.utcnow()
            session.flush()
            user_id   = user.id
            user_role = user.role
            user_name = user.username

        # load fresh user object for flask-login (outside the session above)
        with db_session() as session:
            fresh_user = session.get(User, user_id)
            login_user(fresh_user, remember=remember)

        logger.info(f"Login: {user_name} ({user_role})")
        flash(f"Welcome back, {user_name}!", "success")

        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logger.info(f"Logout: {current_user.username}")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
