"""
이미 빌드된 Chroma 컬렉션에서 벡터를 추출해 npz 로 저장 (재임베딩 없음).

실행:  python export_npz.py

→ storage/<collection>.npz 생성 → VECTOR_BACKEND=memory(A안)·배포에서 사용.
"""
from __future__ import annotations

import numpy as np

import config
import vector_store
from common import get_chroma_collection


def main():
    col = get_chroma_collection()
    got = col.get(include=["embeddings"])
    ids = got["ids"]
    vecs = got["embeddings"]
    if ids is None or len(ids) == 0 or vecs is None or len(vecs) == 0:
        raise SystemExit(f"컬렉션 '{config.collection_name()}' 이 비어 있습니다.")
    vector_store.save_npz(ids, [list(v) for v in vecs])
    arr = np.array(vecs)
    print(f"✅ npz 저장: {config.npz_path()}  ({len(ids)}벡터 · {arr.shape[1]}차원)")


if __name__ == "__main__":
    main()
