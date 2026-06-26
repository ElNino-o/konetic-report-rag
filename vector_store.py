"""
벡터 저장소 추상화 (배포 형태 교체형).

VECTOR_BACKEND:
  - "chroma" : 로컬 영속 Chroma (개발 기본)
  - "memory" : npz(벡터) + chunks.jsonl(메타/본문) 를 메모리에 올려 numpy 코사인
               → 벡터DB 서버 불필요, Streamlit Cloud 무료티어 적합 (A안)
  - "remote" : 로컬에서 띄운 Chroma 서버에 HTTP 접속 (터널 노출, C안)

search(query_vec, top_k, where) → [{id, text, vec_sim, <metadata...>}, ...]
qa_pipeline.hybrid_search 가 이 결과에 BM25 점수를 융합한다.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

import config
from metering import get_logger

log = get_logger()


# ── memory(A) 백엔드: npz + chunks.jsonl 로드 ───────────
@lru_cache(maxsize=4)
def _load_memory():
    npz = config.npz_path()
    log.info("[memory] npz 로드 시도: %s (exists=%s)", npz, npz.exists())
    if not npz.exists():
        raise FileNotFoundError(
            f"{npz} 없음 — export_npz.py 또는 build_*_index.py 로 생성하세요."
        )
    data = np.load(npz, allow_pickle=True)
    ids = list(data["ids"])
    mat = data["vectors"].astype(np.float32)
    log.info("[memory] 로드 완료: %d 벡터 · %d차원", len(ids), mat.shape[1] if mat.ndim == 2 else -1)
    # 코사인용 정규화(이미 정규화돼 있어도 안전)
    norm = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.clip(norm, 1e-12, None)
    # 메타/본문은 chunks.jsonl 에서 id 로 결합
    meta = {}
    with open(config.CHUNK_DUMP, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            meta[c["chunk_id"]] = c
    return ids, mat, meta


def _search_memory(qv, top_k, where):
    ids, mat, meta = _load_memory()
    q = np.asarray(qv, dtype=np.float32)
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    sims = mat @ q                                   # 정규화 → 내적 = 코사인
    order = np.argsort(-sims)
    out = []
    for i in order:
        cid = ids[i]
        c = meta.get(cid, {})
        if where and any(str(c.get(k, "")) != str(v) for k, v in where.items()):
            continue
        out.append({"id": cid, "text": c.get("text", ""),
                    "vec_sim": float(sims[i]),
                    **{k: c.get(k, "") for k in _META_KEYS}})
        if len(out) >= top_k:
            break
    return out


# ── chroma / remote 백엔드 ──────────────────────────────
def _search_chroma(qv, top_k, where):
    from common import get_chroma_collection

    col = get_chroma_collection()
    w = None
    if where:
        clauses = [{k: {"$eq": str(v)}} for k, v in where.items() if v]
        w = clauses[0] if len(clauses) == 1 else ({"$and": clauses} if clauses else None)
    res = col.query(query_embeddings=[list(qv)], n_results=top_k, where=w,
                    include=["documents", "metadatas", "distances"])
    out = []
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                    res["metadatas"][0], res["distances"][0]):
        out.append({"id": cid, "text": doc, "vec_sim": 1.0 - dist, **meta})
    log.info("[search:chroma] '%s' q_dim=%d top_k=%d → %d hits",
             config.collection_name(), len(qv), top_k, len(out))
    return out


_META_KEYS = ("doc_id", "page", "country", "year", "field", "doc_source",
              "title", "tags", "chunk_type", "chapter", "section",
              "subsection", "table_title", "source_file")


def search(query_vec, top_k: int, where: dict | None = None) -> list[dict]:
    """벡터 검색 — VECTOR_BACKEND 에 따라 디스패치. vec_sim(코사인) 포함."""
    log.debug("[search] backend=%s embed=%s where=%s",
              config.VECTOR_BACKEND, config.EMBED_BACKEND, where)
    if config.VECTOR_BACKEND == "memory":
        hits = _search_memory(query_vec, top_k, where)
        log.info("[search:memory] '%s' → %d hits", config.npz_path().name, len(hits))
        return hits
    return _search_chroma(query_vec, top_k, where)   # chroma | remote 동일 인터페이스


# ── memory(A) 산출물 저장: 인덱싱 시 벡터를 npz 로 함께 저장 ──
def save_npz(ids: list[str], vectors: list[list[float]]):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(config.npz_path(),
                        ids=np.array(ids, dtype=object),
                        vectors=np.array(vectors, dtype=np.float32))
    _load_memory.cache_clear()

