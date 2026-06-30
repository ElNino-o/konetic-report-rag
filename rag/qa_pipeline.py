"""
2. 질의응답 파이프라인 (런타임)

흐름:
  1. 사용자 질의 (자연어)
  2. 하이브리드 검색 (질의 임베딩 · 벡터+키워드)   ← OpenAI 임베딩 · BM25 · 벡터저장소
  3. 리랭킹 (off / openai LLM 리스트와이즈)
  4. LLM 답변 생성 (근거 한정 · 출처·페이지 인용)  ← OpenAI(gpt-5.4-nano)

모니터링: 단계별 처리시간 + OpenAI 토큰/비용 추정을 서버 로그(metering)와
          answer() 반환값(timings/usage)으로 제공.

RAGFlow 대응: rag/nlp/search.py 의 Dealer.retrieval (벡터+BM25 융합 + rerank)
              + insert_citations (인용) 를 단일 파일로 축약.
"""
from __future__ import annotations

import time

from rag import config
from rag import services as common
from rag import monitoring as metering
from rag import vector_store
from rag.services import (
    embed_texts,
    load_bm25,
    simple_tokenize,
)

log = metering.get_logger()
log.info("[qa] 모듈 로드 · 설정요약: %s", config.summary())

# 마지막 OpenAI 호출의 토큰 사용량(모니터링용). (prompt, completion, model)
LAST_RERANK_USAGE: tuple | None = None
LAST_LLM_USAGE: tuple | None = None


# ════════════════════════════════════════════════════════
# 2. 하이브리드 검색 (벡터 + 키워드)
#    - 벡터: 질의 임베딩 → vector_store(chroma/memory/remote) 코사인 검색
#    - 키워드: BM25 점수
#    - 융합: final = w·vector + (1-w)·bm25   (RAGFlow 융합식, 기본 w=0.3)
# ════════════════════════════════════════════════════════
def hybrid_search(query: str, filters: dict | None = None, top_k: int | None = None,
                  api_key: str | None = None):
    top_k = top_k or config.TOP_K_RETRIEVE

    # ── 2-a. 벡터 검색 (저장소 백엔드 추상화) ──
    t0 = time.time()
    qvec = embed_texts([query], api_key=api_key)[0]
    log.info("2. 임베딩(openai) 질의 1건 %.2fs (tokens=%d)",
             time.time() - t0, common.LAST_EMBED_TOKENS)
    hits = vector_store.search(qvec, top_k, filters or None)
    vec_sim = {h["id"]: h["vec_sim"] for h in hits}

    # ── 2-b. BM25 키워드 점수 (영속화된 인덱스 사용) ──
    bm25_sim: dict[str, float] = {}
    store = load_bm25()
    if store is not None:
        scores = store["bm25"].get_scores(simple_tokenize(query))
        id2score = dict(zip(store["ids"], scores))
        mx = max(scores) if len(scores) else 1.0
        mx = mx or 1.0
        for h in hits:
            bm25_sim[h["id"]] = id2score.get(h["id"], 0.0) / mx   # 0~1 정규화

    # ── 2-c. 가중 융합 ──
    w = config.VECTOR_WEIGHT
    fused = []
    for h in hits:
        idx = h["id"]
        score = w * vec_sim.get(idx, 0.0) + (1 - w) * bm25_sim.get(idx, 0.0)
        meta = {k: v for k, v in h.items() if k not in ("vec_sim",)}
        meta["score"] = score
        fused.append(meta)
    fused.sort(key=lambda x: x["score"], reverse=True)
    out = [c for c in fused if c["score"] >= config.SIMILARITY_THRESHOLD] or fused
    log.info("2. 하이브리드 검색(%s): 후보 %d건", config.VECTOR_BACKEND, len(out))
    return out


# ════════════════════════════════════════════════════════
# 3. 리랭킹 (off / openai LLM 리스트와이즈)
# ════════════════════════════════════════════════════════
def _rerank_openai(query, candidates, top_n, api_key=None):
    """OpenAI LLM 리스트와이즈 리랭크 — API 1회로 관련도 순 정렬."""
    global LAST_RERANK_USAGE
    client = common._openai_client(common.resolve_key(api_key))
    listing = "\n".join(
        f"[{i}] {c['text'][:280].strip()}" for i, c in enumerate(candidates)
    )
    msg = [
        {"role": "system", "content":
            "너는 검색 결과 재정렬기다. 질문과 가장 관련 있는 후보를 고른다."},
        {"role": "user", "content":
            f"[질문]\n{query}\n\n[후보]\n{listing}\n\n"
            f"가장 관련 있는 상위 {top_n}개의 번호를 관련도 높은 순으로 "
            f"JSON 정수 배열로만 출력하라. 예: [3,0,5]"},
    ]
    resp = client.chat.completions.create(
        model=config.OPENAI_RERANK_MODEL, messages=msg,
        max_completion_tokens=100,
    )
    u = resp.usage
    LAST_RERANK_USAGE = (u.prompt_tokens, u.completion_tokens, config.OPENAI_RERANK_MODEL)
    import json
    import re
    txt = resp.choices[0].message.content or ""
    try:
        order = json.loads(re.search(r"\[[\d,\s]*\]", txt).group(0))
    except Exception:
        order = list(range(len(candidates)))   # 파싱 실패 시 원순서
    ranked, seen = [], set()
    for rank, i in enumerate(order):
        if isinstance(i, int) and 0 <= i < len(candidates) and i not in seen:
            c = candidates[i]
            c["rerank_score"] = float(len(order) - rank)   # 순위 기반 점수
            ranked.append(c)
            seen.add(i)
    for i, c in enumerate(candidates):        # 누락분 보충
        if i not in seen:
            ranked.append(c)
    return ranked[:top_n]


def rerank(query: str, candidates: list[dict], top_n: int | None = None,
           backend: str | None = None, api_key: str | None = None):
    global LAST_RERANK_USAGE
    LAST_RERANK_USAGE = None
    top_n = top_n or config.TOP_N_RERANK
    be = backend or config.RERANK_BACKEND   # 전역 대신 호출 인자 우선(멀티유저 안전)
    if be != "openai" or not candidates:   # off(또는 미지원) → 융합점수 순서 그대로
        return candidates[:top_n]
    t0 = time.time()
    out = _rerank_openai(query, candidates, top_n, api_key=api_key)
    log.info("3. 리랭킹(%s): %d→%d건 %.2fs%s", be, len(candidates), len(out),
             time.time() - t0,
             f" tokens={LAST_RERANK_USAGE[0]}+{LAST_RERANK_USAGE[1]}"
             if LAST_RERANK_USAGE else "")
    return out


# ════════════════════════════════════════════════════════
# 4. LLM 답변 생성 (근거 한정 + 출처·페이지 인용)
# ════════════════════════════════════════════════════════
SYSTEM_PROMPT = (
    "당신은 환경 정책 보고서 분석 도우미입니다. "
    "반드시 아래 [근거]에 있는 내용만 사용해 한국어로 답하세요. "
    "근거에 없는 내용은 '제공된 자료에서 확인할 수 없습니다'라고 답하세요. "
    "답변 문장 끝에는 사용한 근거의 번호를 [1], [2], [3] 형식으로 표기하세요."
)

# 답변 형태(스타일) — 같은 근거로 서술 수준만 달리한다.
STYLE_GUIDE = {
    "summary": (
        "형식: 핵심만 3문장 이내로 요약하세요. 군더더기 없이 결론 위주로, "
        "각 문장 끝에 근거 번호를 인용하세요."
    ),
    "normal": (
        "형식: 일반 독자가 이해하기 쉽게 핵심을 자연스러운 문단으로 설명하세요. "
        "필요하면 짧은 목록을 써도 됩니다."
    ),
    "expert": (
        "형식: 해당 분야 전문가가 납득할 수준으로 깊고 정밀하게 답하세요. "
        "근거에 나온 구체 수치·정책명·시점·기관명을 명시하고, 항목별로 구조화하며, "
        "함의와 한계(자료가 다루지 않는 부분)까지 짚으세요. 근거 인용을 유지하세요."
    ),
}
DEFAULT_STYLE = "normal"

# 형태별 출력 토큰 상한 — 요약은 짧게(빠름), 전문가는 잘리지 않게 넉넉히.
STYLE_MAX_TOKENS = {
    "summary": 400,
    "normal": 1024,
    "expert": 1600,
}


def _max_tokens(style: str) -> int:
    return STYLE_MAX_TOKENS.get(style, config.LLM_MAX_NEW_TOKENS)


def _system_prompt(style: str) -> str:
    guide = STYLE_GUIDE.get(style)
    return f"{SYSTEM_PROMPT}\n\n{guide}" if guide else SYSTEM_PROMPT


def cite_label(c: dict) -> str:
    """인용 라벨: 제목 p.N · 챕터>섹션 (구조 정보 포함)."""
    title = c.get("title") or c.get("source_file", "")
    path = " > ".join(p for p in [c.get("chapter"), c.get("section"), c.get("subsection")] if p)
    label = f"{title} p.{c.get('page')}"
    return f"{label} · {path}" if path else label


def _build_context(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        lines.append(f"[{i}] ({cite_label(c)})\n{c['text']}")
    return "\n\n".join(lines)


def _request_attempts(messages, max_tokens: int, stream: bool):
    """모델 호환 순서대로 시도할 create() 인자 목록.

    신형(gpt-5 계열): max_completion_tokens + reasoning_effort(낮을수록 빠름).
    구형: max_tokens + temperature. 신형 우선 후 폴백.
    """
    base = {"model": config.OPENAI_MODEL, "messages": messages}
    if stream:
        base["stream"] = True
        base["stream_options"] = {"include_usage": True}
    new_style = {**base, "max_completion_tokens": max_tokens}
    attempts = []
    if config.LLM_REASONING_EFFORT:
        attempts.append({**new_style, "reasoning_effort": config.LLM_REASONING_EFFORT})
    attempts.append(new_style)
    attempts.append({**base, "max_tokens": max_tokens, "temperature": config.LLM_TEMPERATURE})
    return attempts


def _create_with_fallback(client, messages, max_tokens: int, stream: bool):
    from openai import BadRequestError
    last_err = None
    for kw in _request_attempts(messages, max_tokens, stream):
        try:
            return client.chat.completions.create(**kw)
        except BadRequestError as e:
            last_err = e
    raise last_err


def _generate_openai(messages, api_key=None, max_tokens: int | None = None) -> str:
    """OpenAI API(비스트리밍). 키는 세션(BYOK) 또는 .env/secrets 에서 로드."""
    global LAST_LLM_USAGE
    client = common._openai_client(common.resolve_key(api_key))
    resp = _create_with_fallback(client, messages,
                                 max_tokens or config.LLM_MAX_NEW_TOKENS, stream=False)
    u = resp.usage
    LAST_LLM_USAGE = (u.prompt_tokens, u.completion_tokens, config.OPENAI_MODEL)
    return resp.choices[0].message.content


def _stream_openai(messages, api_key=None, max_tokens: int | None = None):
    """OpenAI API(스트리밍). 토큰 조각을 yield 하고, 종료 시 사용량을 기록한다."""
    global LAST_LLM_USAGE
    client = common._openai_client(common.resolve_key(api_key))
    stream = _create_with_fallback(client, messages,
                                   max_tokens or config.LLM_MAX_NEW_TOKENS, stream=True)
    usage = None
    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    if usage:
        LAST_LLM_USAGE = (usage.prompt_tokens, usage.completion_tokens, config.OPENAI_MODEL)


def _extractive_answer(query: str, chunks: list[dict]) -> str:
    """LLM 호출 실패 시 폴백: 상위 근거 발췌 + 인용 번호만 제시."""
    lines = ["⚠️ *LLM 호출에 실패해 검색된 근거를 발췌해 보여줍니다.*", ""]
    for i, c in enumerate(chunks, 1):
        snippet = c["text"].strip().replace("\n", " ")
        snippet = (snippet[:300] + "…") if len(snippet) > 300 else snippet
        lines.append(f"- {snippet} [{i}]")
    return "\n".join(lines)


def generate_answer(query: str, chunks: list[dict], api_key: str | None = None,
                    style: str = DEFAULT_STYLE) -> str:
    global LAST_LLM_USAGE
    LAST_LLM_USAGE = None
    if not chunks:
        return "관련 근거를 찾지 못했습니다."
    messages = [
        {"role": "system", "content": _system_prompt(style)},
        {"role": "user", "content": f"[질문]\n{query}\n\n[근거]\n{_build_context(chunks)}"},
    ]
    try:
        return _generate_openai(messages, api_key=api_key, max_tokens=_max_tokens(style))
    except Exception as e:
        # 네트워크/키 오류 등 → 발췌형 폴백으로 결과는 항상 보여준다
        log.warning("[LLM 폴백] %s: %s", type(e).__name__, e)
        return _extractive_answer(query, chunks)


def generate_answer_stream(query: str, chunks: list[dict], api_key: str | None = None,
                           style: str = DEFAULT_STYLE):
    """스트리밍 답변 생성기 — 토큰 조각을 yield. UI 의 st.write_stream 에서 사용."""
    global LAST_LLM_USAGE
    LAST_LLM_USAGE = None
    if not chunks:
        yield "관련 근거를 찾지 못했습니다."
        return
    messages = [
        {"role": "system", "content": _system_prompt(style)},
        {"role": "user", "content": f"[질문]\n{query}\n\n[근거]\n{_build_context(chunks)}"},
    ]
    try:
        yield from _stream_openai(messages, api_key=api_key, max_tokens=_max_tokens(style))
    except Exception as e:
        log.warning("[LLM 스트림 폴백] %s: %s", type(e).__name__, e)
        yield _extractive_answer(query, chunks)


# ════════════════════════════════════════════════════════
# 💰 비용/토큰 집계 (마지막 호출 기준)
# ════════════════════════════════════════════════════════
def _collect_usage() -> dict:
    """이번 질의의 임베딩·리랭크·LLM 토큰과 추정 비용(USD)을 집계."""
    embed_tok = common.LAST_EMBED_TOKENS
    embed_usd = metering.embed_cost(config.OPENAI_EMBED_MODEL, embed_tok)
    rr = LAST_RERANK_USAGE
    rr_usd = metering.chat_cost(rr[2], rr[0], rr[1]) if rr else 0.0
    lm = LAST_LLM_USAGE
    lm_usd = metering.chat_cost(lm[2], lm[0], lm[1]) if lm else 0.0
    return {
        "embed_tokens": embed_tok,
        "rerank_tokens": (rr[0] + rr[1]) if rr else 0,
        "llm_prompt_tokens": lm[0] if lm else 0,
        "llm_completion_tokens": lm[1] if lm else 0,
        "cost_usd": embed_usd + rr_usd + lm_usd,
        "cost_breakdown": {"embed": embed_usd, "rerank": rr_usd, "llm": lm_usd},
    }


def collect_full_usage() -> dict:
    """이번 질의의 임베딩+리랭크+LLM 사용량(새 질문용)."""
    return _collect_usage()


def collect_llm_usage() -> dict:
    """LLM 호출분만 집계(근거 재사용·형태 전환용 — 검색/리랭크 비용 0)."""
    lm = LAST_LLM_USAGE
    lm_usd = metering.chat_cost(lm[2], lm[0], lm[1]) if lm else 0.0
    return {
        "embed_tokens": 0, "rerank_tokens": 0,
        "llm_prompt_tokens": lm[0] if lm else 0,
        "llm_completion_tokens": lm[1] if lm else 0,
        "cost_usd": lm_usd,
        "cost_breakdown": {"embed": 0.0, "rerank": 0.0, "llm": lm_usd},
    }


# ════════════════════════════════════════════════════════
# 검색+리랭크만 수행(답변 생성 분리) — 스트리밍 UI 에서 근거를 먼저 확보
# ════════════════════════════════════════════════════════
def search_rerank(query: str, filters: dict | None = None, rerank_backend: str | None = None,
                  api_key: str | None = None, candidates: list[dict] | None = None) -> dict:
    """검색→리랭크까지 수행하고 근거(sources)와 단계별 시간을 돌려준다.

    candidates 를 주면(업로드 모드) 벡터검색을 건너뛴다. 임베딩/리랭크 사용량은
    전역에 기록되어, 이후 collect_full_usage() 가 LLM 사용량과 합산한다.
    """
    be = rerank_backend or config.RERANK_BACKEND
    t = {}
    if candidates is None:
        t0 = time.time()
        candidates = hybrid_search(query, filters, api_key=api_key)
        t["retrieve"] = time.time() - t0
    else:
        t["retrieve"] = 0.0
    t0 = time.time()
    top = rerank(query, candidates, backend=be, api_key=api_key)
    t["rerank"] = time.time() - t0
    return {"sources": top, "timings": t}


# ════════════════════════════════════════════════════════
# 오케스트레이터: 1. → 2. → 3. → 4. (+ 시간/토큰/비용 모니터링)
# ════════════════════════════════════════════════════════
def generate_only(query: str, chunks: list[dict], style: str = DEFAULT_STYLE,
                  api_key: str | None = None) -> dict:
    """이미 검색·리랭크된 근거(chunks)를 재사용해 답변만 다시 생성한다.

    검색/임베딩/리랭크를 건너뛰므로 비용은 이번 LLM 호출분만 발생한다.
    답변 형태(style) 전환 버튼에서 사용한다.
    """
    global LAST_LLM_USAGE
    LAST_LLM_USAGE = None
    t0 = time.time()
    text = generate_answer(query, chunks, api_key=api_key, style=style)
    llm_t = time.time() - t0
    lm = LAST_LLM_USAGE
    lm_usd = metering.chat_cost(lm[2], lm[0], lm[1]) if lm else 0.0
    usage = {
        "embed_tokens": 0,
        "rerank_tokens": 0,
        "llm_prompt_tokens": lm[0] if lm else 0,
        "llm_completion_tokens": lm[1] if lm else 0,
        "cost_usd": lm_usd,
        "cost_breakdown": {"embed": 0.0, "rerank": 0.0, "llm": lm_usd},
    }
    log.info("4'. 답변 재생성(style=%s) %.2fs | llm 토큰 %d+%d | 추정비용 %s",
             style, llm_t, usage["llm_prompt_tokens"], usage["llm_completion_tokens"],
             metering.usd(lm_usd))
    return {"answer": text, "usage": usage, "llm_time": llm_t}


def answer(query: str, filters: dict | None = None, rerank_backend: str | None = None,
           api_key: str | None = None, candidates: list[dict] | None = None,
           style: str = DEFAULT_STYLE):
    """질의응답. candidates 를 주면(업로드 모드) 벡터검색을 건너뛰고 재사용한다."""
    be = rerank_backend or config.RERANK_BACKEND
    log.info("─" * 8 + " 질의: %r (embed=openai, rerank=%s, llm=%s)",
             query, be, config.OPENAI_MODEL)
    t = {}
    if candidates is None:
        t0 = time.time()
        candidates = hybrid_search(query, filters, api_key=api_key)
        t["retrieve"] = time.time() - t0
    else:
        t["retrieve"] = 0.0                            # 업로드: 세션 검색은 호출측에서 수행

    t0 = time.time()
    top = rerank(query, candidates, backend=be, api_key=api_key)
    t["rerank"] = time.time() - t0

    t0 = time.time()
    text = generate_answer(query, top, api_key=api_key, style=style)
    t["llm"] = time.time() - t0

    usage = _collect_usage()
    t["total"] = t["retrieve"] + t["rerank"] + t["llm"]
    log.info("4. 답변 완료 %.2fs (검색 %.2f · 리랭크 %.2f · LLM %.2f) | "
             "토큰 embed=%d rerank=%d llm=%d+%d | 추정비용 %s",
             t["total"], t["retrieve"], t["rerank"], t["llm"],
             usage["embed_tokens"], usage["rerank_tokens"],
             usage["llm_prompt_tokens"], usage["llm_completion_tokens"],
             metering.usd(usage["cost_usd"]))
    return {"answer": text, "sources": top, "timings": t, "usage": usage}


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "주요 결론을 요약해줘"
    out = answer(q)
    print("\n=== 답변 ===\n", out["answer"])
    print("\n=== 근거 ===")
    for i, s in enumerate(out["sources"], 1):
        print(f"[{i}] {s.get('title')} p.{s.get('page')} (score={s['score']:.3f})")
    print("\n=== 모니터링 ===")
    print("시간:", {k: round(v, 2) for k, v in out["timings"].items()})
    print("토큰/비용:", out["usage"])
