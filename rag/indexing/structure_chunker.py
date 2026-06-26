"""
구조 인식 청커 (KOTRA 국가별/정책규제 보고서 전용)

2. 문서 파싱 + 3. 청킹을 한 번에 수행한다. 규칙 기반(모델 불필요)으로
보고서의 논리 구조를 추출해 청크 단위로 자른다.

산출 청크 스키마(요청하신 샘플과 동일 계열):
  chunk_id, doc_id, source_file, title, country, year, field, doc_source,
  text, page, chunk_type(summary|body|table|interview|reference),
  chapter, section, subsection, table_title, caption_source, footnotes[]

핵심 처리:
  - 본문: pdfplumber 로 줄 복원(레이아웃), 표 영역은 page.filter 로 제외
  - 표  : find_tables → 마크다운, 캡션([표 N]/[그림 N])과 출처 매칭
  - 헤딩: chapter `^\\d+\\.`, section `^\\(\\d+\\)`, subsection `^n `(■ 글리프)
  - 정리: 널바이트(\\x00)·제어문자 제거
  - chunk_type: chapter 키워드로 분류, 표는 table
"""
from __future__ import annotations

import re

import pdfplumber

from rag.monitoring import get_logger

log = get_logger()

# ── 정리: 널바이트·제어문자 제거 ────────────────────────
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\x00", "")
    s = _CTRL.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


# ── 헤딩/구조 패턴 ──────────────────────────────────────
RE_CHAPTER = re.compile(r"^(\d+)\.\s+(.+)$")        # "1. UAE 신재생에너지 시장 특성"
RE_SECTION = re.compile(r"^\((\d+)\)\s+(.+)$")       # "(1) UAE 에너지 산업 현황"
RE_SUBSEC = re.compile(r"^n\s+(.+)$")                # "n 에너지 산업 구조 및 규모" (■ 글리프)
RE_CAPTION = re.compile(r"\[(?:표|그림)\s*\d+\][^\n]*")
RE_FOOTNOTE = re.compile(r"^\(?(\d+)\)\s+\S")        # "1) 생물 유기체로부터…"
RE_DOTLEADER = re.compile(r"[·]{2,}|…|\.{4,}")       # 목차(TOC) 점선 리더
RE_PAGENO = re.compile(r"^\d{1,3}$")                 # 단독 페이지번호 줄
# "◈ 요약" 같은 단독 키워드 헤딩 (줄 전체가 키워드일 때만 — "출처: …" 캡션과 구분)
RE_KW = re.compile(r"^[◈※]?\s*(요약|목차|시사점|출처|참고문헌|현지\s*인터뷰)\s*$")

# chapter 키워드 → chunk_type
CHAPTER_TYPE = [
    ("요약", "summary"),
    ("인터뷰", "interview"),
    ("출처", "reference"),
    ("참고문헌", "reference"),
    ("references", "reference"),
]


def _chapter_type(chapter: str) -> str:
    low = chapter.lower()
    for kw, t in CHAPTER_TYPE:
        if kw in low:
            return t
    return "body"


# ── 표 → 마크다운 ───────────────────────────────────────
def _table_to_md(rows: list) -> str:
    rows = [[(_clean(c) if c else "") for c in r] for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "|".join(["---"] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(cell.replace("\n", " ") for cell in r) + " |")
    return "\n".join(out)


# ── 본문 줄 추출 (표 영역 제외) ─────────────────────────
def _body_lines(page, table_boxes: list) -> list[str]:
    def keep(o):
        cx = (o["x0"] + o["x1"]) / 2
        cy = (o["top"] + o["bottom"]) / 2
        return not any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in table_boxes)

    txt = page.filter(keep).extract_text(x_tolerance=2) or ""
    return [_clean(ln) for ln in txt.split("\n") if _clean(ln)]


# ── 메인: PDF → 청크 리스트 ─────────────────────────────
def parse_and_chunk(pdf_path: str, meta: dict, doc_id: str) -> list[dict]:
    chunks: list[dict] = []
    idx = 0
    # 문서 전체에 걸쳐 유지되는 구조 상태
    chapter = chapter_type = section = subsection = ""

    def new_chunk(text, page, ctype, **extra):
        nonlocal idx
        text = text.strip()
        if not text:
            return
        # chapter 가 정해지기 전(표지·머리말 등)의 잡음 청크는 버린다
        if not chapter:
            return
        c = {
            "chunk_id": f"{doc_id}_c{idx:04d}",
            "doc_id": doc_id,
            "source_file": meta["pdf_filename"],
            "title": meta["title"],
            "country": meta["country"],
            "year": meta["year"],
            "field": meta["field"],
            "doc_source": meta["source"],     # 보고서 출처(시트명)
            "tags": meta.get("tags", ""),
            "text": text,
            "page": page,
            "chunk_type": ctype,
            "chapter": chapter,
            "section": section,
            "subsection": subsection,
            "table_title": extra.get("table_title", ""),
            "caption_source": extra.get("caption_source", ""),
            "footnotes": extra.get("footnotes", []),
        }
        chunks.append(c)
        idx += 1

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            boxes = [t.bbox for t in tables]
            lines = _body_lines(page, boxes)

            # 페이지 내 캡션/출처/각주 수집
            captions = [_clean(m) for ln in lines for m in RE_CAPTION.findall(ln)]
            page_footnotes = [ln for ln in lines if RE_FOOTNOTE.match(ln) and len(ln) > 25]

            # ── 본문 청킹 (구조 경계 기준) ──
            buf: list[str] = []

            def flush(page=pno):
                if not buf:
                    return
                body = "\n".join(buf)
                ctype = chapter_type or "body"
                # 이 청크가 참조하는 각주만 부착
                fns = [f for f in page_footnotes
                       if re.match(rf"^\(?{re.escape(f.split(')')[0])}\)", f)
                       and (f.split(")")[0] + ")") in body]
                new_chunk(body, page, ctype, footnotes=fns)
                buf.clear()

            for ln in lines:
                # 목차(점선 리더)·단독 페이지번호 줄은 구조에 반영하지 않고 버린다
                if RE_DOTLEADER.search(ln) or RE_PAGENO.match(ln):
                    continue

                m_kw = RE_KW.match(ln)
                m_ch = RE_CHAPTER.match(ln)
                m_se = RE_SECTION.match(ln)
                m_su = RE_SUBSEC.match(ln)

                if m_kw:
                    kw = m_kw.group(1).replace(" ", "")
                    if kw == "목차":
                        continue  # 목차 헤딩은 무시
                    flush()
                    chapter = kw
                    chapter_type = _chapter_type(chapter)
                    section = subsection = ""
                    continue
                if m_ch:
                    flush()
                    chapter = f"{m_ch.group(1)}. {m_ch.group(2)}"
                    chapter_type = _chapter_type(chapter)
                    section = subsection = ""
                    continue
                if m_se:
                    flush()
                    section = ln
                    subsection = ""
                    continue
                if m_su:
                    flush()
                    subsection = m_su.group(1).strip()
                    continue
                if RE_CAPTION.fullmatch(ln) or ln.startswith("출처"):
                    # 표/그림 캡션·출처 라인은 본문에서 제외(표 청크에서 사용)
                    continue
                if RE_FOOTNOTE.match(ln) and len(ln) > 25:
                    continue  # 각주는 별도 부착
                buf.append(ln)
                # 길이 상한(과대 청크 방지): 본문이 매우 길면 분할
                if sum(len(x) for x in buf) > 1100:
                    flush()
            flush()

            # ── 표 청킹 ──
            src_lines = [ln for ln in lines if ln.startswith("출처")]
            for ti, t in enumerate(tables):
                rows = t.extract()
                # 빈 표(목차 페이지 등에서 오검출) 제외: 비어있지 않은 셀 4개 이상
                nonempty = sum(1 for r in rows for c in r if c and _clean(c))
                if len(rows) < 2 or nonempty < 4:
                    continue
                md = _table_to_md(rows)
                if not md:
                    continue
                ttitle = captions[ti] if ti < len(captions) else ""
                csource = src_lines[ti] if ti < len(src_lines) else ""
                text = (ttitle + "\n" + md) if ttitle else md
                new_chunk(text, pno, "table",
                          table_title=ttitle, caption_source=csource)

    from collections import Counter
    log.debug("[chunk] %s → %d청크 %s", doc_id, len(chunks),
              dict(Counter(c["chunk_type"] for c in chunks)))
    return chunks


# ── 임베딩/BM25 용 컨텍스트 헤더 텍스트 ──────────────────
def context_text(c: dict) -> str:
    """짧은 청크에 맥락을 부여하기 위해 제목·구조 헤더를 본문 앞에 결합."""
    parts = [p for p in [c.get("country"), c.get("title")] if p]
    path = " > ".join(p for p in [c.get("chapter"), c.get("section"), c.get("subsection")] if p)
    header = " | ".join([" ".join(parts), path]).strip(" |")
    if c.get("table_title"):
        header = (header + " | " + c["table_title"]).strip(" |")
    return f"{header}\n{c['text']}" if header else c["text"]
