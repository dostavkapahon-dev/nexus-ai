#!/usr/bin/env bash
# NEXUS AI — локальный запуск одной командой.
# Поднимает backend (FastAPI :8000) и frontend (Vite :5173).
# Использование:  ./start.sh        — запустить всё
#                 ./start.sh back    — только backend
#                 ./start.sh front   — только frontend
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

start_back() {
  echo "▶ Backend (http://localhost:8000)"
  cd "$ROOT/backend"
  [ -d venv ] || python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
  [ -f .env ] || cp "$ROOT/.env.example" .env && echo "  ⚠ заполни backend/.env ключами"
  uvicorn main:app --reload --port 8000
}

start_front() {
  echo "▶ Frontend (http://localhost:5173)"
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm install
  npm run dev
}

case "${1:-all}" in
  back)  start_back ;;
  front) start_front ;;
  all)
    ( start_back ) &
    BACK_PID=$!
    start_front
    kill $BACK_PID 2>/dev/null || true
    ;;
esac
