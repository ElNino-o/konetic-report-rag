# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688?logo=fastapi&logoColor=white)
![Uvicorn](https://img.shields.io/badge/Uvicorn-0.49-2094F3?logo=gunicorn&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-API-412991?logo=openai&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.58-FF4B4B?logo=streamlit&logoColor=white)
![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4.3-06B6D4?logo=tailwindcss&logoColor=white)
![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?logo=shadcnui&logoColor=white)
![Radix UI](https://img.shields.io/badge/Radix_UI-primitives-161618?logo=radixui&logoColor=white)

## What this is

KEITI(코네틱) 환경 보고서를 대상으로 한 한국어 RAG Q&A 시스템. 임베딩·리랭킹·LLM 모두 OpenAI API
전용(로컬 모델 없음). 두 프론트엔드가 **같은 `rag/` 코어**를 공유한다:

- `app.py` — Streamlit 버전 (원본, 유지 중)
- `backend/main.py` + `frontend/` — FastAPI + React/Vite 버전 (SSE 스트리밍). `rag/` 로직은 한 줄도
  바꾸지 않고 REST/SSE 로 노출하는 얇은 어댑터 계층.

두 프론트엔드를 수정할 때 `rag/` 코어 로직을 변경하는 경우, 다른 쪽 프론트엔드에도 영향이 없는지 확인할 것.

**저작권**: 인덱싱·인용하는 KEITI 보고서 원문·데이터의 저작권은 **한국환경산업기술원(KEITI)**에 귀속한다.
본 프로젝트는 비영리 연구·데모(PoC)이며 원문 재배포 권한을 부여하지 않는다(README "라이선스 / 저작권" 참조).

## Commands

```bash
# 의존성 설치
uv sync --extra indexing              # 런타임 + 인덱싱(pdfplumber/pandas/chromadb 등)

# 오프라인 인덱싱 (KEITI 코퍼스 청킹+임베딩+적재 → storage/)
uv run python -m rag.indexing.index_pipeline

# Streamlit 버전 실행
uv run streamlit run app.py           # http://localhost:8501

# FastAPI + React 버전 실행 — 한 스크립트로 두 서버(의존성 자동 설치, Ctrl-C 로 함께 종료)
./dev.sh                              # macOS/Linux (dev.bat = Windows)
# 또는 수동 두 프로세스:
uv pip install -r backend/requirements.txt   # 최초 1회
uv run uvicorn backend.main:app --reload --port 8000
cd frontend && npm install && npm run dev    # http://localhost:5173 (/api → 8000 프록시)

# requirements.txt(Streamlit Cloud 배포용)는 자동 생성물 — 직접 편집 금지, pyproject 변경 시 재생성
uv pip compile --universal --no-annotate --no-header pyproject.toml -o requirements.txt

# 프론트엔드 빌드/타입체크
cd frontend && npm run build          # tsc -b && vite build
```

자동화된 테스트 스위트는 없다. 검증은 `uv run python -m rag.qa_pipeline "질문"`로 파이프라인을 직접
실행하거나(파일 하단 `if __name__ == "__main__"`), 앱을 띄워 수동 QA한다.

## Architecture

### 데이터 흐름

```
인덱싱(로컬 1회, KEITI 코퍼스):
  PDF + report_list.xlsx → structure_chunker(구조 인식 청킹) → OpenAI 임베딩
  → storage/{chunks.jsonl, reports_openai.npz, bm25_openai.pkl}  (커밋 대상)

런타임(모든 프론트엔드 공통):
  질문 → 질의 임베딩 → vector_store(하이브리드: 벡터+BM25) → rerank(off/openai)
  → LLM 답변 생성(스트리밍, 출처·페이지 인용)
```

### `rag/` 모듈 (런타임 코어 — 두 프론트엔드가 공유)

- `config.py` — 설정 단일 출처. `.env`/`st.secrets` 로드, 경로, 백엔드 선택, 가격표(`PRICES`),
  로깅 레벨. `VECTOR_BACKEND`(`chroma`/`memory`/`remote`), `RERANK_BACKEND`(`off`/`openai`) 교체 지점.
  `chromadb` 미설치 시 `chroma`/`remote` → `memory` 자동 폴백(클라우드 안전장치).
- `services.py` — OpenAI 클라이언트(키별 캐시)·임베딩·Chroma 클라이언트·BM25 로드/저장.
- `vector_store.py` — 벡터 검색 추상화. `search(query_vec, top_k, where)` 하나의 인터페이스로
  chroma(로컬 영속)/memory(npz+chunks.jsonl, Streamlit Cloud 등 서버리스)/remote(터널된 Chroma 서버)를
  디스패치. `qa_pipeline.hybrid_search` 가 여기 결과에 BM25 점수를 융합.
- `qa_pipeline.py` — 오케스트레이터: `hybrid_search`(벡터 w·+BM25(1-w), `VECTOR_WEIGHT=0.3`) →
  `rerank`(openai 리스트와이즈 or off) → `generate_answer`/`generate_answer_stream`. 답변 형태
  3종(`summary`/`normal`/`expert`, `STYLE_GUIDE`/`STYLE_MAX_TOKENS`)을 지원하며, 같은 질문에서 형태만
  바꾸면 `generate_only`/`search_rerank`+재사용으로 검색·임베딩·리랭크를 재실행하지 않는다(비용 0).
  신형(gpt-5 계열, `reasoning_effort`)과 구형 모델 인자를 순서대로 시도하는 폴백(`_request_attempts`)
  포함. LLM 호출 실패 시 발췌형 폴백(`_extractive_answer`)으로 항상 응답을 반환.
- `monitoring.py` — 서버 로깅 + 단계별(임베딩/리랭크/LLM) 토큰·비용(USD) 추정. `config.PRICES`는
  추정치이므로 실제 단가에 맞춰 조정 필요.
- `upload_pipeline.py` — "내 문서 업로드" 모드: 런타임에 PDF 파싱(PyMuPDF)·일반 청킹·세션 메모리
  임베딩·코사인 검색. KEITI 고정 코퍼스와 별개 경로(인덱싱 불필요, 세션 한정).
- `preflight.py` — 환경 자가진단 CLI(`python -m rag.preflight`): storage 아티팩트·OpenAI 키·벡터
  백엔드·원본데이터·프론트 node_modules 를 실측해 한국어로 조치 안내. `dev.sh`/`dev.bat`가 기동 전 호출.
- `indexing/` — 오프라인 전용(배포 런타임에는 불필요):
  - `structure_chunker.py` — KEITI 보고서 구조 인식 파싱(챕터/섹션/표/인터뷰/각주).
  - `semantic.py` — 의미 경계 분할(A안).
  - `index_pipeline.py` — 엑셀(`report_list.xlsx`, 2시트: 국가별/정책규제)↔PDF 매핑 → 청킹 →
    Contextual Retrieval(LLM 1문장 맥락, C안) → 임베딩 → Chroma+BM25 적재.
  - `build_openai_index.py` — 기존 청크 재사용 재임베딩(전체 재청킹 없이 임베딩만 갱신).
  - `export_npz.py` — Chroma → npz 추출(memory 백엔드 배포용 산출물 생성).

### 백엔드 어댑터 (`backend/main.py`)

- `rag/` 함수를 REST + SSE로 노출하는 얇은 계층. `/api/query`(검색+스트리밍 답변),
  `/api/answer`(근거 재사용, 형태 전환만), `/api/upload`(업로드 세션), `/api/documents*`(우측 문서
  패널), `/api/pdf`(원본 PDF, 로컬에만 존재 가능).
- `_QUERY_LOCK`(전역 `Lock`)으로 질의 1건을 직렬화 — `qa_pipeline`의 `LAST_*_USAGE`가 모듈 전역이라
  동시 요청 시 사용량이 섞이는 것을 막기 위함(PoC/저트래픽 가정). 다중 동시 사용자를 지원하려면
  사용량 집계를 요청 로컬로 옮기는 리팩터가 선행되어야 한다.
- 업로드 임베딩 행렬은 클라이언트로 보낼 수 없어 `UPLOAD_SESSIONS`(서버 프로세스 메모리)에
  세션ID로 보관 — 프로세스 재시작 시 소실됨.

### 프론트엔드 (`frontend/`, React 18 + Vite 5 + TS + Tailwind v4 + shadcn/ui)

- `App.tsx` — 3-zone 레이아웃(사이드바 · 답변 · 근거 레일) + 상태 오케스트레이션(모드·테마·세션·근거·문서 뷰어).
- `hooks/useAnswerStream.ts` — **질의 스트리밍 상태머신(로직)**. 검색+답변 / 근거 재사용 형태전환 / 형태
  캐시를 담당. 프레젠테이션(QnA)에서 분리 — 단독 재사용·테스트 가능.
- `components/qa/` — `QnA`(질문·형태버튼·답변, thin) · `Citations`(답변 `[n]`을 틸 인용 칩으로 렌더 +
  한국어 조사 뒤 `**굵게**` 보정) · `ProcessDetail`(비용·토큰·모델 = 개발자용, 기본 접힘).
- `components/` — `Sidebar`(사용자 컨트롤만) · `SourceRail`(근거 카드, 인용 hover→하이라이트) ·
  `DocViewer`(문서 전문·PDF 임베드·코네틱 원문 링크 모달) · `UploadBar`.
- `components/ui/` — shadcn 프리미티브(`button` CVA, `dialog` Radix). `lib/utils.ts`=`cn`.
- `index.css` — Tailwind v4 `@theme` 디자인 토큰([docs/DESIGN.md](docs/DESIGN.md) 팔레트 C). 폰트(Pretendard·IBM Plex Mono)는 `index.html` `<link>`.
- 마크다운: `react-markdown`+`remark-gfm`(`singleTilde: false` — 한국어 범위 `~`가 취소선화되는 것 방지).

### 설정 교체 지점

- `RERANK_BACKEND`: `off` | `openai`
- `VECTOR_BACKEND`: `chroma`(로컬 영속) | `memory`(Streamlit Cloud 등 서버리스, npz 필요) | `remote`(터널된 Chroma)
- `OPENAI_MODEL`/`OPENAI_EMBED_MODEL`/`OPENAI_RERANK_MODEL`: 임베딩·LLM·리랭크는 항상 OpenAI 단일 소스.

### BYOK / 키 관리

공용 키(`OPENAI_API_KEY`, `.env` 또는 배포 secrets)가 없으면 방문자가 사이드바/프론트에서 직접 키를
입력하는 BYOK 모드로 동작. 키는 세션(브라우저 메모리 또는 Streamlit 세션)에만 보관하고 저장·로깅하지
않는다. 코드에 키를 하드코딩하지 말 것 — 항상 `.env`/`st.secrets`/요청 파라미터로 전달.

## Design System (프론트엔드 UI)

React+FastAPI 버전의 모든 시각 결정은 **[docs/DESIGN.md](docs/DESIGN.md)를 단일 출처**로 삼는다.
색·타이포·간격·레이아웃·모션이 거기 정의되어 있으며, 임의 변경 금지(변경은 명시 승인 후 Decisions Log 기록).
핵심 원칙: 팔레트 C(잉크+틸), Pretendard, 8px 그리드, WCAG AA, **Information Altitude**(시스템 내부
지표를 사용자 화면에 노출 금지 — 청크수·모델명·비용은 "처리 상세"로 접음). UI/QA 작업 시 코드가
DESIGN.md와 다르면 플래그할 것.

## 배포 (Streamlit Cloud)

`app.py`가 메인 파일. 배포 전 로컬에서 `uv run python -m rag.indexing.index_pipeline`로 인덱싱해
`storage/{chunks.jsonl, reports_openai.npz, bm25_openai.pkl}`를 커밋해야 한다. 배포 secrets에는
`VECTOR_BACKEND=memory`(무료티어는 chromadb 미설치)가 필수. 상세 secrets 예시는
[README.md](README.md#배포-streamlit-cloud) 참고.

React+FastAPI 버전 운영 배포는 `npm run build` → `frontend/dist/`를 FastAPI `StaticFiles`로 서빙하거나
별도 정적 호스팅 + `/api`만 FastAPI로 프록시하는 방식을 권장 ([docs/REACT_FASTAPI.md](docs/REACT_FASTAPI.md)).

## Roadmap / 진행 상황

완료 항목·백로그·다음 작업·인수인계는 [docs/PLAN.md](docs/PLAN.md)에 단일 출처로 통합되어 있고,
세션별 변경 로그는 [docs/LOGGING.md](docs/LOGGING.md)에 있다.
