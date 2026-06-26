# 배포 가이드 (Streamlit Cloud)

런타임은 **OpenAI API**(임베딩·리랭크·LLM)만 쓰므로 클라우드에 무거운 로컬 모델이
필요 없습니다. 남는 것은 **벡터를 어디서 읽느냐** 뿐이며, 두 방식을 지원합니다.

```
[오프라인·로컬 1회] PDF → 구조청킹 → OpenAI 임베딩 → 인덱스 산출물(npz/bm25/chunks)
[Streamlit Cloud]  질문 → OpenAI 임베딩 → 벡터검색(memory|remote) → OpenAI 리랭크 → OpenAI LLM
```

벡터 저장소 선택은 환경변수/시크릿 `VECTOR_BACKEND` 로 한다.

## 의존성 (uv / pyproject.toml)
- **로컬**: `uv sync --extra indexing` (런타임 + 파싱/Chroma) → `uv run ...`
- **Streamlit Cloud**: uv-네이티브 pyproject 를 직접 못 읽으므로 **`requirements.txt`**(런타임 슬림)를 사용.
  `requirements.txt` 는 `pyproject.toml [project.dependencies]` 의 미러다.

---

## A안 (권장) — 인메모리 numpy (`VECTOR_BACKEND=memory`)

서버 불필요. 임베딩을 npz 파일로 앱에 포함해 메모리에서 코사인 검색.
이 데이터 규모(≈3,265청크)에 최적이며 Streamlit Cloud 무료티어에 맞는다.

### 1) 로컬에서 인덱스 산출물 만들기 — **단일 명령**
```bash
uv sync --extra indexing
uv run python -m rag.indexing.index_pipeline
```
이 한 번으로 **청킹 + OpenAI 임베딩 + 적재**가 끝나고 아래가 생성된다:
`storage/chunks.jsonl`, `storage/reports_openai.npz`, `storage/bm25_openai.pkl` (+ 로컬 Chroma)
→ 앞 3개는 `.gitignore` 에서 제외되어 **커밋 대상**(합쳐 ~38MB).
> 청킹은 그대로 두고 임베딩만 다시 만들려면: `uv run python -m rag.indexing.build_openai_index`
> 이미 Chroma 만 있고 npz 만 필요하면: `uv run python -m rag.indexing.export_npz`

### 2) 배포
- GitHub 에 푸시 (위 3개 산출물 포함)
- Streamlit Cloud → New app → 리포 선택 → **Main file: `app.py`**
- **Advanced settings → Python requirements: `requirements.txt`** (기본값)
- **Secrets** 에 `.streamlit/secrets.toml.example` 내용을 채워 붙여넣기
  (`OPENAI_API_KEY`, `VECTOR_BACKEND="memory"`, `RERANK_BACKEND="openai"`)

### 로컬에서 클라우드와 동일 구성 확인
```bash
VECTOR_BACKEND=memory uv run streamlit run app.py
```

---

## C안 — 로컬 Chroma 서버 + 터널 (`VECTOR_BACKEND=remote`)

벡터를 로컬 Chroma 서버에 두고 Streamlit Cloud가 인터넷으로 접속.
데이터가 커서 npz가 부담될 때 사용. (PC·터널이 항상 켜져 있어야 함)

### 1) 로컬에서 Chroma 서버 실행
```bash
chroma run --host 0.0.0.0 --port 8000 --path storage/chroma
```
(인덱스는 `uv run python -m rag.indexing.index_pipeline` 로 `reports_openai` 컬렉션에 적재돼 있어야 함)

### 2) 터널로 외부 노출 (둘 중 하나)
```bash
cloudflared tunnel --url http://localhost:8000      # 무료, https URL 발급
# 또는  ngrok http 8000
```

### 3) Streamlit Cloud Secrets
```toml
VECTOR_BACKEND = "remote"
CHROMA_HTTP_HOST = "<터널-호스트>"   # 예: xxxx.trycloudflare.com
CHROMA_HTTP_PORT = "443"
CHROMA_HTTP_SSL  = "true"
OPENAI_API_KEY = "sk-..."
RERANK_BACKEND = "openai"
```
이 경우 cloud 에서 `chromadb` 가 필요하므로 `requirements.txt` 에 `chromadb>=0.5` 를 추가한다.

> ⚠️ C안은 로컬 PC·터널이 항상 켜져 있어야 하고 보안 노출이 생긴다.
> 상시 서비스라면 관리형 벡터DB(Qdrant/Pinecone) 전환을 권장.

---

## 로컬 개발 기본값 (`VECTOR_BACKEND=chroma`)
`.env` 의 값으로 동작하며, 로컬 영속 Chroma 를 사용한다. 임베딩/리랭크/LLM 은 모두 OpenAI.
