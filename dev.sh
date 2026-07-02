#!/usr/bin/env bash
# 개발 서버 동시 실행 — FastAPI(:8000) + Vite/React(:5173)
# 사용: ./dev.sh        (Ctrl-C 로 두 서버 함께 종료)
set -euo pipefail
cd "$(dirname "$0")"

# 프론트 의존성 최초 1회 설치
if [ ! -d frontend/node_modules ]; then
  echo "[dev] 프론트 의존성 설치…"
  (cd frontend && npm install)
fi

# 백엔드 의존성(fastapi 등) 없으면 설치
if ! uv run python -c "import fastapi" >/dev/null 2>&1; then
  echo "[dev] 백엔드 의존성 설치…"
  uv pip install -r backend/requirements.txt
fi

# 환경 자가진단 (경고만 — 준비 미완이어도 서버 기동은 막지 않는다)
uv run python -m rag.preflight || true

# 백엔드(FastAPI) 백그라운드 실행
echo "[dev] FastAPI → http://localhost:8000"
uv run uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# 종료(Ctrl-C) 시 백엔드도 함께 정리
cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

# 프론트(Vite) 포그라운드 실행 — 이 프로세스를 종료하면 백엔드도 함께 내려간다
echo "[dev] Vite  → http://localhost:5173"
cd frontend && npm run dev
