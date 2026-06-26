"""
공용 리소스 로더 (임베딩 모델 · Chroma 클라이언트 · BM25 영속화).

RAGFlow 대응:
- 임베딩  ↔ rag/llm/embedding_model.py (BuiltinEmbed → BAAI/bge-m3)
- 벡터DB  ↔ rag/utils/es_conn.py (RAGFlow 는 ES/Infinity, 여기선 Chroma 로 대체)
- BM25    ↔ ES 의 full-text 점수를 rank_bm25 로 대체
"""
from __future__ import annotations

import pickle
from functools import lru_cache

import config

# chromadb 는 무겁고 memory 백엔드(클라우드)에선 불필요 → 지연 import 한다.


# ── ④ 임베딩 (백엔드 교체형) ────────────────────────────
@lru_cache(maxsize=1)
def get_embedder():
    """로컬 BGE-M3 인코더를 1회만 로드한다 (sentence-transformers)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBED_MODEL)


def _embed_bge(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    vecs = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,   # cosine 검색용 L2 정규화
        show_progress_bar=False,
    )
    return vecs.tolist()


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI

    return OpenAI(base_url=config.OPENAI_BASE_URL, api_key=config.OPENAI_API_KEY)


# 마지막 OpenAI 임베딩 호출의 토큰 수(비용 모니터링용). bge 백엔드면 0.
LAST_EMBED_TOKENS = 0


def _embed_openai(texts: list[str]) -> list[list[float]]:
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
        tokens += getattr(resp, "usage", None).total_tokens if getattr(resp, "usage", None) else 0
    LAST_EMBED_TOKENS = tokens
    return out


def _embed_bge_reset(texts):
    global LAST_EMBED_TOKENS
    LAST_EMBED_TOKENS = 0          # 로컬 임베딩은 비용 없음
    return _embed_bge(texts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """문자열 리스트 → dense 벡터 리스트. 백엔드(config.EMBED_BACKEND)별 분기."""
    if config.EMBED_BACKEND == "openai":
        return _embed_openai(texts)
    return _embed_bge_reset(texts)


# ── ③ BGE-reranker (선택, 싱글톤) ───────────────────────
@lru_cache(maxsize=1)
def get_reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANK_MODEL)


# ── ⑤ Chroma 클라이언트 (로컬 영속 / 원격 HTTP) ─────────
@lru_cache(maxsize=1)
def get_chroma_client():
    import chromadb

    if config.VECTOR_BACKEND == "remote":
        # C: 로컬에서 띄운 Chroma 서버에 HTTP 접속(터널 노출 시 사용)
        headers = ({"Authorization": f"Bearer {config.CHROMA_HTTP_TOKEN}"}
                   if config.CHROMA_HTTP_TOKEN else None)
        return chromadb.HttpClient(
            host=config.CHROMA_HTTP_HOST, port=config.CHROMA_HTTP_PORT,
            ssl=config.CHROMA_HTTP_SSL, headers=headers,
        )
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


@lru_cache(maxsize=4)
def get_chroma_collection(name: str | None = None):
    """Chroma 컬렉션 반환/생성 (로컬 영속 또는 원격 HTTP)."""
    return get_chroma_client().get_or_create_collection(
        name=name or config.collection_name(),
        metadata={"hnsw:space": "cosine"},
    )


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
        return None
    with open(p, "rb") as f:
        return pickle.load(f)


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
