"""Pipeline integration tests — real SQLite demo DB + mocked LLM."""

from __future__ import annotations

import json

import httpx
import pytest
from openai import AsyncOpenAI

from insightkit.audit import AuditLog
from insightkit.config import Config
from insightkit.llm.client import build_client
from insightkit.pipeline import InsightKit

PAID_SQL = "SELECT SUM(amount) AS total FROM orders WHERE status = 'paid'"
COUNT_SQL = "SELECT COUNT(*) AS n FROM orders"


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
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
        },
    )


def make_mock_llm(sql_router) -> tuple[AsyncOpenAI, httpx.MockTransport]:
    """sql_router(last_user_content, messages) -> (sql|None, needs_data)."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        messages = body["messages"]
        last_user = messages[-1]["content"]
        if isinstance(last_user, str) and last_user.startswith("Question:"):
            return _completion("Total paid revenue is 400.")
        sql, needs_data = sql_router(last_user, messages)
        plan = {"sql": sql or "", "reasoning": "r", "needs_data": needs_data}
        return _completion(json.dumps(plan))

    transport = httpx.MockTransport(handler)
    cfg = Config(
        database={"url": "sqlite+aiosqlite:///:memory:"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
    )
    client = build_client(cfg, http_client=httpx.AsyncClient(transport=transport))
    return client, transport


def _kit(demo_db, tmp_path, client) -> InsightKit:
    cfg = Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
        storage={"path": str(tmp_path / "ik")},
    )
    return InsightKit(cfg, client=client)


@pytest.mark.asyncio
async def test_ask_happy_path(demo_db, tmp_path) -> None:
    client, transport = make_mock_llm(lambda content, msgs: (PAID_SQL, True))
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    result = await kit.ask("total revenue?", user="tester", role="analyst")
    assert result.status == "ok"
    assert "400" in result.insight
    assert "orders" in result.sql.lower()
    assert result.row_count == 1
    assert result.latency_ms >= 0

    # audit recorded
    rows = await AuditLog(kit.cfg).query(user="tester")
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    await kit.close()


@pytest.mark.asyncio
async def test_ask_self_corrects_bad_sql(demo_db, tmp_path) -> None:
    calls = {"n": 0}

    def router(content, messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return "SELECT * FROM missing_table", True
        return COUNT_SQL, True

    client, transport = make_mock_llm(router)
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    result = await kit.ask("how many orders?")
    assert result.status == "ok"
    assert "COUNT(*)" in result.sql
    assert result.attempts == 2
    await kit.close()


@pytest.mark.asyncio
async def test_ask_guard_rejects_and_recovers(demo_db, tmp_path) -> None:
    calls = {"n": 0}

    def router(content, messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return "DELETE FROM orders", True
        return PAID_SQL, True

    client, transport = make_mock_llm(router)
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    result = await kit.ask("total revenue?")
    assert result.status == "ok"
    assert "delete" not in result.sql.lower()
    await kit.close()


@pytest.mark.asyncio
async def test_ask_gives_up_after_3_attempts(demo_db, tmp_path) -> None:
    client, transport = make_mock_llm(lambda content, msgs: ("SELECT * FROM missing_table", True))
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    result = await kit.ask("x?")
    assert result.status == "error"
    assert result.error is not None
    assert result.attempts == 3
    await kit.close()


@pytest.mark.asyncio
async def test_ask_no_data_shortcircuits(demo_db, tmp_path) -> None:
    client, transport = make_mock_llm(lambda content, msgs: (None, False))
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    result = await kit.ask("apa warna langit?")
    assert result.status == "no_data"
    assert "cannot be answered" in result.insight
    assert result.sql == ""
    await kit.close()


@pytest.mark.asyncio
async def test_ask_cache_hit(demo_db, tmp_path) -> None:
    calls = {"n": 0}

    def router(content, messages):
        calls["n"] += 1
        return PAID_SQL, True

    client, transport = make_mock_llm(router)
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    first = await kit.ask("total revenue?")
    assert first.cached is False
    second = await kit.ask("total revenue?")
    assert second.cached is True
    assert second.insight == first.insight
    await kit.close()


@pytest.mark.asyncio
async def test_stream_events(demo_db, tmp_path) -> None:
    client, transport = make_mock_llm(lambda content, msgs: (PAID_SQL, True))
    kit = _kit(demo_db, tmp_path, client)
    await kit.init()

    events: list[str] = []

    async def cb(event: str, data: dict) -> None:
        events.append(event)

    await kit.ask("total revenue?", stream=cb)
    assert events[0] == "plan"
    assert "sql" in events
    assert "insight" in events
    assert events[-1] == "done"
    await kit.close()
