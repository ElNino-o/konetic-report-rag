"""
대국민 화면 (Streamlit) — OpenAI 전용 · BYOK

두 모드:
  1) KEITI 보고서   : 사전 인덱싱한 고정 코퍼스(storage/) 질의응답
  2) 내 문서 업로드 : 올린 PDF 를 런타임에 파싱·청킹·임베딩(세션 메모리)해 질의응답

인증/비용: 사용자가 사이드바에 본인 OpenAI 키 입력(BYOK). 키는 세션에만 보관하며
          로깅/저장하지 않는다. 로컬에선 .env 키로 폴백한다.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import streamlit as st

# Streamlit Cloud: st.secrets → 환경변수 주입(config import 전에)
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

from rag import config
from rag.monitoring import get_logger

st.set_page_config(page_title="코네틱 국가별보고서, 규제보고서 Q&A", layout="wide")
get_logger().info("[app] 시작 · 설정요약: %s", config.summary())

TYPE_ICON = {"summary": "📌", "body": "📄", "table": "📊",
             "interview": "🎤", "reference": "🔗"}


# ── 고정 코퍼스(청크 백업) 자동 로드 ─────────────────────
@st.cache_data
def load_corpus():
    chunks = []
    if config.CHUNK_DUMP.exists():
        with open(config.CHUNK_DUMP, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f]
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c["source_file"]].append(c)
    return dict(by_doc), {fn: cs[0] for fn, cs in by_doc.items()}, len(chunks)


def _path(c: dict) -> str:
    return " > ".join(p for p in [c.get("chapter"), c.get("section"),
                                  c.get("subsection")] if p)


def render_answer(result, sess):
    """답변 + 모니터링(시간/토큰/비용) + 근거."""
    tm, ug = result["timings"], result["usage"]
    sess["cost"] += ug["cost_usd"]
    sess["queries"] += 1
    sess["tokens"] += (ug["embed_tokens"] + ug["rerank_tokens"]
                       + ug["llm_prompt_tokens"] + ug["llm_completion_tokens"])
    mc = st.columns(4)
    mc[0].metric("총 시간", f"{tm['total']:.1f}s")
    mc[1].metric("검색", f"{tm['retrieve']:.1f}s")
    mc[2].metric("리랭크", f"{tm['rerank']:.1f}s")
    mc[3].metric("LLM", f"{tm['llm']:.1f}s")
    with st.expander(f"💰 이번 질의 추정 비용 ${ug['cost_usd']:.6f} · "
                     f"토큰 {ug['llm_prompt_tokens']}+{ug['llm_completion_tokens']}"):
        st.json({"임베딩 토큰": ug["embed_tokens"], "리랭크 토큰": ug["rerank_tokens"],
                 "LLM 토큰(p/c)": f"{ug['llm_prompt_tokens']}/{ug['llm_completion_tokens']}",
                 "비용(USD)": {k: round(v, 6) for k, v in ug["cost_breakdown"].items()}})
    st.subheader("4. 답변")
    st.markdown(result["answer"])
    st.subheader("📎 근거 (출처 · 페이지)")
    for i, s in enumerate(result["sources"], 1):
        with st.expander(f"[{i}] {s.get('title')} · p.{s.get('page')} · "
                         f"{s.get('chunk_type','')} (score={s['score']:.3f})"):
            if _path(s):
                st.caption(f"📑 {_path(s)}")
            st.write(s["text"])
            st.caption(f"출처: {s.get('doc_source','')} | 파일: {s.get('source_file','')}")


def render_doc_browser(by_doc: dict, docs: dict):
    """우측: 문서 목록 + 선택 문서의 청크."""
    if not docs:
        st.info("표시할 문서가 없습니다.")
        return
    labels = {fn: f"{m.get('title', fn)} · {m.get('country','')}/{m.get('year','')}"
              for fn, m in docs.items()}
    sel = st.selectbox("문서 선택", list(docs.keys()), format_func=lambda fn: labels[fn])
    m = docs[sel]
    meta_line = f"**{m.get('title')}**"
    if m.get("country") or m.get("year"):
        meta_line += f"  \n국가: {m.get('country')} · 발행연도: {m.get('year')} · 분야: {m.get('field')}"
    st.markdown(meta_line)
    if m.get("tags"):
        st.caption(f"🏷️ {m['tags']}")
    st.divider()
    for c in sorted(by_doc[sel], key=lambda x: (int(x["page"]), x["chunk_id"])):
        icon = TYPE_ICON.get(c["chunk_type"], "•")
        with st.expander(f"{icon} p.{c['page']} · {c['chunk_type']} — {_path(c) or c['chunk_id']}"):
            if c.get("table_title"):
                st.caption(f"📊 {c['table_title']}")
            st.write(c["text"])
            if c.get("footnotes"):
                st.caption("각주: " + " / ".join(c["footnotes"]))


def load_qa():
    from rag import qa_pipeline
    return qa_pipeline


corpus_by_doc, corpus_docs, corpus_n = load_corpus()

# ════════════════════════════════════════════════════════
# 사이드바: BYOK 키 · 모드 · 리랭킹 · 상태
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.header("🔑 OpenAI 키 (BYOK)")
    key_in = st.text_input("OpenAI API 키", type="password",
                           placeholder="sk-...", help="세션에만 보관 · 저장/로깅 안 함")
    eff_key = key_in.strip() or config.OPENAI_API_KEY
    st.caption("키 보유 ✅" if eff_key else "키를 입력해야 질의할 수 있습니다")

    st.divider()
    mode = st.radio("모드", ["KEITI 보고서", "내 문서 업로드"])
    rr = st.radio("리랭킹", ["off", "openai"],
                  captions=["끄기 (가장 빠름)", f"OpenAI LLM ({config.OPENAI_RERANK_MODEL})"],
                  index=1 if config.RERANK_BACKEND == "openai" else 0)

    st.divider()
    st.header("📊 상태")
    if mode == "KEITI 보고서":
        st.metric("문서 수", f"{len(corpus_docs)} 건")
        st.metric("청크 수", f"{corpus_n} 개")
        st.caption(f"벡터 저장소: **{config.VECTOR_BACKEND}** · `{config.collection_name()}`")
    else:
        up = st.session_state.get("upload_index", {"chunks": [], "mat": None})
        st.metric("업로드 문서", f"{len({c['source_file'] for c in up['chunks']})} 건")
        st.metric("청크 수", f"{len(up['chunks'])} 개")
    st.caption(f"임베딩 {config.OPENAI_EMBED_MODEL} · LLM {config.OPENAI_MODEL}")

    sess = st.session_state.setdefault("usage_total", {"cost": 0.0, "queries": 0, "tokens": 0})
    st.divider()
    st.header("💰 세션 비용")
    st.metric("누적 추정 비용", f"${sess['cost']:.4f}")
    st.caption(f"질의 {sess['queries']}건 · 누적 토큰 {sess['tokens']:,}")

st.title("🌏 코네틱 국가별보고서, 규제보고서 Q&A")

# ════════════════════════════════════════════════════════
# 모드 1: KEITI 고정 코퍼스
# ════════════════════════════════════════════════════════
if mode == "KEITI 보고서":
    st.caption(f"보고서 {len(corpus_docs)}건 · 임베딩/리랭크/LLM 모두 OpenAI")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("1. 질문")
        query = st.text_area("자연어 질문", height=100,
                             placeholder="예) 폴란드 이차전지 시장 동향을 알려줘")
        run = st.button("🔎 검색 · 답변", type="primary", use_container_width=True,
                        disabled=not (corpus_docs and eff_key))
        if not eff_key:
            st.warning("사이드바에 OpenAI 키를 입력하세요.")
        if run and query.strip():
            qa = load_qa()
            get_logger().info("[app] KEITI 질의 q=%r rerank=%s", query, rr)
            try:
                with st.spinner("2. 검색 → 3. 리랭킹 → 4. 답변..."):
                    result = qa.answer(query, rerank_backend=rr, api_key=key_in.strip() or None)
            except Exception as e:
                get_logger().exception("[app] answer 실패")
                st.error(f"처리 중 오류: {type(e).__name__}: {e}")
                st.stop()
            render_answer(result, sess)
    with right:
        st.subheader("📚 PDF 목록")
        render_doc_browser(corpus_by_doc, corpus_docs)

# ════════════════════════════════════════════════════════
# 모드 2: 내 문서 업로드 (세션 임시)
# ════════════════════════════════════════════════════════
else:
    st.caption("PDF 를 올리면 런타임에 파싱·청킹·임베딩하여(세션 메모리) 질의합니다.")
    files = st.file_uploader("PDF 업로드 (여러 개 가능)", type=["pdf"],
                             accept_multiple_files=True)
    if st.button("📥 업로드 처리(파싱·임베딩)", disabled=not (files and eff_key)):
        from rag import upload_pipeline
        with st.spinner("파싱 → 청킹 → 임베딩 중..."):
            try:
                idx = upload_pipeline.process_files(files, key_in.strip() or config.OPENAI_API_KEY)
                st.session_state["upload_index"] = idx
                st.success(f"완료: {len(idx['chunks'])} 청크 임베딩")
            except Exception as e:
                st.error(f"업로드 처리 오류: {type(e).__name__}: {e}")
    if not eff_key:
        st.warning("사이드바에 OpenAI 키를 입력하세요.")

    up = st.session_state.get("upload_index", {"chunks": [], "mat": None})
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("1. 질문")
        uq = st.text_area("자연어 질문", height=100, key="upq",
                          placeholder="업로드한 문서에 대해 질문하세요")
        urun = st.button("🔎 검색 · 답변", type="primary", use_container_width=True,
                         disabled=not (up["chunks"] and eff_key))
        if not up["chunks"]:
            st.info("먼저 PDF 를 업로드·처리하세요.")
        if urun and uq.strip():
            from rag import upload_pipeline
            qa = load_qa()
            get_logger().info("[app] 업로드 질의 q=%r rerank=%s", uq, rr)
            try:
                with st.spinner("2. 검색 → 3. 리랭킹 → 4. 답변..."):
                    hits = upload_pipeline.search(uq, up, key_in.strip() or config.OPENAI_API_KEY,
                                                  top_k=config.TOP_K_RETRIEVE)
                    result = qa.answer(uq, candidates=hits, rerank_backend=rr,
                                       api_key=key_in.strip() or None)
            except Exception as e:
                get_logger().exception("[app] 업로드 answer 실패")
                st.error(f"처리 중 오류: {type(e).__name__}: {e}")
                st.stop()
            render_answer(result, sess)
    with right:
        st.subheader("📚 업로드 문서")
        by_doc = defaultdict(list)
        for c in up["chunks"]:
            by_doc[c["source_file"]].append(c)
        render_doc_browser(dict(by_doc), {fn: cs[0] for fn, cs in by_doc.items()})
