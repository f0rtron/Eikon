"""
app.py — Flask application entry point
"""

import logging
from flask import Flask, send_from_directory
from flask_login import LoginManager

from config import SECRET_KEY, DEBUG, HOST, PORT, PHOTOS_DIR
from db.connection import init_db, test_connection
from db.models import User

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="app/templates",
        static_folder="app/static",
    )
    app.config["SECRET_KEY"]       = SECRET_KEY
    app.config["WTF_CSRF_ENABLED"] = False   # disabled for local API routes

    # ── Flask-Login ───────────────────────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view             = "auth.login"
    login_manager.login_message          = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        from db.connection import Session
        from sqlalchemy.orm import make_transient
        session = Session()
        user = session.get(User, int(user_id))
        if user:
            session.expunge(user)
            make_transient(user)
        return user

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes.auth       import auth_bp
    from app.routes.dashboard  import dashboard_bp
    from app.routes.students   import students_bp
    from app.routes.attendance import attendance_bp
    from app.routes.reports    import reports_bp
    from app.routes.api        import api_bp
    from app.routes.ai         import ai_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ai_bp)

    # ── Serve face photos ─────────────────────────────────────────────────────
    @app.route("/photos/<path:filename>")
    def serve_photo(filename):
        return send_from_directory(str(PHOTOS_DIR), filename)

    logger.info("Flask app created — all blueprints registered.")
    return app


if __name__ == "__main__":
    if not test_connection():
        raise SystemExit("Cannot connect to database. Check .env and MySQL service.")

    init_db()
    app = create_app()

    logger.info(f"Starting Flask on http://{HOST}:{PORT}")
    print(f"\n  Smart Attendance Dashboard")
    print(f"  Open in browser:  http://localhost:{PORT}")
    print(f"  Login:            admin / Admin@1234\n")

    app.run(host=HOST, port=PORT, debug=DEBUG)