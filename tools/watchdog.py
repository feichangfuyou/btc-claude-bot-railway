"""
ClaudeBot Watchdog — Auto-restart and health monitoring
========================================================
Runs the bot as a subprocess and restarts on crash.
Monitors /health endpoint for liveness.

Usage:
  python -m tools.watchdog
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

MAX_RESTARTS = 50
RESTART_COOLDOWN = 5
HEALTH_CHECK_INTERVAL = 30
HEALTH_URL = "http://localhost:8000/health"
MAX_HEALTH_FAILURES = 3

restart_count = 0
process = None


def start_bot():
    global process, restart_count
    restart_count += 1
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] 🚀 Starting ClaudeBot (attempt {restart_count}/{MAX_RESTARTS})...")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    process = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=project_root,
    )
    return process


def stop_bot(sig=None, frame=None):
    if process and process.poll() is None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] 🛑 Stopping ClaudeBot (PID {process.pid})...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    raise SystemExit(0)


def check_health():
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("status") != "ok":
                return False
            if data.get("price_age_sec", 0) > 600:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] ⚠ Price data stale ({data['price_age_sec']:.0f}s)")
                return False
            return True
    except Exception:
        return False


signal.signal(signal.SIGINT, stop_bot)
signal.signal(signal.SIGTERM, stop_bot)


def main():
    global process

    process = start_bot()
    health_failures = 0
    last_health_check = time.time()
    time.sleep(15)

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
            health_failures = 0
            process = start_bot()
            time.sleep(15)
            continue

        now = time.time()
        if now - last_health_check >= HEALTH_CHECK_INTERVAL:
            last_health_check = now
            if check_health():
                health_failures = 0
            else:
                health_failures += 1
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] ⚠ Health check failed ({health_failures}/{MAX_HEALTH_FAILURES})")

                if health_failures >= MAX_HEALTH_FAILURES:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{ts}] 🛑 Bot appears hung — force restarting...")
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    health_failures = 0
                    time.sleep(RESTART_COOLDOWN)
                    process = start_bot()
                    time.sleep(15)

        time.sleep(2)


if __name__ == "__main__":
    main()
