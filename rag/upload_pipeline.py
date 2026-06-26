"""
업로드 문서 파이프라인 (세션 임시, 외부 DB 불필요).

사용자가 Streamlit 에서 올린 PDF 를 런타임에 처리한다:
  파싱(PyMuPDF) → 일반 청킹(문단) → OpenAI 임베딩(BYOK 키) → 세션 numpy 인덱스
검색은 numpy 코사인. 결과는 qa_pipeline.answer(candidates=...) 로 재사용한다.

고정 코퍼스용 structure_chunker 와 달리, 임의 PDF 에 맞춘 '일반 청커'를 쓴다.
"""
from __future__ import annotations

import re

import numpy as np

from rag import services as common

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(s: str) -> str:
    s = (s or "").replace("\x00", "")
    s = _CTRL.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ── 2. 파싱 (PyMuPDF, bytes 입력) ─────────────────────────
def parse_pdf_bytes(data: bytes) -> list[tuple[int, str]]:
    import fitz  # PyMuPDF

    pages: list[tuple[int, str]] = []
    doc = fitz.open(stream=data, filetype="pdf")
    for i in range(len(doc)):
        pages.append((i + 1, _clean(doc[i].get_text("text"))))
    doc.close()
    return pages


# ── 3. 일반 청킹 (문단 누적, 구조 가정 없음) ──────────────
def chunk_pages(pages, filename: str, target_chars=900, overlap=120) -> list[dict]:
    chunks: list[dict] = []
    idx = 0

    def add(text, page):
        nonlocal idx
        text = text.strip()
        if len(text) < 30:
            return
        chunks.append({
            "chunk_id": f"{filename}__c{idx:04d}", "source_file": filename,
            "title": filename, "page": page, "chunk_type": "body",
            "chapter": "", "section": "", "subsection": "",
            "country": "", "year": "", "field": "", "doc_source": "업로드",
            "tags": "", "table_title": "", "caption_source": "", "footnotes": [],
            "text": text,
        })
        idx += 1

    for page, text in pages:
        buf = ""
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) > target_chars:
                add(buf, page)
                buf = buf[-overlap:]                 # 중첩 꼬리
            buf += ("\n" if buf else "") + para
        add(buf, page)
    return chunks


# ── 2.3.4. 업로드 1건 → 청크 + 임베딩 행렬 ─────────────────
def process_files(files, api_key: str) -> dict:
    """files: Streamlit UploadedFile 리스트 → {'chunks':[...], 'mat': np.ndarray(정규화)}"""
    all_chunks: list[dict] = []
    for f in files:
        data = f.read() if hasattr(f, "read") else f
        name = getattr(f, "name", "uploaded.pdf")
        all_chunks.extend(chunk_pages(parse_pdf_bytes(data), name))
    if not all_chunks:
        return {"chunks": [], "mat": np.zeros((0, 1), dtype=np.float32)}
    vecs = common.embed_texts([c["text"] for c in all_chunks], api_key=api_key)
    mat = np.asarray(vecs, dtype=np.float32)
    mat /= np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12, None)
    return {"chunks": all_chunks, "mat": mat}


# ── 6. 세션 인덱스 검색 (numpy 코사인) ────────────────────
def search(query: str, index: dict, api_key: str, top_k: int = 20) -> list[dict]:
    chunks, mat = index.get("chunks", []), index.get("mat")
    if not chunks or mat is None or len(chunks) == 0:
        return []
    qv = np.asarray(common.embed_texts([query], api_key=api_key)[0], dtype=np.float32)
    qv /= max(float(np.linalg.norm(qv)), 1e-12)
    sims = mat @ qv
    order = np.argsort(-sims)[:top_k]
    out = []
    for i in order:
        c = dict(chunks[int(i)])
        c["score"] = float(sims[int(i)])
        out.append(c)
    return out
