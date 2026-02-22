"""
Launcher for the Streamlit app. Handles Ctrl+C so the app stops quickly
instead of waiting for Streamlit's internal shutdown.
"""
import os
import signal
import subprocess
import sys


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless", "true",
    ]
    proc = subprocess.Popen(cmd, cwd=script_dir)

    def stop(_=None):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if sys.platform != "win32":
        signal.signal(signal.SIGQUIT, stop)

    try:
        proc.wait()
    except KeyboardInterrupt:
        stop()
    sys.exit(proc.returncode or 0)


if __name__ == "__main__":
    main()
