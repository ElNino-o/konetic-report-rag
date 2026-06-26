"""
임베딩 백엔드 비교: BGE-M3(로컬) vs OpenAI 임베딩.

실행:  python compare_embeddings.py
  1) 두 백엔드로 같은 질의를 검색해 상위 결과를 나란히 출력
  2) 인덱싱/검색 임베딩 처리 속도(샘플) 비교

전제: 두 인덱스가 모두 빌드돼 있어야 함.
  - bge-m3 :  python index_pipeline.py                  (EMBED_BACKEND=bge-m3, 기본)
  - openai :  EMBED_BACKEND=openai python index_pipeline.py   (또는 build_openai_index.py)
"""
from __future__ import annotations

import time

import config

QUERIES = [
    "인도네시아 신재생에너지 정책의 핵심 내용은?",
    "UAE의 태양광 발전 프로젝트 현황을 알려줘",
    "중국의 탄소가격 정책은 어떻게 운영되나?",
    "일본 폐기물 정책의 주요 방향은?",
]


def _topk(backend: str, query: str, k: int = 5):
    config.EMBED_BACKEND = backend            # 런타임 백엔드 전환
    import common
    import qa_pipeline
    common.get_chroma_collection.cache_clear()
    common.get_embedder.cache_clear()
    res = qa_pipeline.hybrid_search(query, top_k=k)
    return res[:k]


def main():
    for q in QUERIES:
        print("\n" + "=" * 78)
        print("질의:", q)
        for backend in ("bge-m3", "openai"):
            t = time.time()
            try:
                rows = _topk(backend, q)
            except Exception as e:
                print(f"  [{backend}] 오류: {type(e).__name__}: {e}")
                continue
            dt = time.time() - t
            print(f"  ── {backend} (검색 {dt:.2f}s) ──")
            for i, r in enumerate(rows, 1):
                print(f"    {i}. {r['score']:.3f} | {r.get('title')} "
                      f"p.{r.get('page')} [{r.get('chunk_type')}]")


if __name__ == "__main__":
    main()
