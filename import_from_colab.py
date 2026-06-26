"""
Colab 임베딩 결과 적재 (GPU 오프로딩 3/3 단계).

Colab 에서 내려받은 embeddings_bge.npz 를 로컬 Chroma + BM25 인덱스로 적재한다.
GPU 없이 동작 (단순 삽입). build_openai_index.py 의 bge-m3 GPU 버전.

전제:
  1) python export_for_colab.py 로 embed_input.jsonl 생성 → Colab 업로드
  2) Colab 노트북에서 bge-m3 인코딩 → embeddings_bge.npz 다운로드
  3) 그 파일을 storage/ 에 둔 뒤 이 스크립트 실행

embeddings_bge.npz 포맷:  ids(str 배열) · vectors(float32 [N,1024])
실행:  python import_from_colab.py
"""
from __future__ import annotations

import json

import numpy as np
from rank_bm25 import BM25Okapi

import config
import structure_chunker as sc
from common import get_chroma_collection, save_bm25, simple_tokenize
from index_pipeline import META_FIELDS

config.EMBED_BACKEND = "bge-m3"   # bge-m3 인덱스(reports/bm25.pkl)에 적재
NPZ = config.STORAGE_DIR / "embeddings_bge.npz"


def main():
    if not NPZ.exists():
        raise FileNotFoundError(f"{NPZ} 없음 — Colab 결과를 storage/ 에 두세요.")
    if not config.CHUNK_DUMP.exists():
        raise FileNotFoundError(f"{config.CHUNK_DUMP} 없음 — index_pipeline.py 먼저.")

    data = np.load(NPZ, allow_pickle=True)
    vec_ids = [str(x) for x in data["ids"]]
    vectors = data["vectors"].astype("float32")
    id2vec = {cid: v for cid, v in zip(vec_ids, vectors)}
    print(f"① npz 로드: {len(vec_ids)} 벡터 · 차원 {vectors.shape[1]}")

    # chunks.jsonl 에서 문서/메타 복원 (Colab 은 텍스트만 받았으므로)
    all_chunks = [json.loads(l) for l in open(config.CHUNK_DUMP, encoding="utf-8")]
    retr = [c for c in all_chunks if c["chunk_type"] != "reference"]

    missing = [c["chunk_id"] for c in retr if c["chunk_id"] not in id2vec]
    if missing:
        raise ValueError(f"벡터 누락 {len(missing)}건 (예: {missing[:3]}) — export/Colab 재실행 필요")

    ids = [c["chunk_id"] for c in retr]
    docs = [c["text"] for c in retr]
    embed_input = [sc.context_text(c) for c in retr]
    metas = [{k: str(c.get(k, "")) for k in META_FIELDS} for c in retr]
    embs = [id2vec[cid].tolist() for cid in ids]

    print(f"② Chroma 적재: {config.collection_name()}")
    col = get_chroma_collection()
    existing = col.get()["ids"]
    if existing:
        col.delete(ids=existing)
    B = 256
    for i in range(0, len(ids), B):
        col.add(ids=ids[i:i + B], embeddings=embs[i:i + B],
                documents=docs[i:i + B], metadatas=metas[i:i + B])

    print(f"③ BM25 적재: {config.bm25_path().name}")
    tok = [simple_tokenize(t) for t in embed_input]
    save_bm25(BM25Okapi(tok), tok, ids)

    print(f"✅ bge-m3 인덱스(GPU 오프로딩) 완료: {len(ids)} 청크")


if __name__ == "__main__":
    main()
