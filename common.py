"""
공용 리소스 로더 (임베딩 모델 · Chroma 클라이언트 · BM25 영속화).

RAGFlow 대응:
- 임베딩  ↔ rag/llm/embedding_model.py (여기선 OpenAI 임베딩 API)
- 벡터DB  ↔ rag/utils/es_conn.py (RAGFlow 는 ES/Infinity, 여기선 Chroma/numpy)
- BM25    ↔ ES 의 full-text 점수를 rank_bm25 로 대체
"""
from __future__ import annotations

import pickle
from functools import lru_cache

import config
from metering import get_logger

log = get_logger()

# chromadb 는 무겁고 memory 백엔드(클라우드)에선 불필요 → 지연 import 한다.


# ── ④ 임베딩 (OpenAI 단일) ──────────────────────────────
@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    return OpenAI(base_url=config.OPENAI_BASE_URL, api_key=config.OPENAI_API_KEY)


# 마지막 OpenAI 임베딩 호출의 토큰 수(비용 모니터링용).
LAST_EMBED_TOKENS = 0


def embed_texts(texts: list[str]) -> list[list[float]]:
    """문자열 리스트 → dense 벡터 리스트 (OpenAI 임베딩 API)."""
    global LAST_EMBED_TOKENS
    client = _openai_client()
    kwargs = {"model": config.OPENAI_EMBED_MODEL}
    if config.OPENAI_EMBED_DIM:          # 차원 축소 옵션
        kwargs["dimensions"] = config.OPENAI_EMBED_DIM
    out: list[list[float]] = []
    tokens = 0
    B = 256                               # API 배치 (토큰 한도 내)
    for i in range(0, len(texts), B):
        batch = [t.replace("\n", " ") for t in texts[i:i + B]]
        resp = client.embeddings.create(input=batch, **kwargs)
        out.extend(d.embedding for d in resp.data)
        tokens += resp.usage.total_tokens if getattr(resp, "usage", None) else 0
    LAST_EMBED_TOKENS = tokens
    log.debug("[embed] openai n=%d dim=%d tokens=%d",
              len(out), len(out[0]) if out else 0, tokens)
    return out


# ── ⑤ Chroma 클라이언트 (로컬 영속 / 원격 HTTP) ─────────
@lru_cache(maxsize=1)
def get_chroma_client():
    import chromadb

    if config.VECTOR_BACKEND == "remote":
        # C: 로컬에서 띄운 Chroma 서버에 HTTP 접속(터널 노출 시 사용)
        headers = ({"Authorization": f"Bearer {config.CHROMA_HTTP_TOKEN}"}
                   if config.CHROMA_HTTP_TOKEN else None)
        log.info("[chroma] HttpClient host=%s port=%s ssl=%s",
                 config.CHROMA_HTTP_HOST, config.CHROMA_HTTP_PORT, config.CHROMA_HTTP_SSL)
        return chromadb.HttpClient(
            host=config.CHROMA_HTTP_HOST, port=config.CHROMA_HTTP_PORT,
            ssl=config.CHROMA_HTTP_SSL, headers=headers,
        )
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    log.info("[chroma] PersistentClient path=%s", config.CHROMA_DIR)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


@lru_cache(maxsize=4)
def get_chroma_collection(name: str | None = None):
    """Chroma 컬렉션 반환/생성 (로컬 영속 또는 원격 HTTP)."""
    name = name or config.collection_name()
    col = get_chroma_client().get_or_create_collection(
        name=name, metadata={"hnsw:space": "cosine"})
    try:
        log.info("[chroma] 컬렉션 '%s' 로드: %d 벡터", name, col.count())
    except Exception as e:
        log.warning("[chroma] 컬렉션 '%s' count 실패: %s", name, e)
    return col


# ── ⑤ BM25 인덱스 영속화 (피클, 백엔드별 경로) ──────────
def save_bm25(bm25_obj, tokenized_corpus, chunk_ids):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.bm25_path(), "wb") as f:
        pickle.dump(
            {"bm25": bm25_obj, "corpus": tokenized_corpus, "ids": chunk_ids}, f
        )


def load_bm25():
    p = config.bm25_path()
    if not p.exists():
        log.warning("[bm25] 파일 없음: %s", p)
        return None
    with open(p, "rb") as f:
        store = pickle.load(f)
    log.debug("[bm25] 로드: %s (%d ids)", p.name, len(store.get("ids", [])))
    return store


# ── 간단 토크나이저 (BM25용, 한국어/영문 혼용) ──────────
def simple_tokenize(text: str) -> list[str]:
    """규칙 기반 토큰화: 공백 + 2~3gram 보강 (형태소 분석기 없이 동작)."""
    import re

    words = re.findall(r"[A-Za-z0-9]+|[가-힣]+", text.lower())
    tokens: list[str] = []
    for w in words:
        if re.match(r"[가-힣]+", w) and len(w) > 2:
            # 한글 어절은 2-gram 으로 분해해 부분 매칭률을 높인다.
            tokens.extend(w[i : i + 2] for i in range(len(w) - 1))
        else:
            tokens.append(w)
    return tokens
