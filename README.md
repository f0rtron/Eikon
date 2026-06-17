<p align="center">
  <img src="app/static/img/logo_icon_cyprus.png" alt="Eikon Logo" width="100">
</p>

<h1 align="center">E I K O N</h1>
<p align="center">
  <strong>Smart Attendance System</strong><br>
  <em>Your face is your ID.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PyQt6-Desktop_GUI-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PyQt6">
  <img src="https://img.shields.io/badge/Flask-Web_Dashboard-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/Flutter-Mobile_App-02569B?style=for-the-badge&logo=flutter&logoColor=white" alt="Flutter">
  <img src="https://img.shields.io/badge/InsightFace-AI_Engine-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white" alt="InsightFace">
</p>

---

## What is Eikon?

Eikon is a full-stack biometric attendance system that uses **real-time face recognition** to automate student attendance tracking. It combines a PyQt6 desktop hub, a Flask web dashboard, a fullscreen kiosk terminal, and a Flutter mobile app into a single unified platform.

The system captures student faces during registration, trains 512-dimensional embeddings using InsightFace, and then identifies students live through any standard webcam. Anti-spoof detection rejects printed photos and phone screens.

---

## Features

| Feature | Description |
|---------|-------------|
| **Eikon Hub** | PyQt6 desktop command center with action cards, status LEDs, live stats, developer console, and dark/light theme |
| **Guided Registration** | Kiosk-mode face capture with head-turn instructions. 30 images per student, automatic progress tracking |
| **AI Training** | One-click encoding generation. InsightFace buffalo_sc model extracts 512D face embeddings |
| **Live Recognition** | Real-time attendance scanning with color-coded feedback (green/amber/red/blue) |
| **Anti-Spoof Detection** | Rejects printed photos, phone screens, and masks using liveness analysis |
| **Web Dashboard** | Flask-powered admin panel with live camera stream, attendance tables, analytics, and reports |
| **Kiosk Mode** | Fullscreen door-mount interface with pulsing idle animation and auto-scan |
| **Late Detection** | Configurable grace period. Amber status for late arrivals based on class schedule |
| **AI Assistant (Nixa)** | Groq-powered LLM chat. Ask natural language questions about attendance data |
| **PDF Reports** | Export attendance reports with formatted tables |
| **CSV Import** | Bulk student registration via CSV upload |
| **Email Alerts** | Automated absence notifications via SMTP |
| **Demo Data** | One-click seed/clear of 50 demo students + 14 days of attendance logs |
| **Flutter Mobile** | Admin mobile app with configurable server IP for WiFi-based access |

---

## Tech Stack

```
Frontend        PyQt6 (Hub + Kiosk)  /  Jinja2 + JS (Web Dashboard)  /  Flutter (Mobile)
Backend         Flask, Flask-SocketIO, Flask-Login
AI Engine       InsightFace (buffalo_sc), ONNX Runtime, OpenCV
Database        MySQL 8.0, SQLAlchemy ORM, PyMySQL
LLM             Groq API (llama-3.3-70b-versatile)
Auth            bcrypt password hashing, session-based login
Reports         ReportLab (PDF), Pandas (data processing)
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- MySQL Server 8.0+
- Webcam (built-in or USB)
- Internet connection (first run only, for AI model download)

### Automated Setup (Windows)

```bash
# Double-click setup.bat or run from terminal:
setup.bat
```

The script handles everything: virtual environment, dependencies, database creation, and configuration.

### Manual Setup

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your MySQL password

# 4. Create database
mysql -u root -p < db/schema.sql

# 5. Launch
python run.py
```

---

## Usage

### Launch Modes

```bash
python run.py            # Eikon Hub (desktop GUI)
python run.py --web      # Flask web dashboard (localhost:5000)
python run.py --kiosk    # Fullscreen kiosk terminal
```

### Workflow (all from inside the Hub)

1. **Register** - Click Register card, enter student details, camera captures 30 face images
2. **Train** - Click Train card, generates face encodings from all registered students
3. **Recognize** - Click Recognize card, select subject, live attendance scanning begins
4. **Dashboard** - Click Dashboard card, opens web admin panel in browser

### Recognition Feedback

| Color | Status |
|-------|--------|
| 🟢 Green | Recognized, attendance marked |
| 🟡 Amber | Recognized but late |
| 🔵 Blue | Already marked today |
| 🔴 Red | Unknown face |
| ⚫ Dark Red | Spoof detected |

---

## Project Structure

```
eikon/
├── gui/
│   ├── eikon_hub.py        # Central Hub (PyQt6 dashboard)
│   └── kiosk.py            # Fullscreen kiosk (register + attendance)
├── core/
│   ├── register.py         # Face capture pipeline
│   ├── train.py            # InsightFace embedding generator
│   ├── recognize.py        # Real-time face matching loop
│   ├── face_engine.py      # Shared InsightFace model loader
│   └── anti_spoof.py       # Liveness detection module
├── app/
│   ├── routes/
│   │   ├── api.py          # REST API endpoints
│   │   ├── dashboard.py    # Dashboard views
│   │   ├── students.py     # Student CRUD + CSV import
│   │   ├── reports.py      # PDF export + analytics
│   │   ├── ai.py           # Groq LLM chat (Nixa)
│   │   └── demo.py         # Demo data seeder
│   ├── templates/          # Jinja2 HTML templates
│   └── static/             # CSS, JS, images
├── db/
│   ├── schema.sql          # MySQL table definitions
│   ├── models.py           # SQLAlchemy ORM models
│   └── connection.py       # Database session factory
├── utils/
│   ├── camera.py           # Cross-platform camera abstraction
│   └── email_alert.py      # SMTP notification system
├── config.py               # Central config (reads .env)
├── app.py                  # Flask application factory
├── run.py                  # Unified launcher
├── setup.bat               # One-click Windows setup
├── requirements.txt        # Python dependencies
└── .env                    # Local environment variables
```

---

## Configuration

All settings are managed through the `.env` file:

| Setting | Default | Description |
|---------|---------|-------------|
| `CAMERA_SOURCE` | `0` | Webcam index (0 = built-in, 1 = USB) |
| `MODEL_NAME` | `buffalo_sc` | InsightFace model (`buffalo_l` for higher accuracy) |
| `RECOGNITION_THRESHOLD` | `0.55` | Face match confidence (lower = more lenient) |
| `ANTI_SPOOF_THRESHOLD` | `0.45` | Liveness check strictness |
| `LATE_GRACE_MINUTES` | `10` | Minutes after class start before marking late |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | LLM model for the Nixa AI assistant |
| `PORT` | `5000` | Flask server port |

---

## Mobile App

The Flutter admin app connects to the Flask backend over WiFi:

1. Both devices on the same network
2. Start backend from the Hub (click Dashboard)
3. In the app, tap the connection icon and enter your laptop's local IP
4. Connects on port 5000

---

## Screenshots

> _Coming soon_

---

## License

This project was built as an academic project for semester coursework.

---

<p align="center">
  <strong>Eikon</strong> · Your face is your ID<br>
  <sub>Built by <a href="https://github.com/f0rtron">f0rtron</a></sub>
</p>
