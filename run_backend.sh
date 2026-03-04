#!/usr/bin/env bash
# Keeps the backend running — restarts automatically on crash.
cd "$(dirname "$0")"
echo "Starting backend (restart loop — Ctrl+C to stop)"
while true; do
  python backend.py
  code=$?
  echo "Backend exited (code=$code) — restarting in 3s..."
  sleep 3
done
