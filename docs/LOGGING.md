# 세션 작업 로그 (LOGGING)

이 세션에서 수행한 변경을 트랙별로 기록한다. 최신 세션이 위로 온다.
로드맵·다음 작업·인수인계는 [PLAN.md](PLAN.md) 참조(단일 출처로 통합됨).

---

## 2026-07-02 — 프론트엔드 재설계 · 백엔드 정비 · 배포 아티팩트

목표: React+FastAPI 프런트를 "AI가 만든 느낌"에서 벗어나 근거 신뢰 중심으로 엄밀하게
재설계하고, 백엔드·배포·문서의 드리프트/누락을 정리한다. `rag/` 코어 로직은 변경하지 않았다.

### 1. 프론트엔드 재설계 (React 18 + Vite 5 + TS + Tailwind v4 + shadcn/ui)
- **스택 전환**: 손수 작성한 CSS → shadcn/ui 패턴(소유 컴포넌트 + CVA + Radix 프리미티브 + `cn`).
  2026년 트렌드·서비스 안정도 리서치 후 Chakra 대신 Tailwind v4 + shadcn 채택.
- **디자인 시스템 정립**([docs/DESIGN.md](DESIGN.md)): 팔레트 C "잉크 & 틸"(`#16181D` + `#0F766E`),
  Pretendard 본문 · IBM Plex Mono 수치, 8px 그리드, WCAG AA. 색은 실측 3안 비교 후 사용자 선택.
- **Information Altitude 원칙**: 시스템 내부 지표(청크수·모델명·비용)를 기본 화면에서 제거,
  "처리 상세"로 옵트인 접기. 사이드바는 사용자 컨트롤만 노출.
- **1급 인용(citations)**: 답변 `[n]` → 틸 인용 칩, hover 시 근거 카드 강조, 클릭 시 원문 뷰어.

### 2. 프론트엔드 모듈화 (로직/프레젠테이션 분리)
- `hooks/useAnswerStream.ts` — 질의 스트리밍 상태머신(검색+답변 / 근거 재사용 형태전환 / 형태 캐시).
- `components/qa/` — `QnA`(thin) · `Citations`(인용 칩 렌더 + 한국어 조사 뒤 `**굵게**` 보정) ·
  `ProcessDetail`(비용·토큰·모델, 기본 접힘).
- `components/` — `Sidebar` · `SourceRail`(근거 카드) · `DocViewer`(문서 전문·PDF·코네틱 링크 모달) · `UploadBar`.
- `components/ui/` — shadcn 프리미티브(`button` CVA, `dialog` Radix).

### 3. 한국어 마크다운 렌더 버그 수정
- `~` 범위가 GFM 취소선으로 오변환 → `remarkGfm { singleTilde: false }`.
- 한국어 조사 뒤 `**굵게**`가 리터럴 `**`로 노출 → `Citations`에서 직접 `**bold**` 렌더 + 미완결 `**` 제거.
- `word-break: keep-all` · `text-wrap: pretty`로 한국어 줄바꿈 가독성 개선.

### 4. 에디터 진단(problems) 정리
- **cSpell**: `cspell.json` 생성 — ignorePaths(락파일·node_modules·.venv·dist·storage·requirements*.txt)
  + 도메인 사전(konetic·KEITI·Pretendard·rerank·WCAG 등).
- **TypeScript**: `tsconfig.json` `baseUrl` 제거(TS 5.6 deprecation) + `paths` 유지, `@/*` 별칭.
  `frontend/src/vite-env.d.ts` 추가 → `import "./index.css"` side-effect 타입 오류 해소.
- **CSS/Tailwind**: `.vscode/settings.json`에서 `css.lint.unknownAtRules: ignore`(Tailwind `@theme` 등),
  canonical 클래스(`w-62`·`w-85`·`h-1.25`) 적용.
- `index.html`에 Pretendard·IBM Plex Mono `<link>`(CSS `@import` 순서 경고 회피).

### 5. 백엔드 정비 (`backend/main.py`)
- **Ruff E402**: `sys.path` 조작 이후 임포트 경고 → 3rd-party(fastapi·pydantic) 임포트를 상단으로
  옮기고, `sys.path` 설정에 의존하는 `rag` 임포트만 `# noqa: E402`로 명시.
- **Pylance**: `rag/services.py`의 지연 `import chromadb`(선택적 indexing extra)에 `# type: ignore`.

### 6. 배포 아티팩트 · 실행 스크립트
- **requirements.txt 자동 생성화**: Streamlit Cloud가 uv-native pyproject/uv.lock을 의존성 소스로
  인식하지 못하므로(streamlit#9502) requirements.txt는 유지하되, 수동 미러 → `pyproject`에서
  핀 고정 생성물로 전환. 재생성: `uv pip compile --universal --no-annotate --no-header pyproject.toml -o requirements.txt`.
  (참고: streamlit 1.58은 tornado 대신 starlette/uvicorn 의존 → 전이 의존성에 포함됨.)
- **dev.sh / dev.bat**: FastAPI(:8000) + Vite(:5173)를 한 번에 실행하는 개발 스크립트.
  의존성 미설치 시 자동 설치, Ctrl-C로 두 서버 함께 종료.

### 7. 문서 갱신
- `docs/DESIGN.md`로 이동(디자인 단일 출처), README·CLAUDE에 shields.io 배지(버전 포함) 상단 추가.
- README 아키텍처에 **서비스 구성 mermaid**(React SPA → FastAPI SSE → rag 코어 공유 → OpenAI) 추가,
  기존 다이어그램에 소제목(서비스 구성 / RAG 파이프라인 / 배포) 부여.
- CLAUDE.md에 프론트엔드 섹션 · Design System 포인터 추가.

### 8. 배포 안전 · 개인정보 제거
- `rag/config.py`의 `DATA_DIR` 하드코딩 개인 경로(개인 사용자명이 박힌 Windows 절대경로) 제거 →
  `ROOT/"data"`(리포 상대). 재인덱싱은 이제 `.env`의 `RAG_DATA_DIR` 지정 필요.
  `cspell.json`에서 그 사용자명 사전 항목도 함께 제거.
- `.gitignore`에 `data/` 추가(KEITI 원본 PDF 커밋 방지). `.env.example` 정비.
- `cspell.json` ignorePaths를 `**/node_modules/**` 등으로 수정(중첩 경로 미탐 → 49,842건 오탐 해소).

### 9. 환경 자가진단 · 온보딩 (동료 로컬 이질성 대응)
- `rag/preflight.py`: storage 아티팩트·OpenAI 키·벡터 백엔드·원본데이터·프론트 node_modules를
  실측해 한국어로 "준비/조치"를 안내(런타임 준비 시 exit 0). `dev.sh`/`dev.bat`가 기동 전 호출(경고만).
- **Windows 하드닝**: 콘솔 cp949 `UnicodeEncodeError` 방지 위해 `sys.stdout.reconfigure(utf-8)` +
  `dev.bat`에 `chcp 65001`. `dev.bat`는 백엔드 새 창 + Vite.
- `docs/ONBOARDING.md`: git pull 후 처음 실행 단계별 가이드(Windows uv 설치·포트 정리·재인덱싱 포함).

### 10. CI · 문서 재편
- `.github/workflows/ci.yml`: backend(ruff + import smoke) / frontend(tsc+vite build) / spellcheck(cSpell).
  `permissions: contents:read`, uv 캐시, `--frozen`. 테스트 부재로 pytest 제외.
- `pyproject.toml`에 `[tool.ruff]`(target-version=py310) 추가 — CI 린트 결정론화.
- `docs/plan.md` + `nextsession.md` → **`docs/PLAN.md`** 단일 출처 통합(nextsession 삭제).
  .md 파일명 대문자 통일(`PLAN.md`·`LOGGING.md`).
- README: 사전 요구사항·포트/종료 표·다음작업·라이선스(KEITI 저작권) 섹션, 모듈 트리 보강, 온보딩 링크.

### 검증
- `tsc -b` 통과, `npm run build` 통과. `import backend.main` 정상(E402 수정 후 코퍼스 90문서/3332청크 로드).
- `uv run python -m rag.preflight` exit 0, `uvx ruff check .` 전체 통과, cSpell 0 issues.
- 라이브 브라우저 QA: 스트리밍·인용 칩·근거 레일·처리 상세 정상.
- 미검증(환경 제약): `dev.bat`·preflight의 실제 Windows 실행은 동료 머신에서 1회 확인 필요.
