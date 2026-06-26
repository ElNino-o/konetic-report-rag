"""
모니터링: 서버 로깅 + OpenAI 토큰/비용 추정.

- get_logger(): 단계별 처리 로그(검색·리랭크·LLM 시간/토큰)를 stderr 로 출력
  → streamlit 실행 로그(storage/streamlit.log)나 콘솔에서 확인 가능.
- chat_cost / embed_cost: config.PRICES 기반 USD 추정.
"""
from __future__ import annotations

import logging
import sys

from rag import config

_CONFIGURED = False


def get_logger() -> logging.Logger:
    """'rag' 로거를 1회 구성해 반환 (단계별 로그용). LOG_LEVEL 로 상세도 조절."""
    global _CONFIGURED
    log = logging.getLogger("rag")
    if not _CONFIGURED:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(
            "%(asctime)s [rag:%(levelname)s] %(message)s", "%H:%M:%S"))
        log.addHandler(h)
        log.setLevel(getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO))
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


# ── 인덱싱 비용 누적기 (오프라인 1회 인덱싱용) ───────────
class IndexCost:
    """인덱싱 단계의 임베딩·LLM(맥락생성) 토큰/비용을 누적해 합산 로깅한다."""

    def __init__(self):
        self.embed_tokens = 0
        self.chat_prompt = 0
        self.chat_completion = 0
        self.chat_calls = 0

    def add_embed(self, tokens: int):
        self.embed_tokens += int(tokens or 0)

    def add_chat(self, prompt: int, completion: int):
        self.chat_prompt += int(prompt or 0)
        self.chat_completion += int(completion or 0)
        self.chat_calls += 1

    @property
    def usd(self) -> float:
        return (embed_cost(config.OPENAI_EMBED_MODEL, self.embed_tokens)
                + chat_cost(config.OPENAI_MODEL, self.chat_prompt, self.chat_completion))

    def log(self, log_, label: str = "인덱싱 누적 비용"):
        log_.info("💰 %s: 임베딩 %s토큰 · 맥락LLM %d호출(%s+%s) · 추정 %s",
                  label, f"{self.embed_tokens:,}", self.chat_calls,
                  f"{self.chat_prompt:,}", f"{self.chat_completion:,}", usd(self.usd))


# 인덱싱 실행 동안 공유되는 단일 누적기
INDEX_COST = IndexCost()
