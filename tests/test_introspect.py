from __future__ import annotations

import pytest

from insightkit.config import Config
from insightkit.db.connector import build_engine
from insightkit.db.introspect import introspect


@pytest.mark.asyncio
async def test_introspect_sqlite_full(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="demo", dialect="sqlite")

    assert meta.dialect == "sqlite"
    names = [t.name for t in meta.tables]
    assert "orders" in names and "customers" in names

    orders = meta.table("orders")
    assert orders is not None
    amount = orders.column("amount")
    assert amount is not None and amount.data_type.upper() == "REAL"

    customer_id = orders.column("customer_id")
    assert customer_id is not None and customer_id.fk_ref == "customers.id"

    status = orders.column("status")
    assert status is not None
    assert "paid" in orders.sample.get("status", [])

    customers = meta.table("customers")
    assert customers is not None
    id_col = customers.column("id")
    assert id_col is not None and id_col.is_pk

    await engine.dispose()


@pytest.mark.asyncio
async def test_introspect_row_counts(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="demo", dialect="sqlite")
    assert meta.table("orders").row_count == 5
    assert meta.table("customers").row_count == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_render_summary(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="demo", dialect="sqlite")
    summary = meta.render()
    assert "TABLE orders" in summary
    assert "status" in summary
    assert "samples:" in summary
    assert "customers.id" in summary  # FK rendered
    await engine.dispose()
