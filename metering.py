"""
모니터링: 서버 로깅 + OpenAI 토큰/비용 추정.

- get_logger(): 단계별 처리 로그(검색·리랭크·LLM 시간/토큰)를 stderr 로 출력
  → streamlit 실행 로그(storage/streamlit.log)나 콘솔에서 확인 가능.
- chat_cost / embed_cost: config.PRICES 기반 USD 추정.
"""
from __future__ import annotations

import logging
import sys

import config

_CONFIGURED = False


def get_logger() -> logging.Logger:
    """'rag' 로거를 1회 구성해 반환 (단계별 로그용)."""
    global _CONFIGURED
    log = logging.getLogger("rag")
    if not _CONFIGURED:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s [rag] %(message)s", "%H:%M:%S"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
        _CONFIGURED = True
    return log


# ── 비용 추정 (USD) ─────────────────────────────────────
def chat_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    t = config.PRICES["chat"].get(model, config.PRICES["chat"]["default"])
    return (prompt_tokens * t["in"] + completion_tokens * t["out"]) / 1_000_000


def embed_cost(model: str, tokens: int) -> float:
    rate = config.PRICES["embed"].get(model, config.PRICES["embed"]["default"])
    return tokens * rate / 1_000_000


def usd(x: float) -> str:
    return f"${x:,.6f}"
