"""Performance benchmarks — enforce the PRD performance budget.

Budgets (PRD §10):
- cached ask p50 < 100ms
- full pipeline (mock LLM) < 2s
- introspection of 100 tables < 10s
"""

from __future__ import annotations

import asyncio
import sqlite3
import time

import pytest
from test_pipeline import make_mock_llm

from insightkit.config import Config
from insightkit.db.connector import build_engine
from insightkit.db.introspect import introspect
from insightkit.pipeline import InsightKit

PAID_SQL = "SELECT SUM(amount) AS total FROM orders WHERE status = 'paid'"


@pytest.fixture
def big_db(tmp_path) -> str:
    """SQLite DB with 100 small tables."""
    db = tmp_path / "big.db"
    conn = sqlite3.connect(db)
    for i in range(100):
        conn.execute(f"CREATE TABLE t{i} (id INTEGER PRIMARY KEY, name TEXT, value REAL)")
        conn.execute(f"INSERT INTO t{i} (name, value) VALUES ('x', {i}.5)")
    conn.commit()
    conn.close()
    return str(db)


def _cached_ask(demo_db, tmp_path) -> None:
    client, _ = make_mock_llm(lambda content, msgs: (PAID_SQL, True))
    cfg = Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
        storage={"path": str(tmp_path / "ik")},
    )
    kit = InsightKit(cfg, client=client)
    asyncio.run(kit.init())
    try:
        asyncio.run(kit.ask("total revenue?"))  # warm cache
        t0 = time.perf_counter()
        asyncio.run(kit.ask("total revenue?"))
        elapsed = time.perf_counter() - t0
    finally:
        asyncio.run(kit.close())
    assert elapsed < 0.1, f"cached ask took {elapsed * 1000:.0f}ms (budget 100ms)"


def _fresh_ask(demo_db, tmp_path) -> None:
    client, _ = make_mock_llm(lambda content, msgs: (PAID_SQL, True))
    cfg = Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
        storage={"path": str(tmp_path / "ik2")},
    )
    kit = InsightKit(cfg, client=client)
    asyncio.run(kit.init())
    try:
        t0 = time.perf_counter()
        asyncio.run(kit.ask("total revenue?"))
        elapsed = time.perf_counter() - t0
    finally:
        asyncio.run(kit.close())
    assert elapsed < 2.0, f"full pipeline took {elapsed * 1000:.0f}ms (budget 2s)"


def _introspect_big(big_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{big_db}"})
    engine = build_engine(cfg)

    async def _run() -> None:
        async with engine.connect() as conn:
            await introspect(conn, db_key="big", dialect="sqlite")
        await engine.dispose()

    t0 = time.perf_counter()
    asyncio.run(_run())
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"introspection took {elapsed:.1f}s (budget 10s)"


@pytest.mark.benchmark(min_rounds=5, warmup=True)
def test_cached_ask_under_100ms(benchmark, demo_db, tmp_path) -> None:
    benchmark(_cached_ask, demo_db, tmp_path)


@pytest.mark.benchmark(min_rounds=3)
def test_full_pipeline_under_2s(benchmark, demo_db, tmp_path) -> None:
    benchmark(_fresh_ask, demo_db, tmp_path)


@pytest.mark.benchmark(min_rounds=3)
def test_introspect_100_tables_under_10s(benchmark, big_db) -> None:
    benchmark(_introspect_big, big_db)
