"""LLM client + SQL generation tests (httpx MockTransport, no network)."""

from __future__ import annotations

import httpx
import pytest

from insightkit.config import Config
from insightkit.llm.client import LLMError, build_client, complete
from insightkit.llm.sqlgen import SqlGenError, generate_sql, parse_sql_plan


def _mock_client(handler) -> tuple[Config, object]:
    cfg = Config(
        database={"url": "sqlite+aiosqlite:///:memory:"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 1},
    )
    transport = httpx.MockTransport(handler)
    client = build_client(cfg, http_client=httpx.AsyncClient(transport=transport))
    return cfg, client


def _json_response(content: str) -> httpx.Response:
    body = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return httpx.Response(200, json=body)


@pytest.mark.asyncio
async def test_complete_ok() -> None:
    cfg, client = _mock_client(lambda req: _json_response("hello"))
    out = await complete(cfg, [{"role": "user", "content": "hi"}], client=client)
    assert out == "hello"


@pytest.mark.asyncio
async def test_complete_retries_then_fails() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "busy"})

    cfg, client = _mock_client(handler)
    with pytest.raises(LLMError, match="after retries"):
        await complete(cfg, [{"role": "user", "content": "hi"}], client=client)
    assert calls["n"] == 2  # max_retries=1 → 2 attempts


@pytest.mark.asyncio
async def test_complete_4xx_no_retry() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "auth"})

    cfg, client = _mock_client(handler)
    with pytest.raises(LLMError, match="LLM request failed"):
        await complete(cfg, [{"role": "user", "content": "hi"}], client=client)
    assert calls["n"] == 1


def test_parse_sql_plan_plain() -> None:
    plan = parse_sql_plan('{"sql": "SELECT 1", "reasoning": "r", "needs_data": true}')
    assert plan.sql == "SELECT 1"
    assert plan.needs_data is True


def test_parse_sql_plan_fenced() -> None:
    plan = parse_sql_plan('```json\n{"sql": "SELECT 2"}\n```')
    assert plan.sql == "SELECT 2"


def test_parse_sql_plan_stray_text() -> None:
    plan = parse_sql_plan('Sure! Here it is:\n{"sql": "SELECT 3", "needs_data": false}')
    assert plan.sql == "SELECT 3"
    assert plan.needs_data is False


def test_parse_sql_plan_prose_answer() -> None:
    # non-data question: model answered in prose without JSON → non-data answer
    plan = parse_sql_plan(
        "Berikut rekomendasi untuk meningkatkan revenue:\n1. Fokus pada pelanggan kota besar"
    )
    assert plan.sql == ""
    assert plan.needs_data is False
    assert "rekomendasi" in plan.reasoning


def test_parse_sql_plan_invalid() -> None:
    # broken JSON (object started but unparseable) still raises
    with pytest.raises(SqlGenError):
        parse_sql_plan('{"sql": "SELECT oops')


@pytest.mark.asyncio
async def test_generate_sql_end_to_end() -> None:
    cfg, client = _mock_client(lambda req: _json_response('{"sql": "SELECT COUNT(*) FROM orders"}'))
    plan = await generate_sql(cfg, "how many orders?", client=client)
    assert plan.sql == "SELECT COUNT(*) FROM orders"
