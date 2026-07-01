"""
FastAPI 백엔드 — 기존 RAG 코어(rag/)를 그대로 재사용해 REST + SSE 스트리밍으로 노출.

Streamlit(app.py)의 두 모드(KEITI 고정 코퍼스 / 내 문서 업로드)를 동일하게 제공:
  - 검색 → 리랭크 → 스트리밍 답변(SSE: meta → token... → done)
  - 답변 형태 3종(요약/일반/전문가): 같은 질문이면 근거(sources) 재사용해 LLM만 재호출
  - 비용/토큰/시간 모니터링, 근거 출처, 문서 전문/PDF 뷰

RAG 로직은 한 줄도 바꾸지 않는다(이 파일은 얇은 어댑터 계층).
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from threading import Lock

# 저장소 루트를 import 경로에 추가(backend/ 의 부모) → `rag` 패키지 사용
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from rag import config
from rag import qa_pipeline as qa
from rag import upload_pipeline
from rag.monitoring import get_logger

log = get_logger()
app = FastAPI(title="코네틱 보고서 RAG API")

# 개발: Vite(5173)에서 호출. 운영은 동일 출처 서빙 권장.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# qa_pipeline 은 마지막 호출 사용량을 모듈 전역에 둔다 → 동시 요청 시 사용량이 섞이지
# 않도록 질의 1건을 직렬화한다(PoC: 저트래픽 가정).
_QUERY_LOCK = Lock()

# 업로드 인덱스(임베딩 행렬은 클라이언트로 못 보냄) → 세션별 서버 메모리 보관
UPLOAD_SESSIONS: dict[str, dict] = {}

STYLES = [
    {"key": "summary", "label": "📌 3문장 요약", "help": "핵심만 3문장 이내로 압축"},
    {"key": "normal", "label": "📝 일반 답변", "help": "이해하기 쉬운 일반 설명"},
    {"key": "expert", "label": "🎓 전문가 답변", "help": "수치·정책·함의까지 짚는 전문가 수준"},
]

# 근거(chunk)에서 프론트로 보낼 필드만 추린다.
_SOURCE_FIELDS = ("chunk_id", "source_file", "title", "page", "chunk_type", "score",
                  "chapter", "section", "subsection", "doc_source", "text",
                  "table_title", "footnotes", "country", "year", "field", "tags")


def _slim_source(s: dict) -> dict:
    out = {k: s.get(k) for k in _SOURCE_FIELDS if k in s}
    if "score" in s:
        out["score"] = float(s["score"])
    return out


# ════════════════════════════════════════════════════════
# 고정 코퍼스 로드 (app.load_corpus 미러)
# ════════════════════════════════════════════════════════
def _load_corpus():
    chunks: list[dict] = []
    if config.CHUNK_DUMP.exists():
        with open(config.CHUNK_DUMP, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f]
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        by_doc[c["source_file"]].append(c)
    docs = {fn: cs[0] for fn, cs in by_doc.items()}
    return dict(by_doc), docs, len(chunks)


CORPUS_BY_DOC, CORPUS_DOCS, CORPUS_N = _load_corpus()
log.info("[api] 코퍼스 로드: 문서 %d · 청크 %d", len(CORPUS_DOCS), CORPUS_N)


def _pdf_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for d in config.pdf_dirs():
        if d.exists():
            for p in d.glob("*.pdf"):
                idx[p.name] = str(p)
    return idx


PDF_INDEX = _pdf_index()


def _doc_meta(meta: dict, chunks: list[dict]) -> dict:
    return {
        "source_file": meta.get("source_file"),
        "title": meta.get("title") or meta.get("source_file"),
        "country": meta.get("country", ""),
        "year": meta.get("year", ""),
        "field": meta.get("field", ""),
        "tags": meta.get("tags", ""),
        "doc_source": meta.get("doc_source", ""),
        "chunks": len(chunks),
        "has_pdf": meta.get("source_file") in PDF_INDEX,
    }


# ════════════════════════════════════════════════════════
# 세션 조회 헬퍼 (업로드 모드)
# ════════════════════════════════════════════════════════
def _session_corpus(session_id: str | None):
    """업로드 세션 → (by_doc, docs) 구성. 없으면 빈 dict."""
    idx = UPLOAD_SESSIONS.get(session_id or "")
    if not idx:
        return {}, {}
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for c in idx["chunks"]:
        by_doc[c["source_file"]].append(c)
    return dict(by_doc), {fn: cs[0] for fn, cs in by_doc.items()}


# ════════════════════════════════════════════════════════
# REST: 설정 / 문서 목록 / 문서 전문 / PDF
# ════════════════════════════════════════════════════════
@app.get("/api/config")
def get_config():
    return {
        "publicKey": bool(config.OPENAI_API_KEY),
        "model": config.OPENAI_MODEL,
        "embedModel": config.OPENAI_EMBED_MODEL,
        "rerankModel": config.OPENAI_RERANK_MODEL,
        "vectorBackend": config.VECTOR_BACKEND,
        "rerankDefault": config.RERANK_BACKEND,
        "styles": STYLES,
        "corpus": {"docs": len(CORPUS_DOCS), "chunks": CORPUS_N},
    }


@app.get("/api/documents")
def list_documents(mode: str = "keiti", sessionId: str | None = None):
    if mode == "upload":
        by_doc, docs = _session_corpus(sessionId)
    else:
        by_doc, docs = CORPUS_BY_DOC, CORPUS_DOCS
    items = [_doc_meta(docs[fn], by_doc[fn]) for fn in docs]
    return {"documents": items, "count": len(items)}


@app.get("/api/documents/full")
def document_full(source_file: str, mode: str = "keiti", sessionId: str | None = None):
    if mode == "upload":
        by_doc, docs = _session_corpus(sessionId)
    else:
        by_doc, docs = CORPUS_BY_DOC, CORPUS_DOCS
    if source_file not in docs:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    meta = docs[source_file]
    chunks = sorted(by_doc[source_file],
                    key=lambda x: (int(x.get("page", 0) or 0), x.get("chunk_id", "")))
    blocks = [{
        "page": c.get("page"),
        "text": c.get("text", ""),
        "table_title": c.get("table_title", ""),
        "footnotes": c.get("footnotes", []),
    } for c in chunks]
    import urllib.parse
    title = meta.get("title") or source_file
    konetic = "https://www.google.com/search?q=" + urllib.parse.quote(f"{title} 코네틱")
    return {
        "meta": _doc_meta(meta, chunks),
        "blocks": blocks,
        "hasPdf": source_file in PDF_INDEX,
        "pdfUrl": f"/api/pdf?source_file={urllib.parse.quote(source_file)}" if source_file in PDF_INDEX else None,
        "koneticUrl": konetic,
    }


@app.get("/api/pdf")
def get_pdf(source_file: str):
    path = PDF_INDEX.get(source_file)
    if not path or not Path(path).exists():
        raise HTTPException(404, "PDF가 없습니다(배포 환경엔 원본 PDF 미포함).")
    # inline: iframe 미리보기용(attachment 면 브라우저가 자동 다운로드함).
    # 명시 다운로드는 프론트의 <a download> 링크가 처리한다.
    return FileResponse(path, media_type="application/pdf",
                        content_disposition_type="inline")


# ════════════════════════════════════════════════════════
# 업로드: PDF 파싱·임베딩 → 세션 인덱스
# ════════════════════════════════════════════════════════
@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...), apiKey: str = Form("")):
    blobs = []
    for f in files:
        data = await f.read()
        blobs.append(type("F", (), {"read": lambda self, d=data: d, "name": f.filename})())
    try:
        idx = upload_pipeline.process_files(blobs, apiKey.strip() or config.OPENAI_API_KEY)
    except Exception as e:
        log.exception("[api] 업로드 처리 실패")
        raise HTTPException(400, f"{type(e).__name__}: {e}")
    sid = uuid.uuid4().hex
    UPLOAD_SESSIONS[sid] = idx
    by_doc, docs = _session_corpus(sid)
    return {
        "sessionId": sid,
        "chunks": len(idx["chunks"]),
        "documents": [_doc_meta(docs[fn], by_doc[fn]) for fn in docs],
    }


# ════════════════════════════════════════════════════════
# SSE 스트리밍: 질의(검색+답변) / 형태 전환(근거 재사용)
# ════════════════════════════════════════════════════════
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class QueryReq(BaseModel):
    query: str
    mode: str = "keiti"          # keiti | upload
    rerank: str | None = None    # off | openai
    style: str = "normal"
    apiKey: str | None = None
    sessionId: str | None = None


class AnswerReq(BaseModel):
    query: str
    sources: list[dict]
    style: str = "normal"
    apiKey: str | None = None


def _query_gen(req: QueryReq):
    key = (req.apiKey or "").strip() or None
    rerank = req.rerank or config.RERANK_BACKEND
    with _QUERY_LOCK:
        try:
            if req.mode == "upload":
                idx = UPLOAD_SESSIONS.get(req.sessionId or "")
                if not idx or not idx.get("chunks"):
                    yield _sse("error", {"message": "업로드 세션이 없습니다. 먼저 PDF를 업로드하세요."})
                    return
                cands = upload_pipeline.search(
                    req.query, idx, key or config.OPENAI_API_KEY, top_k=config.TOP_K_RETRIEVE)
                sr = qa.search_rerank(req.query, candidates=cands, rerank_backend=rerank, api_key=key)
            else:
                sr = qa.search_rerank(req.query, rerank_backend=rerank, api_key=key)
            sources = sr["sources"]
            yield _sse("meta", {
                "sources": [_slim_source(s) for s in sources],
                "timings": {"retrieve": sr["timings"]["retrieve"],
                            "rerank": sr["timings"]["rerank"]},
            })
            t0 = time.time()
            for piece in qa.generate_answer_stream(req.query, sources, api_key=key, style=req.style):
                yield _sse("token", {"text": piece})
            llm_t = time.time() - t0
            usage = qa.collect_full_usage()
            yield _sse("done", {
                "usage": usage, "llm_time": llm_t,
                "timings": {"retrieve": sr["timings"]["retrieve"],
                            "rerank": sr["timings"]["rerank"], "llm": llm_t,
                            "total": sr["timings"]["retrieve"] + sr["timings"]["rerank"] + llm_t},
            })
        except Exception as e:
            log.exception("[api] 질의 스트림 실패")
            yield _sse("error", {"message": f"{type(e).__name__}: {e}"})


def _answer_gen(req: AnswerReq):
    """형태 전환: 클라이언트가 보낸 근거를 재사용해 LLM만 스트리밍(검색 비용 0)."""
    key = (req.apiKey or "").strip() or None
    with _QUERY_LOCK:
        try:
            t0 = time.time()
            for piece in qa.generate_answer_stream(req.query, req.sources, api_key=key, style=req.style):
                yield _sse("token", {"text": piece})
            llm_t = time.time() - t0
            usage = qa.collect_llm_usage()
            yield _sse("done", {"usage": usage, "llm_time": llm_t,
                                "timings": {"retrieve": 0.0, "rerank": 0.0,
                                            "llm": llm_t, "total": llm_t}})
        except Exception as e:
            log.exception("[api] 답변 스트림 실패")
            yield _sse("error", {"message": f"{type(e).__name__}: {e}"})


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.post("/api/query")
def query(req: QueryReq):
    return StreamingResponse(_query_gen(req), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


@app.post("/api/answer")
def answer(req: AnswerReq):
    return StreamingResponse(_answer_gen(req), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


@app.get("/api/health")
def health():
    return {"ok": True}
