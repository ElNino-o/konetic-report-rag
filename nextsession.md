# 다음 세션 작업 (NEXT SESSION)

## 현재 상태 (이번 세션 종료 시점)
- **배포 동작 중**: Streamlit Cloud, OpenAI 전용, memory 백엔드, 공용 키 + (권장)APP_PASSWORD.
- **인덱스**: 청킹 아티팩트 수정 + 재인덱싱 완료(3458청크). 커밋됨. 앱 정상.
- **A+C(의미분할+Contextual Retrieval)**: 모듈 `rag/indexing/semantic.py` **작성 완료, 아직 미배선**.
  - `semantic_split()` : 긴 본문을 문장 임베딩 의미거리로 분할 (kiwipiepy 문장분리)
  - `apply_semantic_split(chunks, api_key)` : body>1500자만 재분할
  - `contextualize(chunks, api_key)` : 청크별 LLM 1문장 맥락을 `c['context']`에 부여(병렬)

## 다음 세션 TODO (A+C 마무리 — 1회 재인덱싱)
1. **`rag/indexing/structure_chunker.py`**
   - 길이 상한 절단 제거: `if sum(len(x) for x in buf) > 1100: flush()` 줄 삭제(섹션 통째 유지 → 의미분할이 처리).
   - `context_text(c)` 수정: `c.get('context')`(LLM 맥락) 있으면 그걸 헤더로, 없으면 기존 제목+챕터+섹션 헤더 폴백.
     ```python
     def context_text(c):
         ctx = (c.get("context") or "").strip()
         header = ctx or _structural_header(c)   # 기존 헤더 로직을 함수로
         return f"{header}\n{c['text']}" if header else c["text"]
     ```
2. **`rag/indexing/index_pipeline.py` main()** — dedup 직전/직후에:
   ```python
   from rag.indexing import semantic
   deduped = semantic.apply_semantic_split(deduped)          # A
   retr = [c for c in deduped if c["chunk_type"] != "reference"]
   semantic.contextualize(retr)                              # B: c['context'] 채움
   build_index(deduped)
   ```
   - `build_index`/`build_openai_index` 의 `embed_input = [sc.context_text(c) ...]` 가 자동으로 LLM 맥락 사용.
   - `chunks.jsonl` 덤프에 `context` 필드 포함되는지 확인.
3. **재인덱싱**: `uv run python -m rag.indexing.index_pipeline`
   - 비용/시간: 문장 임베딩(긴 본문) + 맥락 LLM 3천여 호출(병렬 12). 일회성 ~$1–3, ~10분 예상.
4. **검증**: 새 청크 길이 분포 확인, `context` 채워졌는지, qa.answer 품질, Playwright 1회.
5. **커밋/푸시**: chunks.jsonl·reports_openai.npz·bm25_openai.pkl + 코드.

## 로깅(요청) — 확인/보강 항목
- `semantic.py` 가 이미 로깅함: `의미 분할: N개`, `맥락 생성 N/M`, `맥락 생성 완료`.
- 인덱싱 **API 비용 추정 로그** 추가 권장(맥락생성·문장임베딩 토큰 합산 → `monitoring.chat_cost/embed_cost`).
- 재인덱싱 로그를 `storage/reindex.log` 로 남기고, 실패 청크(맥락 빈 문자열) 카운트 로깅.

## 주의/함정 (재발 방지)
- `.gitignore`/정규식: **인라인 주석 금지**, `\s{2,}`는 개행도 매칭(라인 병합 사고) → 인라인 치환 금지.
- 빈 `OPENAI_BASE_URL` 환경변수는 OpenAI 클라이언트 오류 → config 에서 pop 처리됨(유지).
- 재인덱싱은 인덱싱 extra 필요: `uv sync --extra indexing` (pdfplumber/chromadb/kiwipiepy).
