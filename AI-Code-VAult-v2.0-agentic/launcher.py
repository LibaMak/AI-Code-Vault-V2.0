from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "streamlit_app.py"
HOST = "localhost"
PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
APP_URL = f"http://{HOST}:{PORT}"


def start_streamlit() -> subprocess.Popen[str]:
    """Start Streamlit in a subprocess."""
    streamlit_exe = shutil.which("streamlit")
    if not streamlit_exe:
        streamlit_exe = str(Path(sys.executable).with_name("streamlit.exe"))

    command = [
        streamlit_exe,
        "run",
        str(APP_PATH),
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    return subprocess.Popen(command, cwd=str(ROOT))


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"Could not find Streamlit entry point: {APP_PATH}")

    print("Launching AI Code Vault...")
    process = start_streamlit()

    try:
        time.sleep(2)
        print(f"Opening browser at {APP_URL}")
        webbrowser.open(APP_URL)
        process.wait()
    except KeyboardInterrupt:
        print("Shutting down launcher...")
        process.terminate()


if __name__ == "__main__":
    main()