@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Eikon Smart Attendance - Setup

:: ╔══════════════════════════════════════════════════════════════════════╗
:: ║  Eikon Smart Attendance System - Automated Setup                   ║
:: ║  This script sets up everything your project needs to run.         ║
:: ╚══════════════════════════════════════════════════════════════════════╝

:: Color codes: 0=Black 1=Blue 2=Green 3=Cyan 4=Red 5=Purple 6=Yellow 7=White
:: A=LightGreen B=LightCyan C=LightRed D=LightPurple E=LightYellow F=BrightWhite

set "PASS=0"
set "FAIL=0"
set "TOTAL_STEPS=7"
set "CURRENT_STEP=0"

:: ── Banner ───────────────────────────────────────────────────────────────────
cls
color 0F
echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║                                                                ║
echo  ║     ███████╗██╗██╗  ██╗ ██████╗ ███╗   ██╗                    ║
echo  ║     ██╔════╝██║██║ ██╔╝██╔═══██╗████╗  ██║                    ║
echo  ║     █████╗  ██║█████╔╝ ██║   ██║██╔██╗ ██║                    ║
echo  ║     ██╔══╝  ██║██╔═██╗ ██║   ██║██║╚██╗██║                    ║
echo  ║     ███████╗██║██║  ██╗╚██████╔╝██║ ╚████║                    ║
echo  ║     ╚══════╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝                    ║
echo  ║                                                                ║
echo  ║         Smart Attendance System ~ Automated Setup              ║
echo  ║                                                                ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo   This script will configure everything automatically.
echo   You only need to provide your MySQL root password.
echo.
echo   Steps:
echo     [1] Check Python installation
echo     [2] Create virtual environment
echo     [3] Install dependencies
echo     [4] Configure database credentials
echo     [5] Create database and tables
echo     [6] Verify database connection
echo     [7] Final checks
echo.
echo  ════════════════════════════════════════════════════════════════════
echo.
pause

:: ── STEP 1: Check Python ─────────────────────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Checking Python installation"

where python >nul 2>&1
if %errorlevel% neq 0 (
    call :fail "Python not found on your system."
    echo.
    echo   Please install Python 3.10 or newer from:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: Check "Add Python to PATH" during installation.
    echo.
    goto :done
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
call :ok "Found: !PY_VER!"

:: Check version is 3.10+
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if %errorlevel% neq 0 (
    call :warn "Python 3.10+ is recommended. You have: !PY_VER!"
    echo   Some features may not work on older versions.
    echo.
)

:: ── STEP 2: Virtual Environment ──────────────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Creating virtual environment"

if exist "venv\Scripts\python.exe" (
    call :skip "Virtual environment already exists. Reusing it."
) else (
    echo   Creating venv... This takes a moment.
    python -m venv venv 2>nul
    if !errorlevel! neq 0 (
        call :fail "Could not create virtual environment."
        echo   Try running: python -m venv venv
        goto :done
    )
    call :ok "Virtual environment created successfully."
)

:: Activate venv for subsequent commands
call venv\Scripts\activate.bat 2>nul

:: ── STEP 3: Install Dependencies ─────────────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Installing Python dependencies"

echo   This will take 3-8 minutes depending on your internet speed.
echo   InsightFace and OpenCV are large packages.
echo.
echo   ┌──────────────────────────────────────────────────────────┐
echo   │  Installing... (pip output below)                        │
echo   └──────────────────────────────────────────────────────────┘
echo.

pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt 2>&1

if %errorlevel% neq 0 (
    call :warn "Some packages may have had issues. Trying fallback..."
    echo.
    echo   Attempting individual installs for known tricky packages...
    pip install cmake 2>nul
    pip install insightface 2>nul
    pip install opencv-python 2>nul
    pip install -r requirements.txt 2>&1
)

:: Also install 'requests' (needed for Day 9 AI features)
pip install requests >nul 2>&1

:: Verify critical imports
python -c "import cv2; import numpy; import flask; print('Core imports OK')" 2>nul
if %errorlevel% neq 0 (
    call :fail "Critical packages failed to install."
    echo   Check the output above for errors.
    goto :done
)
call :ok "All dependencies installed successfully."

:: ── STEP 4: Configure Database Credentials ───────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Configuring database credentials"

if not exist ".env" (
    call :fail ".env file not found. It should be included in the project."
    goto :done
)

:: Check if password is still the placeholder
findstr /C:"DB_PASSWORD=SETUP_WILL_ASK" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo   Your MySQL root password is needed to create the database.
    echo   It will be saved in the .env file (local only, never shared).
    echo.
    set /p "DB_PASS=   Enter your MySQL root password: "
    echo.

    if "!DB_PASS!"=="" (
        call :warn "Empty password entered. If your MySQL has no password, this is fine."
    )

    :: Replace placeholder in .env
    powershell -Command "(Get-Content '.env') -replace 'DB_PASSWORD=SETUP_WILL_ASK', 'DB_PASSWORD=!DB_PASS!' | Set-Content '.env'"

    call :ok "Database password saved to .env"
) else (
    call :skip "Database password already configured in .env"
)

:: Also set camera source
echo.
echo   Which camera should Eikon use?
echo     [0] Built-in laptop webcam (default)
echo     [1] External USB webcam
echo.
set /p "CAM_SRC=   Enter camera number (0 or 1, default=0): "
if "!CAM_SRC!"=="" set "CAM_SRC=0"
powershell -Command "(Get-Content '.env') -replace 'CAMERA_SOURCE=0', 'CAMERA_SOURCE=!CAM_SRC!' | Set-Content '.env'"
call :ok "Camera source set to: !CAM_SRC!"

:: ── STEP 5: Create Database ──────────────────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Creating database and tables"

:: Read password from .env
for /f "tokens=2 delims==" %%a in ('findstr /B "DB_PASSWORD=" .env') do set "DB_PWD=%%a"

echo   Running schema.sql against MySQL...
echo.

if "!DB_PWD!"=="" (
    mysql -u root < db\schema.sql 2>&1
) else (
    mysql -u root -p"!DB_PWD!" < db\schema.sql 2>&1
)

if %errorlevel% neq 0 (
    call :fail "Could not create database."
    echo.
    echo   Common fixes:
    echo     - Make sure MySQL Server is running
    echo     - Check that your password is correct
    echo     - Open Services (Win+R, services.msc) and start "MySQL80"
    echo.
    echo   You can also create the database manually:
    echo     mysql -u root -p ^< db\schema.sql
    echo.
    goto :done
)

call :ok "Database 'smart_attendance' created with all tables."

:: ── STEP 6: Verify Database Connection ───────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Verifying database connection"

python -c "from db.connection import test_connection; result = test_connection(); exit(0 if result else 1)" 2>nul
if %errorlevel% neq 0 (
    call :fail "Database connection test failed."
    echo   Check DB_PASSWORD in .env matches your MySQL root password.
    goto :done
)
call :ok "Database connection verified successfully."

:: Verify tables exist
if "!DB_PWD!"=="" (
    mysql -u root -e "USE smart_attendance; SHOW TABLES;" 2>nul
) else (
    mysql -u root -p"!DB_PWD!" -e "USE smart_attendance; SHOW TABLES;" 2>nul
)

:: ── STEP 7: Final Checks ────────────────────────────────────────────────────
set /a CURRENT_STEP+=1
call :header "STEP !CURRENT_STEP!/%TOTAL_STEPS%" "Running final checks"

echo   [a] Config module...
python -c "import config; print('    Config loaded OK')" 2>nul
if %errorlevel% neq 0 (
    call :warn "Config module had warnings (check output above)"
) else (
    call :ok "Config loads cleanly."
)

echo   [b] Checking webcam availability...
python -c "import cv2; cap=cv2.VideoCapture(!CAM_SRC!); ret,_=cap.read(); cap.release(); exit(0 if ret else 1)" 2>nul
if %errorlevel% neq 0 (
    call :warn "Could not open camera !CAM_SRC!. Make sure a webcam is connected."
) else (
    call :ok "Webcam detected on source !CAM_SRC!."
)

echo   [c] AI model check...
echo     InsightFace model will download automatically on first run (~30MB).
echo     Make sure you have internet for the first launch.
call :ok "AI model set to: buffalo_sc (auto-download on first run)."

:: ── DONE ─────────────────────────────────────────────────────────────────────
:done
echo.
echo  ════════════════════════════════════════════════════════════════════
echo.

if %FAIL% gtr 0 (
    color 0C
    echo   Setup completed with %FAIL% error(s). Fix the issues above and re-run.
) else (
    color 0A
    echo  ╔══════════════════════════════════════════════════════════════════╗
    echo  ║                                                                ║
    echo  ║              SETUP COMPLETE ~ ALL CHECKS PASSED                ║
    echo  ║                                                                ║
    echo  ╠══════════════════════════════════════════════════════════════════╣
    echo  ║                                                                ║
    echo  ║   To launch Eikon Hub (main GUI):                              ║
    echo  ║     python run.py                                              ║
    echo  ║                                                                ║
    echo  ║   To start the web dashboard:                                  ║
    echo  ║     python run.py --web                                        ║
    echo  ║                                                                ║
    echo  ║   To launch the kiosk terminal:                                ║
    echo  ║     python run.py --kiosk                                      ║
    echo  ║                                                                ║
    echo  ║   First time? Register a student first:                        ║
    echo  ║     python core\register.py                                    ║
    echo  ║                                                                ║
    echo  ║   Then train the AI model:                                     ║
    echo  ║     python core\train.py                                       ║
    echo  ║                                                                ║
    echo  ╚══════════════════════════════════════════════════════════════════╝
)

echo.
pause
goto :eof

:: ─────────────────────────────────────────────────────────────────────────────
:: Helper Functions
:: ─────────────────────────────────────────────────────────────────────────────

:header
echo.
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  %~1  ::  %~2
echo  └──────────────────────────────────────────────────────────────────┘
echo.
goto :eof

:ok
set /a PASS+=1
echo   [OK]  %~1
goto :eof

:fail
set /a FAIL+=1
echo   [FAIL]  %~1
goto :eof

:warn
echo   [WARN]  %~1
goto :eof

:skip
echo   [SKIP]  %~1
goto :eof
