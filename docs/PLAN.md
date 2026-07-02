# 프로젝트 로드맵 (PLAN)

코네틱 보고서 RAG — OpenAI 전용, Streamlit Cloud + React/FastAPI(PoC).
상세 아키텍처·배포는 [../README.md](../README.md), 세션별 변경 로그는 [LOGGING.md](LOGGING.md).

> 이 파일은 로드맵(완료·다음·백로그)과 다음 세션 인수인계(현재 상태·주의·시작 프롬프트)를
> 하나로 합친 단일 출처다. 세션 종료 시 여기 "현재 상태"와 "다음"을 갱신한다.

---

## 완료

### RAG 코어 · 인덱싱
- [x] 구조 인식 청킹(KEITI 보고서) — 챕터/섹션/표/인터뷰/각주
- [x] 하이브리드 검색(벡터+BM25) + 리랭킹(off/openai LLM)
- [x] OpenAI 전용화(임베딩/리랭크/LLM), bge·torch 제거
- [x] 벡터 저장소 교체형(chroma/memory/remote) + chromadb 미설치 자동 memory 폴백
- [x] 토큰/비용 모니터링(서버 로그 + UI)
- [x] 패키지 구조화(`rag/`, `rag/indexing/`), uv/pyproject + cloud requirements.txt
- [x] BYOK + 공용 키 모드(공용 키 시 입력칸 숨김) + APP_PASSWORD 게이트(Streamlit)
- [x] 두 모드: KEITI 고정 코퍼스 / 내 문서 업로드(세션 임시)
- [x] 청킹 아티팩트 수정(쪽번호/표 빈셀/중복/파편) + 재인덱싱
- [x] **A+C 맥락 단위 청킹**: 의미 분할(semantic_split) + Contextual Retrieval(LLM 1문장 맥락)
      배선·재인덱싱 완료. 길이상한 절단 제거 → 섹션 통째 유지 후 의미 경계 분할,
      `context_text`가 LLM 맥락(`c['context']`) 우선 사용
- [x] 인덱싱 API 비용 합산 로깅(`monitoring.INDEX_COST`) + 빈맥락 청크 카운트
- [x] 빈맥락 원인규명(429 레이트리밋)·해결: max_completion_tokens 512, reasoning_effort=low,
      백오프 재시도, 동시성 12→6, 2차 보충 패스

### 프론트엔드 · 백엔드 · 배포
- [x] Streamlit Cloud 배포(공용 키, memory)
- [x] UI 정리(Streamlit): 내부 단계번호 제거, 사이드바 상태·세션비용 가독성/즉시갱신
- [x] 우측 패널 개편: 질문 후 '관련 문서' 표시 → 선택 시 전체화면(로컬 PDF 임베드 /
      배포는 문서 전문 텍스트 / 항상 코네틱 원문 검색 링크)
- [x] FastAPI 백엔드(`backend/main.py`): `rag/` 코어를 REST + SSE로 노출(얇은 어댑터)
- [x] 답변 형태 3종(요약/일반/전문가) + 스트리밍 응답
- [x] **React 프론트 재설계**(Tailwind v4 + shadcn/ui, 팔레트 C, Information Altitude,
      1급 인용 칩·근거 레일·문서 뷰어) + 로직/프레젠테이션 모듈화 — 상세 [LOGGING.md](LOGGING.md) 2026-07-02
- [x] 한국어 마크다운 렌더 버그 수정(`~` 취소선·조사 뒤 `**굵게**`)
- [x] 에디터 진단 정리(cSpell/TS/CSS/Tailwind), `vite-env.d.ts`
- [x] 백엔드 Ruff E402 정리, `chromadb` 지연 임포트 `# type: ignore`
- [x] requirements.txt를 pyproject에서 핀 고정 자동 생성으로 전환(수동 미러 폐기)
- [x] 개발 실행 스크립트 `dev.sh` / `dev.bat`(FastAPI + Vite 동시 기동)

---

## 진행 중 / 다음

### RAG 품질 튜닝 (선택)
- [ ] 표(table)·요약(summary)도 의미분할 대상 포함 검토: 현재 `apply_semantic_split`은 `body`만
      분할 → 1500자 초과 91건 중 일부 비-body 큰 청크 존재
- [ ] 변경 시 1회 재인덱싱 → `qa.answer` + Playwright 검증 → 커밋·푸시

### React/FastAPI 운영화
- [ ] **FastAPI 인증 게이트 부재**: `app.py`엔 `APP_PASSWORD` 게이트가 있으나 백엔드엔 없음.
      공개 배포 시 공용 키 남용 방지 게이트(헤더/미들웨어) 필요. 현재 CORS는 localhost 전용
- [ ] React+FastAPI 운영 배포: `npm run build` → `frontend/dist/`를 FastAPI StaticFiles로 서빙하거나
      정적 호스팅 + `/api` 프록시([REACT_FASTAPI.md](REACT_FASTAPI.md))
- [ ] 다중 동시 사용자 지원 시 `qa_pipeline`의 `LAST_*_USAGE` 모듈 전역 → 요청 로컬로 리팩터
      (현재는 `_QUERY_LOCK`으로 질의 1건 직렬화 — 저트래픽 가정)

---

## 백로그 (우선순위 낮음)
- [ ] 크로스-페이지 섹션 병합(현재 페이지 경계에서 본문이 끊김)
- [ ] 표 추출 품질 향상(행라벨 열 누락 케이스), table_title↔table 매칭 정확화
- [ ] 부모-자식(small-to-big) 검색 옵션
- [ ] 한국어 BM25 토크나이저 고도화(형태소 기반)
- [ ] gpt-5.4-nano 실단가 반영(config.PRICES) / OpenAI 사용 한도 설정
- [ ] 평가셋(질문-정답)으로 검색/답변 품질 정량 측정(회귀 방지)

---

## 현재 상태 (최근 세션 종료 시점)

- **배포 동작 중**: Streamlit Cloud, OpenAI 전용, memory 백엔드, 공용 키 + (권장)APP_PASSWORD.
- **React+FastAPI 버전**: 재설계·모듈화 완료. 로컬 `dev.sh`/`dev.bat`로 기동(:5173 → /api :8000).
- **코퍼스**: 90문서 / **3332청크** / 검색대상 3191 / context 채움 91.8%(2929).
  인덱싱 추정비용 $0.247. 로그: `storage/reindex.log`.
- **빈맥락 원인·해결(완료)**: 추론토큰 소진이 아니라 **OpenAI 429 레이트리밋**이었음
  (RPM 500 초과 135건 + TPM 200k 초과 127건). 조치: `max_completion_tokens` 80→512,
  `reasoning_effort=low`, 429 점증 백오프(`CTX_MAX_RETRIES=6`), 동시성 12→6, 2차 보충 패스.
  참고: `max_completion_tokens`는 Chat Completions에서 gpt-5 계열의 공식 파라미터(추론+출력 합산 상한).

---

## 주의 / 함정 (재발 방지)

- `.gitignore`/정규식: **인라인 주석 금지**, `\s{2,}`는 개행도 매칭(라인 병합 사고) → 인라인 치환 금지.
- 빈 `OPENAI_BASE_URL` 환경변수는 OpenAI 클라이언트 오류 → config에서 pop 처리됨(유지).
- 재인덱싱은 인덱싱 extra 필요: `uv sync --extra indexing`(pdfplumber/chromadb/kiwipiepy).
- `requirements.txt`는 **자동 생성물**(직접 편집 금지). pyproject 의존성 변경 시 재생성:
  `uv pip compile --universal --no-annotate --no-header pyproject.toml -o requirements.txt`.
- `rag/` 코어를 바꿀 때 두 프론트엔드(Streamlit/React) 양쪽 영향 확인.

---

## 운영 메모
- 비용 관리: OpenAI 대시보드 월 한도 설정 권장.
- 공개 URL은 APP_PASSWORD 필수(공용 키 남용 방지). React/FastAPI는 아직 게이트 미구현(위 "다음" 참조).

---

## 다음 세션 시작 프롬프트 (그대로 붙여넣기)

```
코네틱 보고서 RAG 프로젝트(OpenAI 전용, GitHub: ElNino-o/konetic-report-rag)를 이어서 작업한다.
docs/PLAN.md 를 먼저 읽어 현재 상태·다음 작업을 파악해라(로드맵과 인수인계가 이 한 파일에 통합됨).

RAG 코어(A+C 맥락 청킹)와 React 프론트 재설계는 완료 상태다.
다음 후보(PLAN.md "진행 중 / 다음" 참조):
 1) RAG 품질 튜닝: 표/요약도 의미분할 포함 검토(현재 body만, 1500자 초과 91건)
 2) React/FastAPI 운영화: FastAPI 인증 게이트, 정적 빌드 서빙/프록시 배포
 변경 시 재인덱싱 or 빌드 → qa.answer/Playwright 검증 → 커밋·푸시

주의: .gitignore/정규식 인라인 주석 금지, \s{2,} 개행 매칭 주의(과거 사고).
requirements.txt 는 자동 생성물(uv pip compile) — 직접 편집 금지.
작업 전 uv sync --extra indexing 로 의존성 설치 확인. 개발 서버는 ./dev.sh.
```
