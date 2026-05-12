# Eikon

**Your face is your ID. Walk in, you're marked.**

Eikon is a face recognition attendance system built for real classrooms. Students walk through the door, the system recognises them in under a second, and attendance is marked automatically. No roll calls, no cards, no apps to open. Just show up.

Built with InsightFace ArcFace, Flask, CustomTkinter, and Flutter. Runs entirely on a local network — no internet, no cloud dependency, no monthly fees.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat&logo=flask)
![Flutter](https://img.shields.io/badge/Flutter-3.x-02569B?style=flat&logo=flutter)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat&logo=mysql&logoColor=white)
![InsightFace](https://img.shields.io/badge/InsightFace-ArcFace-FF6B35?style=flat)


## What it does

The moment a student steps in front of the camera, Eikon runs their face through a 512-dimensional ArcFace embedding, compares it against enrolled students using cosine similarity, checks for liveness (so a printed photo won't fool it), determines whether they arrived on time or late, saves a photo crop as proof, and writes the record to MySQL. All of this happens in under 400 milliseconds.

Teachers get a web dashboard and a Flutter app. Both pull from the same API. The dashboard has a live camera feed so teachers can see the door from their desk. An AI assistant powered by Groq LLaMA 3 answers natural language questions about attendance — who's absent, who's a defaulter, what the week looked like.


## Four interfaces, one backend

**Kiosk Terminal** — fullscreen CustomTkinter app for the classroom door. Animated state machine: idle shows a pulsing ring, scanning fills an arc, green screen means marked present, amber means late, red means unknown or spoof. 8-frame confirmation prevents false marks from someone walking past.

**Web Dashboard** — Flask with Tailwind CSS. Cyprus and Sand colour theme. Weekly stacked bar chart, live camera feed, student detail pages with recognition confidence graphs, bulk CSV import, PDF and CSV export.

**Flutter Mobile App** — five screens: Dashboard, Attendance, Students, Reports, and an AI chat interface. Offline mode caches up to an hour of data so teachers can check attendance even when the server is unreachable.

**AI Assistant** — Groq LLaMA 3.3 70B with live database context injected into every prompt. Answers questions like "which students are at risk of becoming defaulters?" using actual records, not generic responses.


## Prerequisites

You need these installed before anything else.

| Software | Version | Notes |
|-|-|-|
| Python | 3.11 exactly | 3.12 and 3.13 break InsightFace on Windows |
| MySQL Server | 8.0 or later | Community edition is fine |
| Flutter SDK | 3.x | Only needed for the mobile app |
| Git | Any | For cloning and contributing |

On Mac and Linux, Python 3.11 is recommended but InsightFace installs cleanly on newer versions too. The version restriction only matters on Windows.


## Installation

### Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/eikon.git
cd eikon
```

### Create a virtual environment with Python 3.11

```bash
# Windows
py -3.11 -m venv venv
venv\Scripts\activate

# Mac or Linux
python3.11 -m venv venv
source venv/bin/activate
```

Verify:
```bash
python version
# Should print: Python 3.11.x
```

### Install InsightFace — Windows only

InsightFace has a C++ extension that fails to compile on Windows with standard pip. Use a prebuilt wheel instead. Run these in order and do not skip steps.

```bash
pip install "numpy==1.26.4"

pip install https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp311-cp311-win_amd64.whl no-deps

pip install "opencv-python==4.8.1.78" no-deps

pip install onnxruntime onnx

pip uninstall albucore albumentations -y
pip install "albucore==0.0.24" no-deps
pip install "albumentations==1.4.3" no-deps
pip install PyYAML pydantic simsimd stringzilla

pip install matplotlib no-deps
pip install cycler kiwisolver pyparsing python-dateutil contourpy fonttools
```

On Mac or Linux, just run:
```bash
pip install insightface
```

### Install remaining packages

```bash
pip install Flask Flask-Login Flask-WTF Werkzeug
pip install SQLAlchemy PyMySQL cryptography
pip install bcrypt python-dotenv requests
pip install pandas reportlab
pip install customtkinter colorlog
```

### Verify the installation

```bash
python -c "
import numpy as np, cv2, insightface
print('NumPy:', np.__version__)
print('OpenCV:', cv2.__version__)
print('InsightFace:', insightface.__version__)
print('All good.')
"
```

NumPy must be 1.26.4, OpenCV 4.8.1, InsightFace 0.7.3. If any of these differ, the system will not work correctly on Windows.


## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Open .env in any text editor. The fields you must fill in are marked with a comment.

```env
# REQUIRED — your MySQL root password
DB_PASSWORD=your_password_here

# REQUIRED — any random 32+ character string
SECRET_KEY=pick-any-long-random-string-here

# REQUIRED — get a free key at console.groq.com
GROQ_API_KEY=gsk_your_key_here

# Leave everything else at default for now
```

Everything else in the file has sensible defaults. You can tune recognition thresholds, late arrival grace periods, and camera source once the system is running.


## Database Setup

### Start MySQL

```bash
# Windows
net start MySQL80

# Mac
brew services start mysql

# Linux
sudo systemctl start mysql
```

### Create the tables

Windows PowerShell:
```bash
$env:PATH += ";C:\Program Files\MySQL\MySQL Server 8.0\bin"
Get-Content db/schema.sql | mysql -u root -p
```

Mac or Linux:
```bash
mysql -u root -p < db/schema.sql
```

### Set the admin password

The schema inserts a placeholder hash. Generate a real one for your chosen password:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'YourPassword', bcrypt.gensalt(12)).decode())"
```

Then update it in MySQL:

```bash
mysql -u root -p smart_attendance
```

```sql
UPDATE users SET password_hash='paste_hash_here' WHERE username='admin';
EXIT;
```

### Verify everything

```bash
python test_day2.py
```

All five checks should pass. If the database check fails, the password or service is the issue. If the camera check fails, something else has the webcam open.


## Running Eikon

### Register a student

```bash
python core/register.py
```

The camera opens. The student sits in front of it. 30 images are captured automatically over about 30 seconds — the system guides them to vary their angle slightly. Run this once per student.

### Train face encodings

Run this after every registration session:

```bash
python core/train.py
```

This reads all the captured images, generates 512-dimensional face embeddings, and saves them to encodings/encodings.pkl. Takes about 5 seconds on first run while the model downloads.

### Start the web dashboard

```bash
python app.py
```

Open your browser at http://localhost:5000 and log in with the admin credentials you set earlier.

### Start the kiosk

Open a second terminal:

```bash
python gui/kiosk.py subject 1
```

To find your subject IDs:
```bash
mysql -u root -p -e "USE smart_attendance; SELECT id, code, name FROM subjects;"
```

Press ESC to exit the kiosk. Press F11 to toggle fullscreen.

### Live recognition without the kiosk

For testing without the fullscreen interface:

```bash
python core/recognize.py subject 1
```

Press Q to quit.


## Flutter Mobile App

### Set your server address

Open smart_attendance_app/lib/core/constants.dart and update the baseUrl:

```dart
static const String baseUrl = 'http://YOUR_LAPTOP_IP:5000';
```

Find your laptop's IP address:

```bash
# Windows
ipconfig
# Look for IPv4 Address under your WiFi adapter

# Mac or Linux
ifconfig | grep inet
```

Your phone and laptop must be on the same WiFi network.

### Allow HTTP on Android

Add this attribute to the application tag in smart_attendance_app/android/app/src/main/AndroidManifest.xml:

```xml
android:usesCleartextTraffic="true"
```

### Run the app

```bash
cd smart_attendance_app
flutter pub get
flutter run
```

Log in with the same admin credentials as the web dashboard.


## Project Structure

```
eikon/
├── core/
│   ├── face_engine.py       InsightFace singleton — loaded once, shared everywhere
│   ├── register.py          Student registration and face image capture
│   ├── train.py             Generate 512D ArcFace embeddings
│   ├── recognize.py         Live recognition loop with photo capture and late detection
│   └── anti_spoof.py        Liveness detection — LBP, DFT, gradient analysis
│
├── db/
│   ├── models.py            SQLAlchemy ORM models
│   ├── connection.py        Engine and session factory
│   └── schema.sql           MySQL schema — run once to set up
│
├── app/
│   ├── routes/
│   │   ├── auth.py          Login and logout
│   │   ├── dashboard.py     Stats, weekly chart, recent activity
│   │   ├── students.py      List, add, detail page, bulk import
│   │   ├── attendance.py    View by date and subject, manual marking
│   │   ├── reports.py       Summary table, CSV and PDF export
│   │   ├── api.py           JSON API for Flutter and kiosk
│   │   └── ai.py            Groq AI endpoints, streaming and non-streaming
│   ├── templates/           Jinja2 HTML templates
│   └── static/              CSS and JavaScript
│
├── gui/
│   └── kiosk.py             CustomTkinter fullscreen kiosk terminal
│
├── utils/
│   ├── camera.py            Hardware abstraction — same code runs on laptop and Pi
│   ├── email_alert.py       SMTP alerts for absences and defaulters
│   └── report.py            PDF generation with ReportLab
│
├── smart_attendance_app/    Flutter mobile app
│   └── lib/
│       ├── core/            API service, auth provider, theme, constants
│       ├── models/          Data models with fromJson factories
│       ├── screens/         Dashboard, Attendance, Students, Reports, AI Chat
│       └── widgets/         Shared components — stat cards, badges, offline banner
│
├── dataset/                 Face images per student — not committed to git
├── encodings/               Trained face embeddings — not committed to git
├── photos/                  Attendance photo crops — not committed to git
├── logs/                    Application logs — not committed to git
│
├── app.py                   Flask entry point
├── config.py                Central configuration loaded from .env
├── requirements.txt         Python dependencies
└── .env.example             Environment variable template
```


## Contributing

### Branch naming

```
feature/what-you-are-adding
fix/what-you-are-fixing
docs/what-you-are-documenting
```

### Workflow

```bash
git checkout main
git pull origin main
git checkout -b feature/your-feature-name

# Make your changes
git add .
git commit -m "feat: describe what you did"
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub. One team member must approve before it can be merged into main.

### Commit style

```
feat: add something new
fix: fix a bug
docs: update documentation
refactor: restructure existing code
style: formatting only
```


## Troubleshooting

**NumPy binary incompatibility on Windows**
InsightFace was compiled against NumPy 1.x. If another package upgrades NumPy to 2.x, everything breaks. Fix it by pinning back:
```bash
pip install "numpy==1.26.4"
```

**MySQL access denied**
Your DB_PASSWORD in .env does not match your MySQL root password. Verify by connecting manually with `mysql -u root -p`.

**Camera not opening**
Close any other application using the webcam. If you have multiple cameras, try CAMERA_SOURCE=1 in .env.

**Everyone recognised as Unknown**
Run `python core/train.py` after registering students. If already done, try lowering RECOGNITION_THRESHOLD to 0.45 in .env and registering in the same lighting conditions as the classroom.

**AI chat returns no response**
Check that GROQ_API_KEY is set correctly in .env and that GROQ_MODEL is set to `llama-3.3-70b-versatile`. Test your key directly at console.groq.com.

**Flutter cannot connect to server**
Confirm the baseUrl in constants.dart matches your laptop's IP (use ipconfig to check). Flask must show "Running on 0.0.0.0" in its startup log, not just 127.0.0.1. Both devices must be on the same WiFi.

**PDF export fails**
```bash
pip install reportlab
```


## Default Credentials

Username: `admin`
Password: `Admin@1234` (or whatever you set during database setup)

Change this before showing the system to anyone outside the team.


*Eikon — Built as a Final Year Project. University of Central Punjab.*
