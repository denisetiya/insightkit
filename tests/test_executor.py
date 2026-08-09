"""Executor tests — real SQLite demo DB."""

from __future__ import annotations

import asyncio

import pytest

from insightkit.config import Config
from insightkit.db.connector import build_engine
from insightkit.db.executor import DBError, TableNotFoundError, execute_query


@pytest.mark.asyncio
async def test_execute_query_returns_df(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    df = await execute_query(engine, "SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
    assert df.shape[0] == 3  # paid, pending, refunded
    assert "n" in df.columns
    assert df["n"].sum() == 5
    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_query_empty_result(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    df = await execute_query(engine, "SELECT * FROM customers WHERE id = 999")
    assert df.height == 0
    assert "name" in df.columns
    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_query_missing_table_raises_notfound(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    with pytest.raises(TableNotFoundError):
        await execute_query(engine, "SELECT * FROM nope_table")
    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_query_timeout() -> None:
    """Timeout must raise DBError deterministically (fake slow engine, no zombie thread)."""

    class SlowConn:
        async def __aenter__(self) -> SlowConn:
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def exec_driver_sql(self, sql: str):
            await asyncio.sleep(5)
            raise AssertionError("should never reach here")

    class SlowEngine:
        url = type("U", (), {"get_backend_name": staticmethod(lambda: "sqlite")})()
        def connect(self) -> SlowConn:
            return SlowConn()

    with pytest.raises(DBError, match="timed out"):
        await execute_query(SlowEngine(), "SELECT slow", timeout_s=0.2)
