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


def _password_gate():
    """공개 배포에서 공용 키 남용 방지. APP_PASSWORD 가 설정된 경우에만 동작."""
    pw = os.getenv("APP_PASSWORD", "")
    if not pw or st.session_state.get("authed"):
        return
    st.title("🔒 코네틱 보고서 Q&A")
    entered = st.text_input("접속 비밀번호", type="password")
    if st.button("입장"):
        if entered == pw:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


_password_gate()


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
    render_session_cost()   # 사이드바 누적값을 이번 질의 반영해 즉시 갱신
    st.subheader("💬 답변")
    st.markdown(result["answer"])
    st.subheader("📎 근거 (출처 · 페이지)")
    for i, s in enumerate(result["sources"], 1):
        with st.expander(f"[{i}] {s.get('title')} · p.{s.get('page')} · "
                         f"{s.get('chunk_type','')} (score={s['score']:.3f})"):
            if _path(s):
                st.caption(f"📑 {_path(s)}")
            st.write(s["text"])
            st.caption(f"출처: {s.get('doc_source','')} | 파일: {s.get('source_file','')}")


# ── 원본 PDF 위치/원문 링크 ──────────────────────────────
@st.cache_data
def _pdf_index() -> dict:
    """데이터 폴더의 PDF 파일명→경로 색인(로컬 전용). 배포엔 PDF 없어 빈 dict."""
    idx = {}
    for d in config.pdf_dirs():
        if d.exists():
            for p in d.glob("*.pdf"):
                idx[p.name] = str(p)
    return idx


def _pdf_path(source_file: str):
    from pathlib import Path
    p = _pdf_index().get(source_file)
    return Path(p) if p else None


def _konetic_search_url(title: str) -> str:
    """konetic 보고서는 내부 ID로만 접근 → 제목 검색 링크로 원문 안내."""
    import urllib.parse
    return "https://www.google.com/search?q=" + urllib.parse.quote(f"{title} 코네틱")


def _embed_pdf(path):
    """실제 PDF 를 전체 화면으로 임베드(로컬). 내려받기 버튼 동반."""
    import base64
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="850" '
        'style="border:1px solid #ddd;border-radius:6px"></iframe>',
        unsafe_allow_html=True,
    )
    st.download_button("⬇️ PDF 내려받기", data, file_name=path.name,
                       mime="application/pdf", use_container_width=True)


def _render_full_text(chunks: list[dict]):
    """원본 PDF 가 없을 때(배포): 추출 텍스트를 페이지 순서로 이어 문서 전문처럼 표시."""
    cur = None
    for c in sorted(chunks, key=lambda x: (int(x["page"]), x["chunk_id"])):
        if c["page"] != cur:
            cur = c["page"]
            st.markdown(f"###### 📄 p.{cur}")
        if c.get("table_title"):
            st.caption(f"📊 {c['table_title']}")
        st.markdown(c["text"])
        if c.get("footnotes"):
            st.caption("각주: " + " / ".join(c["footnotes"]))


def render_full_document(source_file: str, chunks: list[dict], meta: dict):
    """선택 문서를 전체 화면으로: 로컬 PDF 임베드 → 없으면 문서 전문(텍스트) + 원문 링크."""
    st.markdown(f"**{meta.get('title', source_file)}**")
    info = [x for x in [f"국가 {meta.get('country')}" if meta.get("country") else "",
                        f"발행 {meta.get('year')}" if meta.get("year") else "",
                        meta.get("field", "")] if x]
    if info:
        st.caption(" · ".join(info))
    if meta.get("tags"):
        st.caption(f"🏷️ {meta['tags']}")
    st.markdown(f"[🔗 코네틱(konetic.or.kr)에서 원문 보기]"
                f"({_konetic_search_url(meta.get('title') or source_file)})")
    st.divider()
    pdf = _pdf_path(source_file)
    if pdf:
        _embed_pdf(pdf)
    else:
        st.caption("ℹ️ 배포 환경에는 원본 PDF가 없어 **문서 전문(추출 텍스트)** 으로 표시합니다. "
                   "원본은 위 ‘코네틱에서 원문 보기’ 링크로 확인하세요.")
        _render_full_text(chunks)


def render_doc_panel(by_doc: dict, docs: dict, relevant=None, key_prefix=""):
    """질문 후엔 관련 문서만, 질문 전엔 전체 목록. 선택 시 전체 화면 표시."""
    if not docs:
        st.info("표시할 문서가 없습니다.")
        return
    all_files = list(docs.keys())
    rel = [f for f in (relevant or []) if f in docs]
    if rel:
        show_all = st.checkbox(f"전체 문서 목록 보기 ({len(all_files)}건)",
                               value=False, key=f"{key_prefix}showall")
        files = all_files if show_all else rel
        if not show_all:
            st.caption(f"🎯 이번 질문에 사용된 문서 {len(rel)}건")
    else:
        files = all_files
        st.caption(f"전체 문서 {len(all_files)}건 — 질문하면 관련 문서만 보여줍니다.")
    labels = {fn: f"{docs[fn].get('title', fn)} · "
                  f"{docs[fn].get('country','')}/{docs[fn].get('year','')}" for fn in files}
    # 옵션 목록이 (전체↔관련) 바뀔 때 이전 선택값이 빠지면 예외 → 초기화
    sk = f"{key_prefix}docsel"
    if st.session_state.get(sk) not in files:
        st.session_state.pop(sk, None)
    sel = st.selectbox("문서 선택", files, format_func=lambda fn: labels[fn], key=sk)
    st.divider()
    render_full_document(sel, by_doc.get(sel, []), docs[sel])


def load_qa():
    from rag import qa_pipeline
    return qa_pipeline


corpus_by_doc, corpus_docs, corpus_n = load_corpus()

# ════════════════════════════════════════════════════════
# 사이드바: 키 · 모드 · 리랭킹 · 상태
# ════════════════════════════════════════════════════════
with st.sidebar:
    # 공용 키(secrets/.env)가 있으면 그걸 쓰고 입력칸 숨김(PoC). 없으면 BYOK 입력.
    if config.OPENAI_API_KEY:
        key_in = ""
        eff_key = config.OPENAI_API_KEY
        st.caption("🔑 공용 OpenAI 키 사용 중")
    else:
        st.header("🔑 OpenAI 키 (BYOK)")
        key_in = st.text_input("OpenAI API 키", type="password",
                               placeholder="sk-...", help="세션에만 보관 · 저장/로깅 안 함")
        eff_key = key_in.strip()
        st.caption("키 보유 ✅" if eff_key else "키를 입력해야 질의할 수 있습니다")

    st.divider()
    mode = st.radio("모드", ["KEITI 보고서", "내 문서 업로드"])
    rr = st.radio("리랭킹", ["off", "openai"],
                  captions=["끄기 (가장 빠름)", f"OpenAI LLM ({config.OPENAI_RERANK_MODEL})"],
                  index=1 if config.RERANK_BACKEND == "openai" else 0)

    st.divider()
    st.subheader("📊 상태")
    if mode == "KEITI 보고서":
        n_docs, n_chunks = len(corpus_docs), corpus_n
    else:
        up = st.session_state.get("upload_index", {"chunks": [], "mat": None})
        n_docs = len({c["source_file"] for c in up["chunks"]})
        n_chunks = len(up["chunks"])
    sc1, sc2 = st.columns(2)
    sc1.metric("문서", f"{n_docs}")
    sc2.metric("청크", f"{n_chunks}")
    st.caption(f"벡터 저장소 `{config.VECTOR_BACKEND}` · 임베딩 `{config.OPENAI_EMBED_MODEL}`")
    st.caption(f"답변 LLM `{config.OPENAI_MODEL}`")

    sess = st.session_state.setdefault("usage_total", {"cost": 0.0, "queries": 0, "tokens": 0})
    st.divider()
    st.subheader("💰 세션 누적")
    _cost_ph = st.empty()   # 답변 직후 즉시 갱신(한 박자 지연 방지)


def render_session_cost():
    """사이드바 세션 비용 placeholder 를 현재 누적값으로 다시 그린다."""
    with _cost_ph.container():
        cc1, cc2 = st.columns(2)
        cc1.metric("추정 비용", f"${sess['cost']:.4f}")
        cc2.metric("질의 수", f"{sess['queries']}")
        st.caption(f"누적 토큰 {sess['tokens']:,}")


render_session_cost()

st.title("🌏 코네틱 국가별보고서, 규제보고서 Q&A")

# ════════════════════════════════════════════════════════
# 모드 1: KEITI 고정 코퍼스
# ════════════════════════════════════════════════════════
if mode == "KEITI 보고서":
    st.caption(f"보고서 {len(corpus_docs)}건 · 임베딩/리랭크/LLM 모두 OpenAI")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("✍️ 질문")
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
                with st.spinner("검색 → 리랭킹 → 답변 생성 중..."):
                    result = qa.answer(query, rerank_backend=rr, api_key=key_in.strip() or None)
            except Exception as e:
                get_logger().exception("[app] answer 실패")
                st.error(f"처리 중 오류: {type(e).__name__}: {e}")
                st.stop()
            # 이번 질문에 사용된 문서(중복 제거, 근거 순서 유지) → 우측 패널이 사용
            st.session_state["keiti_src"] = list(
                dict.fromkeys(s["source_file"] for s in result["sources"]))
            render_answer(result, sess)
    with right:
        st.subheader("📄 문서")
        render_doc_panel(corpus_by_doc, corpus_docs,
                         relevant=st.session_state.get("keiti_src"), key_prefix="keiti_")

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
        st.subheader("✍️ 질문")
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
                with st.spinner("검색 → 리랭킹 → 답변 생성 중..."):
                    hits = upload_pipeline.search(uq, up, key_in.strip() or config.OPENAI_API_KEY,
                                                  top_k=config.TOP_K_RETRIEVE)
                    result = qa.answer(uq, candidates=hits, rerank_backend=rr,
                                       api_key=key_in.strip() or None)
            except Exception as e:
                get_logger().exception("[app] 업로드 answer 실패")
                st.error(f"처리 중 오류: {type(e).__name__}: {e}")
                st.stop()
            st.session_state["upload_src"] = list(
                dict.fromkeys(s["source_file"] for s in result["sources"]))
            render_answer(result, sess)
    with right:
        st.subheader("📄 문서")
        by_doc = defaultdict(list)
        for c in up["chunks"]:
            by_doc[c["source_file"]].append(c)
        render_doc_panel(dict(by_doc), {fn: cs[0] for fn, cs in by_doc.items()},
                         relevant=st.session_state.get("upload_src"), key_prefix="upload_")
