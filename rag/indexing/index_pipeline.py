"""
1. 데이터 인덱싱 파이프라인 (오프라인) — 구조 인식 청킹 버전

실행:  python index_pipeline.py

흐름:
  1. 메타데이터(엑셀) 읽기 + PDF 매핑            (load_metadata)
  2.3. 구조 인식 파싱·청킹                         (structure_chunker)
  4. 임베딩 생성 (OpenAI, 컨텍스트 헤더 결합)
  5. 벡터DB 적재 (Chroma + BM25, 드라이브 영속화)

RAGFlow 대응: rag/flow/pipeline.py 의 File→Parser→Chunker→Tokenizer 를
              외부 인프라 없이 로컬로 재구성. 청킹은 보고서 구조를 인식한다.
"""
from __future__ import annotations

import json
import re

import pandas as pd
from rank_bm25 import BM25Okapi

from rag import config
from rag.indexing import structure_chunker as sc
from rag.services import embed_texts, get_chroma_collection, save_bm25, simple_tokenize


# ════════════════════════════════════════════════════════
# 1. 메타데이터 읽기 · PDF 연결
#    report_list.xlsx 의 두 시트(국가별/정책규제)를 읽어
#    국가·분야·제목·내용·태그를 가져오고, 파일명을 키로
#    country_report/policy_report 안의 PDF 와 매핑한다.
# ════════════════════════════════════════════════════════
def _build_pdf_index() -> dict:
    idx = {}
    for d in config.pdf_dirs():
        if not d.exists():
            print(f"  [경고] PDF 폴더 없음: {d}")
            continue
        for p in d.glob("*.pdf"):
            idx[p.name] = p
    return idx


def _derive_year(filename: str) -> str:
    m = re.search(r"\((\d{2})[A-Z]", filename)
    return f"20{m.group(1)}" if m else ""


def _doc_id(filename: str, fallback: int) -> str:
    """청크 id 접두사용 짧은 문서 식별자. 보고서 코드(25AR-01)가 있으면 사용."""
    m = re.search(r"\((\d{2}[A-Z]{2}-\d+)\)", filename)
    return m.group(1) if m else f"doc{fallback:03d}"


def load_metadata() -> dict[str, dict]:
    if not config.METADATA_XLSX.exists():
        raise FileNotFoundError(f"메타데이터 엑셀이 없습니다: {config.METADATA_XLSX}")

    pdf_index = _build_pdf_index()
    print(f"1. PDF 파일 {len(pdf_index)}건 발견")

    xl = pd.ExcelFile(config.METADATA_XLSX)
    meta_by_file: dict[str, dict] = {}
    missing = 0
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet, dtype=str).fillna("")
        for _, row in df.iterrows():
            fname = str(row.get(config.META_KEY_COLUMN, "")).strip()
            if not fname or fname not in pdf_index:
                missing += 1 if fname else 0
                continue
            meta_by_file[fname] = {
                "pdf_filename": fname,
                "pdf_path": str(pdf_index[fname]),
                "country": row.get(config.META_COLUMNS["country"], ""),
                "field": row.get(config.META_COLUMNS["field"], ""),
                "title": (row.get(config.META_COLUMNS["title"], "") or fname),
                "summary": row.get(config.META_COLUMNS["summary"], ""),
                "tags": row.get(config.META_COLUMNS["tags"], ""),
                "year": _derive_year(fname),
                "source": sheet,
            }
    if missing:
        print(f"  [경고] 엑셀에 있으나 PDF 미발견: {missing}건")
    print(f"1. 메타데이터 {len(meta_by_file)}건 ↔ PDF 매핑 완료")
    return meta_by_file


# Chroma 메타데이터로 저장할 스칼라 필드 (footnotes 같은 리스트는 제외)
META_FIELDS = (
    "doc_id", "page", "country", "year", "field", "doc_source", "title",
    "tags", "chunk_type", "chapter", "section", "subsection", "table_title",
    "source_file",
)


# ════════════════════════════════════════════════════════
# 4. 임베딩  +  5. 벡터DB·BM25 적재 (영속화)
#    - reference(출처/참고문헌) 타입은 검색 노이즈라 인덱스에서 제외
#      (단, chunks.jsonl 에는 전부 저장 → UI 우측 PDF 본문 표시용)
#    - 임베딩/BM25 입력은 context_text(제목·구조 헤더 + 본문)
# ════════════════════════════════════════════════════════
def build_index(all_chunks: list[dict]):
    # 5.-c 청크 원문 전체 백업 (UI 표시용 — reference 포함)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.CHUNK_DUMP, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # 검색 대상: reference 제외
    retr = [c for c in all_chunks if c["chunk_type"] != "reference"]
    ids = [c["chunk_id"] for c in retr]
    documents = [c["text"] for c in retr]                       # 원문(표시·LLM용)
    embed_input = [sc.context_text(c) for c in retr]            # 컨텍스트 헤더 결합
    metadatas = [{k: str(c.get(k, "")) for k in META_FIELDS} for c in retr]

    # ── 4. 임베딩 생성 (OpenAI) ──
    print(f"4. 임베딩 생성: {len(embed_input)} 청크(reference 제외) → OpenAI {config.OPENAI_EMBED_MODEL}")
    vectors = embed_texts(embed_input)

    # ── 5.-a Chroma 적재 ──
    print("5. Chroma 적재 중...")
    col = get_chroma_collection()
    existing = col.get()["ids"]
    if existing:
        col.delete(ids=existing)
    B = 256
    for i in range(0, len(ids), B):
        col.add(
            ids=ids[i:i + B],
            embeddings=vectors[i:i + B],
            documents=documents[i:i + B],
            metadatas=metadatas[i:i + B],
        )

    # ── 5.-b BM25 적재 (컨텍스트 헤더 포함 토큰) ──
    print("5. BM25 인덱스 생성 중...")
    tokenized = [simple_tokenize(t) for t in embed_input]
    save_bm25(BM25Okapi(tokenized), tokenized, ids)

    # ── 5.-c 인메모리(numpy) 백엔드용 npz 저장 (배포 A안) ──
    from rag import vector_store
    vector_store.save_npz(ids, vectors)
    print(f"5. npz 저장: {config.npz_path().name}")

    print(f"✅ 인덱싱 완료: 검색 {len(ids)}청크 / 전체 {len(all_chunks)}청크 → {config.STORAGE_DIR}")


# ════════════════════════════════════════════════════════
# 오케스트레이터: 1. → 2.3. → 4.5.
# ════════════════════════════════════════════════════════
def main():
    meta_by_file = load_metadata()
    all_chunks: list[dict] = []
    for i, (fname, meta) in enumerate(meta_by_file.items(), 1):
        doc_id = _doc_id(fname, i)
        print(f"구조 청킹 [{i}/{len(meta_by_file)}] {doc_id}: {fname}")
        try:
            chunks = sc.parse_and_chunk(meta["pdf_path"], meta, doc_id)
        except Exception as e:
            print(f"   [청킹 오류] {type(e).__name__}: {e}")
            chunks = []
        # 본문 추출이 빈약하면(스캔본 등) 엑셀 '내용'을 폴백 청크로
        if not chunks and meta.get("summary"):
            chunks = [{
                "chunk_id": f"{doc_id}_c0000", "doc_id": doc_id,
                "source_file": fname, "title": meta["title"],
                "country": meta["country"], "year": meta["year"],
                "field": meta["field"], "doc_source": meta["source"],
                "tags": meta["tags"], "text": sc._clean(meta["summary"]),
                "page": 1, "chunk_type": "summary", "chapter": "요약",
                "section": "", "subsection": "", "table_title": "",
                "caption_source": "", "footnotes": [],
            }]
        all_chunks.extend(chunks)
        print(f"   → {len(chunks)} 청크")
    if not all_chunks:
        print("처리할 청크가 없습니다. data 구성을 확인하세요.")
        return
    # 완전중복 본문 제거(첫 등장 유지) — 임베딩 비용·노이즈 절감
    seen, deduped = set(), []
    for c in all_chunks:
        if c["text"] in seen:
            continue
        seen.add(c["text"])
        deduped.append(c)
    if len(deduped) < len(all_chunks):
        print(f"   중복 제거: {len(all_chunks)} → {len(deduped)} 청크")
    build_index(deduped)


if __name__ == "__main__":
    main()
