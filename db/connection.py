"""
db/connection.py — Database engine and session management
All other modules import get_session() from here. Never create
engines or sessions anywhere else.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import DB_URL
from db.models import Base

logger = logging.getLogger(__name__)

# ─── Engine (single instance for entire app) ──────────────────────────────────
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,     # reconnects automatically on dropped connections
    pool_size=5,            # keep 5 connections open
    max_overflow=10,        # allow 10 extra under heavy load
    pool_recycle=3600,      # recycle connections every hour
    echo=False,             # set True to print every SQL query (debug only)
)

# ─── Session factory ──────────────────────────────────────────────────────────
_SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Session = scoped_session(_SessionFactory)


# ─── Public helpers ───────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables that don't exist yet.
    Call once at app startup (app.py does this).
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialised — all tables ready.")
    except OperationalError as e:
        logger.critical(f"Cannot connect to database: {e}")
        raise SystemExit(1)


def get_session():
    """
    Return a database session.
    Prefer using the db_session() context manager below for automatic cleanup.
    """
    return Session()


@contextmanager
def db_session():
    """
    Context manager for safe database operations.

    Usage:
        with db_session() as session:
            student = session.query(Student).filter_by(reg_number="L123").first()

    Commits on success, rolls back on any exception, always closes.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error — rolled back: {e}")
        raise
    finally:
        session.close()


def test_connection() -> bool:
    """
    Quick health check. Returns True if the database is reachable.
    Used at startup and in the admin dashboard health endpoint.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        return True
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return False
