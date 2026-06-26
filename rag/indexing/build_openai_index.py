"""
인덱스 재빌더 (chunks.jsonl 재사용 — 재청킹 없이 임베딩만 다시).

실행:  python build_openai_index.py
  - index_pipeline.py 가 만든 storage/chunks.jsonl 을 그대로 사용
  - reference 제외 후 OpenAI 임베딩으로 컬렉션 + BM25 + npz 재생성
  - 청킹은 그대로 두고 임베딩만 갱신할 때 유용 (index_pipeline 은 청킹+임베딩 모두 수행)
"""
from __future__ import annotations

import json

from rank_bm25 import BM25Okapi

from rag import config
from rag.indexing import structure_chunker as sc
from rag.services import embed_texts, get_chroma_collection, save_bm25, simple_tokenize
from rag.indexing.index_pipeline import META_FIELDS


def main():
    if not config.CHUNK_DUMP.exists():
        raise FileNotFoundError(
            f"{config.CHUNK_DUMP} 없음 — 먼저 python index_pipeline.py 로 청킹하세요."
        )
    all_chunks = [json.loads(line) for line in open(config.CHUNK_DUMP, encoding="utf-8")]
    retr = [c for c in all_chunks if c["chunk_type"] != "reference"]
    ids = [c["chunk_id"] for c in retr]
    docs = [c["text"] for c in retr]
    embed_input = [sc.context_text(c) for c in retr]
    metas = [{k: str(c.get(k, "")) for k in META_FIELDS} for c in retr]

    print(f"4. OpenAI 임베딩: {len(embed_input)} 청크 → {config.OPENAI_EMBED_MODEL}")
    vectors = embed_texts(embed_input)
    print(f"   차원: {len(vectors[0])}")

    print(f"5. Chroma 적재: {config.collection_name()}")
    col = get_chroma_collection()
    existing = col.get()["ids"]
    if existing:
        col.delete(ids=existing)
    B = 256
    for i in range(0, len(ids), B):
        col.add(ids=ids[i:i + B], embeddings=vectors[i:i + B],
                documents=docs[i:i + B], metadatas=metas[i:i + B])

    print(f"5. BM25 적재: {config.bm25_path().name}")
    tok = [simple_tokenize(t) for t in embed_input]
    save_bm25(BM25Okapi(tok), tok, ids)

    from rag import vector_store
    vector_store.save_npz(ids, vectors)
    print(f"5. npz 저장: {config.npz_path().name}")

    print(f"✅ OpenAI 인덱스 완료: {len(ids)} 청크")


if __name__ == "__main__":
    main()
