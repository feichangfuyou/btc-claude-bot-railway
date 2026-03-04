"""
ClaudeBot Watchdog — Auto-restart and health monitoring
========================================================
Runs backend.py as a subprocess and restarts on crash.
Monitors /health endpoint for liveness.

Usage:
  python watchdog.py
"""

import subprocess
import sys
import time
import signal
import os

MAX_RESTARTS = 10
RESTART_COOLDOWN = 5
HEALTH_CHECK_INTERVAL = 30
HEALTH_URL = "http://localhost:8000/health"

restart_count = 0
process = None


def start_bot():
    global process, restart_count
    restart_count += 1
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] 🚀 Starting ClaudeBot (attempt {restart_count}/{MAX_RESTARTS})...")
    process = subprocess.Popen(
        [sys.executable, "backend.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    return process


def stop_bot(sig=None, frame=None):
    global process
    if process and process.poll() is None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] 🛑 Stopping ClaudeBot (PID {process.pid})...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    raise SystemExit(0)


signal.signal(signal.SIGINT, stop_bot)
signal.signal(signal.SIGTERM, stop_bot)


def main():
    global restart_count

    process = start_bot()

    while True:
        exit_code = process.poll()

        if exit_code is not None:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] ⚠ ClaudeBot exited with code {exit_code}")

            if restart_count >= MAX_RESTARTS:
                print(f"[{ts}] 🛑 Max restarts ({MAX_RESTARTS}) reached — giving up")
                sys.exit(1)

            print(f"[{ts}] ⏳ Restarting in {RESTART_COOLDOWN}s...")
            time.sleep(RESTART_COOLDOWN)
            process = start_bot()

        time.sleep(2)


if __name__ == "__main__":
    main()
