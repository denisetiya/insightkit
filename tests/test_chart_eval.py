"""Chart + eval tests."""

from __future__ import annotations

import json

import polars as pl
import pytest
from test_pipeline import make_mock_llm

from insightkit.chart import build_chart
from insightkit.config import Config
from insightkit.eval import load_golden, normalize_sql, run_eval


def test_normalize_sql() -> None:
    assert normalize_sql("  SELECT   a   FROM b; ") == "select a from b"


def test_load_golden(tmp_path) -> None:
    f = tmp_path / "g.yml"
    f.write_text(
        "- question: q\n  sql_expected: SELECT 1\n"
        "- question: q2\n  result_keywords: [x, y]\n"
    )
    cases = load_golden(f)
    assert len(cases) == 2
    assert cases[1].result_keywords == ["x", "y"]


def test_build_chart_bar() -> None:
    df = pl.DataFrame({"status": ["paid", "pending"], "n": [4, 1]})
    chart = build_chart(df)
    assert chart is not None
    data = json.loads(chart)
    assert data["data"]  # traces exist


def test_build_chart_none_on_empty() -> None:
    assert build_chart(None) is None
    assert build_chart(pl.DataFrame()) is None
    assert build_chart(pl.DataFrame({"a": [1, 2]})) is None  # single column


@pytest.mark.asyncio
async def test_run_eval_passes(demo_db, tmp_path) -> None:
    def router(content, messages):
        if "paid" in content and "jumlah" not in content:
            return "SELECT SUM(amount) FROM orders WHERE status = 'paid'", True
        if "jumlah orders" in content:
            return "SELECT COUNT(*) FROM orders", True
        return "SELECT SUM(amount) FROM orders WHERE status = 'paid'", True

    client, transport = make_mock_llm(router)
    cfg = Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
        storage={"path": str(tmp_path / "ik")},
    )
    golden = load_golden("tests/golden/orders.yml")
    result = await run_eval(cfg, golden, client=client)
    assert result.score == 1.0
    assert result.total == 3
