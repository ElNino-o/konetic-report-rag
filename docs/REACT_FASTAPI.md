# React + FastAPI 버전 (RAG 코어 보존)

기존 Streamlit(`app.py`)과 **동일한 RAG 파이프라인(`rag/`)** 을 그대로 사용하되,
프론트엔드를 React, 백엔드를 FastAPI로 분리한 버전입니다. RAG 로직은 한 줄도
바꾸지 않았고, FastAPI는 `rag/` 함수를 import 해 REST + SSE 스트리밍으로 노출하는
얇은 어댑터 계층입니다.

```
backend/   FastAPI — rag 파이프라인을 REST/SSE 로 노출 (main.py)
frontend/  React + Vite + TypeScript — 기존 2모드 UX 재현
app.py     기존 Streamlit 버전(그대로 유지, 삭제하지 않음)
```

> **한 번에 실행**: 루트에서 `./dev.sh`(mac/Linux) 또는 `dev.bat`(Windows)를 쓰면 두 서버를
> 함께 띄운다(의존성 자동 설치 + 기동 전 `rag.preflight` 환경 점검). 아래 1·2는 수동 실행 절차다.

## 1. 백엔드 실행 (FastAPI, 포트 8000)

```bash
# 의존성(최초 1회) — 기존 .venv 에 추가 설치
uv pip install -r backend/requirements.txt

# 실행 (프로젝트 루트에서)
uv run uvicorn backend.main:app --reload --port 8000
#  └ .env 의 OPENAI_API_KEY / VECTOR_BACKEND 등 기존 설정을 그대로 사용
```

주요 엔드포인트:

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET  | `/api/config` | 모델·코퍼스·스타일 등 초기 설정 |
| GET  | `/api/documents?mode=keiti` | 문서 목록(우측 패널) |
| GET  | `/api/documents/full?source_file=…` | 문서 전문(추출 텍스트) / PDF 여부 |
| GET  | `/api/pdf?source_file=…` | 로컬 원본 PDF (있을 때) |
| POST | `/api/upload` | PDF 업로드 → 파싱·임베딩(세션 인덱스) |
| POST | `/api/query` | **SSE**: 검색 → 스트리밍 답변 (`meta`→`token…`→`done`) |
| POST | `/api/answer` | **SSE**: 근거 재사용해 형태만 재생성 (검색 비용 0) |

## 2. 프론트엔드 실행 (React, 포트 5173)

```bash
cd frontend
npm install        # 최초 1회
npm run dev        # http://localhost:5173  (/api 는 8000 으로 프록시)
```

브라우저에서 http://localhost:5173 접속.

## 동작 개요 (기존 UX 이식)

- **3가지 답변 형태 버튼**(요약/일반/전문가): 질문 입력 후 원하는 형태 버튼으로 바로
  검색·답변. 답변은 토큰 단위로 **스트리밍** 표시.
- **형태 전환 비용 0**: 같은 질문에서 다른 형태 버튼을 누르면 클라이언트가 보유한
  근거(sources)를 백엔드에 되돌려보내 LLM만 재호출(검색·임베딩·리랭크 생략).
- **두 모드**: KEITI 고정 코퍼스 / 내 문서 업로드(PDF). 업로드 임베딩 행렬은 서버
  세션 메모리에 보관.
- **모니터링**: 단계별 시간 + 토큰/비용, 사이드바 세션 누적.
- **문서 패널**: 질문에 사용된 관련 문서 우선 표시, 전체 보기 토글, 원본 PDF 임베드 /
  배포 시 추출 텍스트 전문 + 코네틱 원문 링크.

## 운영 배포 메모

- 단일 출처 서빙: `npm run build` → `frontend/dist/` 를 FastAPI `StaticFiles` 로 서빙하거나
  Nginx 등에서 정적 호스팅 + `/api` 만 FastAPI 로 프록시.
- BYOK: 공용 키(`OPENAI_API_KEY`)가 없으면 프론트 사이드바에서 키를 입력받아
  요청마다 전달(브라우저 메모리에만 보관).
- `/api/query`·`/api/answer` 는 사용량 전역(qa_pipeline) 보호를 위해 질의 1건을
  직렬화한다(PoC: 저트래픽 가정). 다중 동시 사용자가 필요하면 사용량 집계를
  요청 로컬로 옮기는 리팩터가 필요.
