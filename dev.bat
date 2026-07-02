@echo off
REM 개발 서버 동시 실행 — FastAPI(:8000) + Vite/React(:5173)
REM 사용: dev.bat   (백엔드는 새 창, 이 창은 Vite / 각 창에서 Ctrl-C 종료)
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist frontend\node_modules (
  echo [dev] 프론트 의존성 설치...
  pushd frontend && call npm install && popd
)

uv run python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
  echo [dev] 백엔드 의존성 설치...
  uv pip install -r backend\requirements.txt
)

REM 환경 자가진단 (경고만 — 준비 미완이어도 서버 기동은 막지 않는다)
uv run python -m rag.preflight

echo [dev] FastAPI -^> http://localhost:8000  ^(새 창^)
start "konetic-backend" cmd /k "uv run uvicorn backend.main:app --reload --port 8000"

echo [dev] Vite -^> http://localhost:5173
cd frontend && npm run dev
