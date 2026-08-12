"""OpenAI-compatible LLM client — works with OpenAI, DeepSeek, Ollama, vLLM, etc."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from insightkit.config import Config


class LLMError(RuntimeError):
    """LLM call failed after retries."""


def build_client(cfg: Config, http_client: httpx.AsyncClient | None = None) -> AsyncOpenAI:
    if not cfg.llm.base_url:
        raise LLMError("LLM misconfigured: llm.base_url is empty")
    if not cfg.llm.api_key:
        raise LLMError("LLM misconfigured: llm.api_key is empty")
    return AsyncOpenAI(
        base_url=cfg.llm.base_url,
        api_key=cfg.llm.api_key,
        timeout=cfg.llm.timeout_s,
        max_retries=0,  # we handle retries ourselves with backoff
        http_client=http_client,
    )


async def complete(
    cfg: Config,
    messages: list[dict],
    json_mode: bool = False,
    model: str | None = None,
    client: AsyncOpenAI | None = None,
    max_tokens: int | None = None,
) -> str:
    """Single non-streaming completion with exponential backoff retry."""
    c = client or build_client(cfg)
    kwargs: dict = {"model": model or cfg.llm.model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    last_err: Exception | None = None
    for attempt in range(cfg.llm.max_retries + 1):
        try:
            resp = await c.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError) as exc:
            if isinstance(exc, APIStatusError) and exc.status_code < 500:
                # 4xx — no retry, hard failure
                raise LLMError(f"LLM request failed: {exc}") from exc
            last_err = exc
            if attempt < cfg.llm.max_retries:
                await asyncio.sleep(2**attempt * 0.5)
        except Exception as exc:  # auth/config errors — no retry
            raise LLMError(f"LLM request failed: {exc}") from exc
    raise LLMError(f"LLM request failed after retries: {last_err}")


async def complete_stream(
    cfg: Config,
    messages: list[dict],
    json_mode: bool = False,
    model: str | None = None,
    client: AsyncOpenAI | None = None,
) -> AsyncIterator[str]:
    """Streamed completion — yields content deltas."""
    c = client or build_client(cfg)
    kwargs: dict = {"model": model or cfg.llm.model, "messages": messages, "stream": True}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        stream = await c.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
        raise LLMError(f"LLM stream failed: {exc}") from exc
