"""
Colab 임베딩용 입력 내보내기 (GPU 오프로딩 1/3 단계).

무거운 bge-m3 인코딩만 Colab GPU 로 떼어내기 위한 입력 파일을 만든다.
- storage/chunks.jsonl 을 읽어 reference 청크를 제외
- 각 청크의 임베딩 입력 텍스트(context_text)만 추출
- storage/embed_input.jsonl 로 저장 → Colab 에 업로드

출력 한 줄: {"chunk_id": "...", "text": "<헤더+본문>"}
실행:  python export_for_colab.py
"""
from __future__ import annotations

import json

import config
import structure_chunker as sc

OUT = config.STORAGE_DIR / "embed_input.jsonl"


def main():
    if not config.CHUNK_DUMP.exists():
        raise FileNotFoundError(
            f"{config.CHUNK_DUMP} 없음 — 먼저 python index_pipeline.py 로 청킹하세요."
        )
    all_chunks = [json.loads(l) for l in open(config.CHUNK_DUMP, encoding="utf-8")]
    retr = [c for c in all_chunks if c["chunk_type"] != "reference"]

    with open(OUT, "w", encoding="utf-8") as f:
        for c in retr:
            row = {"chunk_id": c["chunk_id"], "text": sc.context_text(c)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"✅ 내보내기 완료: {len(retr)} 청크 → {OUT}")
    print("   이 파일을 Colab 에 업로드한 뒤 노트북에서 bge-m3 인코딩하세요.")


if __name__ == "__main__":
    main()
