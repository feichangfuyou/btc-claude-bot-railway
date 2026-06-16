#!/usr/bin/env bash
# Keeps the backend running — restarts automatically on crash.
cd "$(dirname "$0")"
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
echo "Starting backend (restart loop — Ctrl+C to stop)"
while true; do
  python run.py
  code=$?
  if [[ "$code" -eq 137 ]]; then
    echo "Backend killed (code=137 — likely OOM) — restarting in 5s..."
    sleep 5
  else
    echo "Backend exited (code=$code) — restarting in 3s..."
    sleep 3
  fi
done
