"""
맥락 단위 청킹 보강 (인덱싱 전용).

A. semantic_split : 긴 본문을 문장 임베딩의 의미 거리 급변 지점에서 분할
                    (한국어 문장 분리는 kiwipiepy, 없으면 정규식 폴백)
B. contextualize  : 각 청크에 LLM(gpt-5.4-nano)이 쓴 1문장 맥락을 부여
                    (Anthropic Contextual Retrieval 방식 — 검색 정확도↑)

둘 다 OpenAI API 를 쓰므로 오프라인 인덱싱 단계에서만 호출한다.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from rag import config
from rag import services
from rag.monitoring import INDEX_COST, get_logger
from rag.services import _openai_client, embed_texts, resolve_key

log = get_logger()


# ── 한국어 문장 분리 ─────────────────────────────────────
def _get_kiwi():
    try:
        from kiwipiepy import Kiwi
        return Kiwi()
    except Exception:
        return None


_KIWI = _get_kiwi()
_SENT_RE = re.compile(r"(?<=[.!?。])\s+|(?<=다)\n|(?<=음)\n|(?<=함)\n|\n{2,}")


def split_sentences(text: str) -> list[str]:
    if _KIWI is not None:
        try:
            return [s.text.strip() for s in _KIWI.split_into_sents(text) if s.text.strip()]
        except Exception:
            pass
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


# ── A. 의미 분할 ─────────────────────────────────────────
def semantic_split(text: str, api_key: str | None = None,
                   max_chars=1500, min_chars=350, pct=82) -> list[str]:
    """긴 본문 → 의미 경계로 분할된 부분 텍스트 리스트."""
    if len(text) <= max_chars:
        return [text]
    sents = split_sentences(text)
    if len(sents) <= 2:
        return _hard_split(text, max_chars)
    vecs = np.asarray(embed_texts(sents, api_key=api_key), dtype=np.float32)
    INDEX_COST.add_embed(services.LAST_EMBED_TOKENS)   # 문장 임베딩 비용 누적
    vecs /= np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12, None)
    dist = 1.0 - np.sum(vecs[:-1] * vecs[1:], axis=1)   # 인접 문장 코사인 거리
    thr = float(np.percentile(dist, pct))
    out, cur = [], sents[0]
    for i in range(1, len(sents)):
        boundary = dist[i - 1] >= thr and len(cur) >= min_chars
        if boundary or len(cur) + len(sents[i]) > max_chars:
            out.append(cur)
            cur = sents[i]
        else:
            cur += " " + sents[i]
    out.append(cur)
    return out


def _hard_split(text, max_chars):
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def apply_semantic_split(chunks: list[dict], api_key: str | None = None,
                         threshold=1500) -> list[dict]:
    """body 청크 중 긴 것만 의미 분할로 재분할."""
    out, n_split = [], 0
    for c in chunks:
        if c["chunk_type"] == "body" and len(c["text"]) > threshold:
            parts = semantic_split(c["text"], api_key=api_key, max_chars=threshold)
            if len(parts) > 1:
                n_split += 1
                for j, p in enumerate(parts):
                    nc = dict(c)
                    nc["text"] = p
                    nc["chunk_id"] = f"{c['chunk_id']}_{j}"
                    out.append(nc)
                continue
        out.append(c)
    log.info("의미 분할: %d개 긴 본문 → 분할, 총 %d청크", n_split, len(out))
    return out


# ── B. Contextual Retrieval (청크별 1문장 맥락) ──────────
_CTX_SYS = ("너는 문서 청크에 검색용 맥락 한 문장을 붙이는 도우미다. "
            "청크가 어떤 보고서의 어느 부분에서 무엇을 다루는지 한국어 한 문장(60자 이내)으로만 답하라.")


def _ctx_one(c: dict, api_key: str) -> str:
    loc = " > ".join(p for p in [c.get("chapter"), c.get("section"), c.get("subsection")] if p)
    user = (f"[보고서] {c.get('country','')} {c.get('title','')}\n"
            f"[위치] {loc}\n[청크]\n{c['text'][:1200]}")
    try:
        r = _openai_client(api_key).chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "system", "content": _CTX_SYS},
                      {"role": "user", "content": user}],
            max_completion_tokens=80,
        )
        u = getattr(r, "usage", None)
        if u:
            INDEX_COST.add_chat(u.prompt_tokens, u.completion_tokens)   # 맥락생성 비용 누적
        return (r.choices[0].message.content or "").strip().replace("\n", " ")
    except Exception as e:
        log.warning("[contextualize] %s", e)
        return ""


def contextualize(chunks: list[dict], api_key: str | None = None, workers=12):
    """각 청크에 c['context'] (LLM 1문장 맥락) 부여. 병렬 호출."""
    key = resolve_key(api_key)
    done = [0]

    def work(c):
        c["context"] = _ctx_one(c, key)
        done[0] += 1
        if done[0] % 200 == 0:
            log.info("맥락 생성 %d/%d", done[0], len(chunks))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, chunks))
    n_empty = sum(1 for c in chunks if not c.get("context"))
    log.info("맥락 생성 완료: %d청크 (실패/빈맥락 %d)", len(chunks), n_empty)
