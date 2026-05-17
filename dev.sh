#!/usr/bin/env bash
# Start the FastAPI backend and the Vite dev server together.
# One command, hot-reload for both. Ctrl+C stops everything.
#
#   ./dev.sh
#
# Backend:  http://localhost:8765  (API + WebSocket, /docs for OpenAPI)
# Frontend: http://localhost:5173  (open this; /api and /ws proxy to :8765)

set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# Free a port held by a stale process from a previous crashed/hung run.
# A reloader that died without releasing the socket leaves the port bound
# (often a CLOSED socket whose FD is still open), so a fresh ./dev.sh would
# fail to bind. Reap any holder before (re)starting.
free_port() {
  local port="$1" label="$2" held
  held=$(lsof -ti "tcp:${port}" 2>/dev/null || true)
  if [ -n "${held}" ]; then
    echo "→ port ${port} (${label}) held by stale PID(s): ${held//$'\n'/ } — reaping"
    kill ${held} 2>/dev/null || true
    sleep 1
    held=$(lsof -ti "tcp:${port}" 2>/dev/null || true)
    [ -n "${held}" ] && kill -9 ${held} 2>/dev/null || true
    sleep 1
  fi
}
free_port "${BACKEND_PORT}" backend
free_port "${FRONTEND_PORT}" frontend

# Kill the whole process group on exit so neither server is orphaned.
pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "→ backend  : http://localhost:${BACKEND_PORT}"
python -m uvicorn backend.main:app --reload --port "${BACKEND_PORT}" &
pids+=($!)

if [ ! -d frontend/node_modules ]; then
  echo "→ installing frontend deps (first run)…"
  (cd frontend && npm install)
fi

echo "→ frontend : http://localhost:5173"
(cd frontend && npm run dev) &
pids+=($!)

# Portable wait (macOS ships bash 3.2, no `wait -n`): poll until either
# server exits, then the EXIT trap brings the other down too.
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do
  sleep 1
done
