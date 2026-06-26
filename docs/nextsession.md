# 다음 세션 작업 (NEXT SESSION)

## 현재 상태 (이번 세션 종료 시점)
- **배포 동작 중**: Streamlit Cloud, OpenAI 전용, memory 백엔드, 공용 키 + (권장)APP_PASSWORD.
- **A+C(의미분할+Contextual Retrieval) 완료·재인덱싱 완료**:
  - 길이상한(1100자) 절단 제거 → 섹션 통째 유지 후 `semantic.apply_semantic_split`이 의미 경계로 분할.
  - `context_text`가 LLM 맥락(`c['context']`) 우선, 없으면 `_structural_header` 폴백.
  - `index_pipeline.main`에 `apply_semantic_split`(A) → `contextualize`(C) → `build_index` 배선.
  - 인덱싱 비용 누적기 `monitoring.INDEX_COST`(임베딩+맥락LLM 토큰/USD) + 빈맥락 카운트 로깅.
- **재인덱싱 결과(2026-06-26)**: 전체 **3332청크** / 검색대상 **3191** / **context 채움 91.8%**(2929) /
  본문길이 p50=312·p90=769·평균408·max2294 / 인덱싱 추정비용 **$0.247**. 로그: `storage/reindex.log`.
- **검증 완료**: `qa.answer`(폴란드 이차전지) 정상 인용·13.99s·$0.00067, Playwright UI 통과(단계번호 누출 없음).
- **UI 정리**: 내부 단계번호(1.질문/4.답변) 제거 → `✍️ 질문`/`💬 답변`, 사이드바 상태 2열 + 세션비용
  placeholder 즉시 갱신(한 박자 지연 해소).

## 빈맥락 원인 규명 + 해결 (완료)
- **실제 원인**: 추론토큰 소진(빈 응답)이 아니라 **OpenAI 429 레이트리밋**이었음.
  `reindex.log` 분석 결과 빈맥락 262건 = 429 (RPM 500 초과 135건 + TPM 200k 초과 127건).
  12워커가 한도를 지속 초과 → 클라이언트 기본 재시도(2회)로도 회복 실패.
- **조치**(`semantic._ctx_one`/`contextualize`, `config`):
  - `max_completion_tokens` 80→**512**(추론+출력 합산 상한 넉넉히, `config.CTX_MAX_TOKENS`).
  - **추론강도 `reasoning_effort=low`**(단순 1문장 작업) — 미지원 모델이면 자동 폴백.
  - **429 점증 백오프 재시도**(`CTX_MAX_RETRIES=6`) + **동시성 12→6**(`CTX_WORKERS`)로 한도 회피.
  - **2차 보충 패스**: 1차 후 남은 빈맥락만 동시성 2로 재시도 → 누락 0 지향.
- 참고: `max_completion_tokens`는 Chat Completions API에서 gpt-5 계열(추론형)의 공식 파라미터가 맞음
  (Responses API라면 `max_output_tokens`). 추론토큰+출력토큰 합산 상한이라 작으면 빈 응답 위험.

## 다음 세션 TODO (품질 튜닝 — 선택)
1. **표(table)·요약(summary)도 의미분할 대상에 포함 검토**: 현재 `apply_semantic_split`은 `body`만 분할
   → 1500자 초과 91건 중 일부 비-body 큰 청크 존재.
2. (백로그는 `plan.md` 참조: 크로스페이지 병합, 부모-자식 검색, 형태소 BM25, 평가셋 등)

## 주의/함정 (재발 방지)
- `.gitignore`/정규식: **인라인 주석 금지**, `\s{2,}`는 개행도 매칭(라인 병합 사고) → 인라인 치환 금지.
- 빈 `OPENAI_BASE_URL` 환경변수는 OpenAI 클라이언트 오류 → config 에서 pop 처리됨(유지).
- 재인덱싱은 인덱싱 extra 필요: `uv sync --extra indexing` (pdfplumber/chromadb/kiwipiepy).

---

## 다음 세션 시작 프롬프트 (그대로 붙여넣기)

```
rag_prototype 프로젝트(코네틱 보고서 RAG, OpenAI 전용, GitHub: ElNino-o/konetic-report-rag)
이어서 작업한다. docs/nextsession.md 와 docs/plan.md 를 먼저 읽어 현재 상태를 파악해라.

A+C 맥락 단위 청킹 완료. 빈맥락 원인은 429 레이트리밋으로 규명·해결됨
(max_completion_tokens 512, reasoning_effort=low, 백오프 재시도, 워커6, 2차 보충).
이번엔 품질 튜닝을 진행한다(nextsession.md "다음 세션 TODO" 참조):
 1) 표/요약도 의미분할 대상 포함 검토(현재 body만 분할, 1500자 초과 91건)
 2) 변경 시 1회 재인덱싱 → qa.answer + Playwright 검증 → 커밋·푸시

주의: .gitignore/정규식 인라인 주석 금지, \s{2,} 개행 매칭 사고 주의(둘 다 과거 사고).
작업 전 uv sync --extra indexing 로 의존성(kiwipiepy 등) 설치 확인.
재인덱싱 로그는 storage/reindex.log, 인덱싱 비용은 monitoring.INDEX_COST 로 합산된다.
```
