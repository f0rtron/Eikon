"""
config.py — Central configuration for Smart Attendance System
All settings loaded from .env file. Never hardcode secrets.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parent
DATASET_DIR   = BASE_DIR / "dataset"
ENCODINGS_DIR = BASE_DIR / "encodings"
LOGS_DIR      = BASE_DIR / "logs"
PHOTOS_DIR    = BASE_DIR / "photos"

for _dir in [DATASET_DIR, ENCODINGS_DIR, LOGS_DIR, PHOTOS_DIR]:
    _dir.mkdir(exist_ok=True)

# ─── Database ─────────────────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_NAME     = os.getenv("DB_NAME", "smart_attendance")
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_URL      = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ─── Flask ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-before-deployment")
DEBUG      = os.getenv("DEBUG", "False").lower() == "true"
HOST       = os.getenv("HOST", "0.0.0.0")
PORT       = int(os.getenv("PORT", 5000))

# ─── Camera ───────────────────────────────────────────────────────────────────
CAMERA_SOURCE  = int(os.getenv("CAMERA_SOURCE", 0))
STREAM_QUALITY = int(os.getenv("STREAM_QUALITY", 70))

# ─── Face Recognition ─────────────────────────────────────────────────────────
MODEL_NAME            = os.getenv("MODEL_NAME", "buffalo_sc")
RECOGNITION_THRESHOLD = float(os.getenv("RECOGNITION_THRESHOLD", 0.55))
ANTI_SPOOF_THRESHOLD  = float(os.getenv("ANTI_SPOOF_THRESHOLD", 0.5))
IMAGES_PER_STUDENT    = int(os.getenv("IMAGES_PER_STUDENT", 30))
ENCODINGS_FILE        = ENCODINGS_DIR / "encodings.pkl"
DUPLICATE_WINDOW_SECS = int(os.getenv("DUPLICATE_WINDOW_SECS", 3600))

# ─── Late Arrival ─────────────────────────────────────────────────────────────
LATE_GRACE_MINUTES = int(os.getenv("LATE_GRACE_MINUTES", 10))

# ─── Re-registration Alert ────────────────────────────────────────────────────
REREG_CONFIDENCE_THRESHOLD = float(os.getenv("REREG_CONFIDENCE_THRESHOLD", 0.65))
REREG_CHECK_LAST_N         = int(os.getenv("REREG_CHECK_LAST_N", 5))

# ─── Email Alerts ─────────────────────────────────────────────────────────────
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", 587))
SMTP_USER         = os.getenv("SMTP_USER", "")
SMTP_PASSWORD     = os.getenv("SMTP_PASSWORD", "")
ALERT_ABSENT_DAYS = int(os.getenv("ALERT_ABSENT_DAYS", 3))

# ─── GPIO (Raspberry Pi only) ─────────────────────────────────────────────────
GPIO_LED_GREEN = int(os.getenv("GPIO_LED_GREEN", 17))
GPIO_LED_RED   = int(os.getenv("GPIO_LED_RED",   27))
GPIO_BUZZER    = int(os.getenv("GPIO_BUZZER",    22))

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE  = LOGS_DIR / "app.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("smart-attendance")
logger.info(f"Config loaded. DB: {DB_HOST}/{DB_NAME} | Model: {MODEL_NAME}")

# ─── Groq AI ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama3-8b-8192")
