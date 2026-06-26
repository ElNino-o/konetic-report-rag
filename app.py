"""
⑤ 대국민 화면 (Streamlit 프로토타입 UI)

실행:  streamlit run app.py

두 가지 모드 (사이드바에서 선택):
  1) 질의응답   — 좌: 질문/답변(인용)  우: PDF 목록/본문
  2) 임베딩 비교 — 같은 질문을 bge-m3 vs OpenAI 두 백엔드에 넣어 좌우로 비교
                   (검색 결과·유사도·지연시간, 선택 시 LLM 답변까지)

storage/ 인덱싱 산출물을 자동 로드하므로 별도 업로드가 필요 없다.
질문 입력만으로 전체 문서를 검색한다(국가/분야 필터는 사용하지 않음).
"""
from __future__ import annotations

import json
import os
import time
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

st.set_page_config(page_title="코네틱 국가별보고서, 규제보고서 Q&A", layout="wide")

TYPE_ICON = {"summary": "📌", "body": "📄", "table": "📊",
             "interview": "🎤", "reference": "🔗"}
BACKEND_DIM = {"bge-m3": "1024",
               "openai": str(config.OPENAI_EMBED_DIM or 3072)}


def _local_bge_available() -> bool:
    """로컬 bge-m3(임베딩/리랭크) 사용 가능 여부.
    클라우드(슬림 의존성: torch/sentence-transformers 미설치)에선 False →
    UI 에서 bge-m3·로컬 리랭크·임베딩 비교 모드를 숨겨 배포 에러를 방지한다."""
    import importlib.util
    return importlib.util.find_spec("sentence_transformers") is not None


LOCAL_BGE = _local_bge_available()

# 클라우드에서 bge-m3/local 이 잘못 지정돼도 안전하게 openai 로 고정
if not LOCAL_BGE:
    if config.EMBED_BACKEND == "bge-m3":
        config.EMBED_BACKEND = "openai"
    if config.RERANK_BACKEND == "local":
        config.RERANK_BACKEND = "openai"

from metering import get_logger  # 서버 로깅(storage/streamlit.log)
get_logger().info("[app] 시작 · LOCAL_BGE=%s · 설정요약: %s", LOCAL_BGE, config.summary())


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
    countries = sorted({c["country"] for c in chunks if c.get("country")})
    fields = sorted({c["field"] for c in chunks if c.get("field")})
    return dict(by_doc), docs, countries, fields, len(chunks)


by_doc, docs, countries, fields, n_chunks = load_chunks()


def _path(c: dict) -> str:
    return " > ".join(p for p in [c.get("chapter"), c.get("section"),
                                  c.get("subsection")] if p)


def run_backend(qa, query, filters, backend, want_answer):
    """지정 백엔드로 검색(+리랭킹, 선택 시 답변). config 를 런타임 전환."""
    config.EMBED_BACKEND = backend
    t0 = time.time()
    cands = qa.hybrid_search(query, filters or None)
    top = qa.rerank(query, cands)
    t_ret = time.time() - t0
    ans, t_ans = None, 0.0
    if want_answer and top:
        t1 = time.time()
        ans = qa.generate_answer(query, top)
        t_ans = time.time() - t1
    return top, t_ret, ans, t_ans


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
# 사이드바: 모드 + 백엔드 + 인덱스 상태
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 설정")
    # 임베딩 비교 모드는 로컬(bge-m3 가능)에서만 노출 — 클라우드에선 질의응답만
    mode_opts = ["질의응답"] + (["임베딩 비교"] if LOCAL_BGE else [])
    mode = st.radio("모드", mode_opts)

    if mode == "질의응답":
        if LOCAL_BGE:
            backend = st.radio(
                "임베딩 백엔드", ["bge-m3", "openai"],
                captions=["로컬 BGE-M3 (1024d)", f"OpenAI {config.OPENAI_EMBED_MODEL}"],
                index=0 if config.EMBED_BACKEND == "bge-m3" else 1,
            )
            config.EMBED_BACKEND = backend
        else:
            # 클라우드: OpenAI 임베딩 고정 (bge-m3 선택지 숨김)
            config.EMBED_BACKEND = "openai"
            st.caption(f"임베딩: OpenAI {config.OPENAI_EMBED_MODEL} (고정)")

    # 리랭킹 백엔드: 로컬에선 off/local/openai, 클라우드에선 off/openai
    if LOCAL_BGE:
        RR_OPTS = ["off", "local", "openai"]
        RR_CAP = ["끄기 (가장 빠름)", "로컬 bge-reranker (CPU·느림)",
                  f"OpenAI LLM ({config.OPENAI_RERANK_MODEL})"]
    else:
        RR_OPTS = ["off", "openai"]
        RR_CAP = ["끄기 (가장 빠름)", f"OpenAI LLM ({config.OPENAI_RERANK_MODEL})"]
    rr = st.radio("리랭킹", RR_OPTS, captions=RR_CAP,
                  index=RR_OPTS.index(config.RERANK_BACKEND)
                  if config.RERANK_BACKEND in RR_OPTS else len(RR_OPTS) - 1)
    config.RERANK_BACKEND = rr

    st.divider()
    st.header("📊 인덱스 상태")
    st.metric("문서 수", f"{len(docs)} 건")
    st.metric("청크 수", f"{n_chunks} 개")
    st.caption(f"벡터 저장소: **{config.VECTOR_BACKEND}** · 임베딩 {config.EMBED_BACKEND}")
    st.caption(f"리랭킹: {config.RERANK_BACKEND}")
    st.caption(f"LLM: {config.LLM_BACKEND} · {config.OPENAI_MODEL}")

    # 💰 세션 누적 비용/토큰 모니터
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


def _load_qa():
    try:
        import qa_pipeline
        return qa_pipeline
    except ModuleNotFoundError as e:
        st.error(f"필요 패키지 없음: `{e.name}` — `pip install -r requirements.txt`")
        st.stop()


# ════════════════════════════════════════════════════════
# 모드 1: 질의응답
# ════════════════════════════════════════════════════════
if mode == "질의응답":
    st.caption(f"보고서 {len(docs)}건 자동 로드 · 활성 임베딩 **{config.EMBED_BACKEND}** "
               f"(`{config.collection_name()}`)")
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("① 질문")
        query = st.text_area("자연어 질문", height=100,
                             placeholder="예) 인도네시아 신재생에너지 정책의 핵심 내용은?")
        run = st.button("🔎 검색 · 답변", type="primary", use_container_width=True,
                        disabled=not docs)

        if run and query.strip():
            qa = _load_qa()
            get_logger().info(
                "[app] 질의제출 q=%r | embed=%s vector=%s(%s) rerank=%s",
                query, config.EMBED_BACKEND, config.VECTOR_BACKEND,
                config.collection_name(), config.RERANK_BACKEND)
            with st.spinner("② 검색 → ③ 리랭킹 → ④ 답변 생성..."):
                result = qa.answer(query)          # 전체 문서 대상(필터 없음)

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
                    "비용 세부(USD)": {k: round(v, 6)
                                       for k, v in ug["cost_breakdown"].items()},
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

# ════════════════════════════════════════════════════════
# 모드 2: 임베딩 비교 (bge-m3 vs OpenAI, 좌우 나란히)
# ════════════════════════════════════════════════════════
else:
    st.caption("같은 질문을 두 임베딩에 넣어 검색 품질·속도를 비교합니다.")
    query = st.text_area("자연어 질문", height=80,
                         placeholder="예) 인도네시아 신재생에너지 정책의 핵심 내용은?")
    want_answer = st.checkbox("LLM 답변도 비교", value=False)
    run = st.button("⚖️ 두 임베딩 비교", type="primary", disabled=not docs)

    if run and query.strip():
        qa = _load_qa()

        col_l, col_r = st.columns(2, gap="large")
        for col, be in ((col_l, "bge-m3"), (col_r, "openai")):
            with col:
                st.markdown(f"### {be}  ·  {BACKEND_DIM[be]}d")
                with st.spinner(f"{be} 검색 중..."):
                    try:
                        top, t_ret, ans, t_ans = run_backend(qa, query, None, be, want_answer)
                    except Exception as e:
                        st.error(f"{be} 오류: {type(e).__name__}: {e}")
                        continue
                if not top:
                    st.warning(f"`{config.collection_name()}` 인덱스가 비어 있습니다.\n"
                               f"{'`python build_openai_index.py` 실행 필요' if be=='openai' else '인덱싱 필요'}")
                    continue
                m1, m2 = st.columns(2)
                m1.metric("검색 지연", f"{t_ret:.2f}s")
                m2.metric("상위 점수", f"{top[0]['score']:.3f}")
                if ans is not None:
                    st.markdown("**④ 답변**")
                    st.markdown(ans)
                    st.caption(f"답변 생성 {t_ans:.2f}s")
                    st.divider()
                st.markdown("**📎 검색 근거**")
                render_sources(top)
