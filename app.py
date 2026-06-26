"""
⑤ 대국민 화면 (Streamlit) — OpenAI 전용

실행:  streamlit run app.py

- 좌: 질문 입력 → 답변(출처·페이지 인용) + 처리시간·토큰·비용
- 우: PDF 목록 + 선택 PDF 의 구조 인식 청크
storage/ 인덱싱 산출물을 자동 로드하므로 별도 업로드가 필요 없다.
임베딩·리랭크·LLM 은 모두 OpenAI API 로 처리한다(로컬 모델 없음).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import streamlit as st

# Streamlit Cloud 배포: st.secrets 값을 환경변수로 주입(config import 전에).
# 로컬에선 .env(python-dotenv)가 쓰이고, 클라우드에선 secrets 가 채워진다.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

import config
from metering import get_logger

st.set_page_config(page_title="코네틱 국가별보고서, 규제보고서 Q&A", layout="wide")
get_logger().info("[app] 시작 · 설정요약: %s", config.summary())

TYPE_ICON = {"summary": "📌", "body": "📄", "table": "📊",
             "interview": "🎤", "reference": "🔗"}


# ── 인덱싱 산출물(청크 백업) 자동 로드 ───────────────────
@st.cache_data
def load_chunks():
    chunks = []
    if config.CHUNK_DUMP.exists():
        with open(config.CHUNK_DUMP, encoding="utf-8") as f:
            for line in f:
                chunks.append(json.loads(line))
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c["source_file"]].append(c)
    docs = {fn: cs[0] for fn, cs in by_doc.items()}
    return dict(by_doc), docs, len(chunks)


by_doc, docs, n_chunks = load_chunks()


def _path(c: dict) -> str:
    return " > ".join(p for p in [c.get("chapter"), c.get("section"),
                                  c.get("subsection")] if p)


def render_sources(sources):
    for i, s in enumerate(sources, 1):
        with st.expander(
            f"[{i}] {s.get('title')} · p.{s.get('page')} · "
            f"{s.get('chunk_type','')} (score={s['score']:.3f})"
        ):
            if _path(s):
                st.caption(f"📑 {_path(s)}")
            st.write(s["text"])
            st.caption(f"출처: {s.get('doc_source','')} | 파일: {s.get('source_file','')}")


# ════════════════════════════════════════════════════════
# 사이드바: 리랭킹 + 인덱스 상태 + 세션 비용
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 설정")
    RR_OPTS = ["off", "openai"]
    rr = st.radio("리랭킹", RR_OPTS,
                  captions=["끄기 (가장 빠름)", f"OpenAI LLM ({config.OPENAI_RERANK_MODEL})"],
                  index=RR_OPTS.index(config.RERANK_BACKEND)
                  if config.RERANK_BACKEND in RR_OPTS else 1)
    config.RERANK_BACKEND = rr

    st.divider()
    st.header("📊 인덱스 상태")
    st.metric("문서 수", f"{len(docs)} 건")
    st.metric("청크 수", f"{n_chunks} 개")
    st.caption(f"벡터 저장소: **{config.VECTOR_BACKEND}** · `{config.collection_name()}`")
    st.caption(f"임베딩: OpenAI {config.OPENAI_EMBED_MODEL}")
    st.caption(f"리랭킹: {config.RERANK_BACKEND} · LLM: {config.OPENAI_MODEL}")

    sess = st.session_state.setdefault("usage_total",
                                       {"cost": 0.0, "queries": 0, "tokens": 0})
    st.divider()
    st.header("💰 세션 비용")
    st.metric("누적 추정 비용", f"${sess['cost']:.4f}")
    st.caption(f"질의 {sess['queries']}건 · 누적 토큰 {sess['tokens']:,}")

    if st.button("🔄 인덱스 다시 불러오기"):
        # 청크 + 벡터 저장소 캐시를 모두 비운다(다른 프로세스가 인덱스를 갱신한
        # 경우 stale 한 Chroma/npz 핸들을 버리고 새로 로드).
        load_chunks.clear()
        try:
            import common
            import vector_store
            common.get_chroma_collection.cache_clear()
            common.get_chroma_client.cache_clear()
            vector_store._load_memory.cache_clear()
            get_logger().info("[app] 인덱스 캐시 초기화(재로딩)")
        except Exception as e:
            get_logger().warning("[app] 캐시 초기화 실패: %s", e)
        st.rerun()

st.title("🌏 코네틱 국가별보고서, 규제보고서 Q&A")
st.caption(f"보고서 {len(docs)}건 자동 로드 · 임베딩/리랭크/LLM 모두 OpenAI "
           f"(`{config.collection_name()}`)")


def _load_qa():
    try:
        import qa_pipeline
        return qa_pipeline
    except ModuleNotFoundError as e:
        st.error(f"필요 패키지 없음: `{e.name}`")
        st.stop()


# ════════════════════════════════════════════════════════
# 좌: 질문/답변   우: PDF 목록/본문
# ════════════════════════════════════════════════════════
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("① 질문")
    query = st.text_area("자연어 질문", height=100,
                         placeholder="예) 폴란드 이차전지 시장 동향을 알려줘")
    run = st.button("🔎 검색 · 답변", type="primary", use_container_width=True,
                    disabled=not docs)

    if run and query.strip():
        qa = _load_qa()
        get_logger().info("[app] 질의제출 q=%r | vector=%s(%s) rerank=%s",
                          query, config.VECTOR_BACKEND, config.collection_name(),
                          config.RERANK_BACKEND)
        try:
            with st.spinner("② 검색 → ③ 리랭킹 → ④ 답변 생성..."):
                result = qa.answer(query)      # 전체 문서 대상(필터 없음)
        except Exception as e:
            get_logger().exception("[app] answer 실패")
            st.error(f"처리 중 오류가 발생했습니다: {type(e).__name__}: {e}\n\n"
                     "OpenAI 키/네트워크 또는 인덱스 상태를 확인하세요.")
            st.stop()

        # ⏱️/💰 모니터링: 처리시간 + 토큰/비용 (서버 로그에도 기록됨)
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
            st.json({
                "임베딩 토큰": ug["embed_tokens"],
                "리랭크 토큰": ug["rerank_tokens"],
                "LLM 토큰(prompt/completion)":
                    f"{ug['llm_prompt_tokens']} / {ug['llm_completion_tokens']}",
                "비용 세부(USD)": {k: round(v, 6) for k, v in ug["cost_breakdown"].items()},
            })

        st.subheader("④ 답변")
        st.markdown(result["answer"])
        st.subheader("📎 근거 (출처 · 페이지)")
        render_sources(result["sources"])

with right:
    st.subheader("📚 PDF 목록")
    if not docs:
        st.info("인덱싱된 문서가 없습니다. `python index_pipeline.py` 실행 후 새로고침.")
    else:
        labels = {fn: f"{m.get('title', fn)} · {m.get('country','')}/{m.get('year','')}"
                  for fn, m in docs.items()}
        sel_pdf = st.selectbox("PDF 선택", list(docs.keys()),
                               format_func=lambda fn: labels[fn])
        meta = docs[sel_pdf]
        st.markdown(f"**{meta.get('title')}**  \n국가: {meta.get('country')} · "
                    f"발행연도: {meta.get('year')} · 분야: {meta.get('field')} · "
                    f"출처: {meta.get('doc_source')}")
        if meta.get("tags"):
            st.caption(f"🏷️ {meta['tags']}")
        st.divider()
        st.caption("선택한 PDF 내용 (구조 인식 청크)")
        for c in sorted(by_doc[sel_pdf], key=lambda x: (int(x["page"]), x["chunk_id"])):
            icon = TYPE_ICON.get(c["chunk_type"], "•")
            with st.expander(f"{icon} p.{c['page']} · {c['chunk_type']} — "
                             f"{_path(c) or c['chunk_id']}"):
                if c.get("table_title"):
                    st.caption(f"📊 {c['table_title']}")
                st.write(c["text"])
                if c.get("footnotes"):
                    st.caption("각주: " + " / ".join(c["footnotes"]))
