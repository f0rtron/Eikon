"""
run.py — Eikon Launcher

Usage:
    python run.py          → Launch Eikon Hub GUI
    python run.py --web    → Start Flask web dashboard
    python run.py --kiosk  → Launch fullscreen kiosk (attendance mode)
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def get_venv_python():
    windows_path = ROOT / "venv" / "Scripts" / "python.exe"
    unix_path = ROOT / "venv" / "bin" / "python"
    
    if windows_path.exists():
        return str(windows_path)
    elif unix_path.exists():
        return str(unix_path)
    return None


def main():
    venv_py = get_venv_python()
    if venv_py and Path(sys.executable).resolve() != Path(venv_py).resolve():
        print(f"[Eikon] Detected virtual environment: {venv_py}")
        print("[Eikon] Relaunching main script under venv...")
        cmd = [venv_py] + sys.argv
        try:
            sys.exit(subprocess.run(cmd).returncode)
        except KeyboardInterrupt:
            sys.exit(0)

    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg in ("--web", "--backend", "--server"):
        print("Starting Eikon Web Backend...")
        subprocess.run([sys.executable, str(ROOT / "app.py")])

    elif arg == "--kiosk":
        print("Launching Eikon Kiosk...")
        subprocess.run([sys.executable, str(ROOT / "gui" / "kiosk.py"),
                        "--mode", "attendance", "--subject", "1"])

    else:
        print("Launching Eikon Hub...")
        subprocess.run([sys.executable, str(ROOT / "gui" / "eikon_hub.py")])


if __name__ == "__main__":
    main()
