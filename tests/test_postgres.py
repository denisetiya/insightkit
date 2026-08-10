"""PostgreSQL E2E — requires a running Postgres with shop data (see seed_pg.py)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from insightkit.config import Config
from insightkit.db.connector import build_engine, ping
from insightkit.db.introspect import introspect

PG_DSN = os.environ.get(
    "INSIGHTKIT_TEST_PG", "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/shop"
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pg_introspect() -> None:
    cfg = Config(database={"url": PG_DSN})
    engine = build_engine(cfg)
    assert await ping(engine) is True

    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="shop", dialect="postgresql")

    names = {t.name for t in meta.tables}
    assert {"orders", "customers"} <= names
    orders = meta.table("orders")
    assert orders is not None
    customer_id = orders.column("customer_id")
    assert customer_id is not None and customer_id.fk_ref == "customers.id"
    assert orders.column("amount") is not None
    assert orders.row_count == 10_000
    await engine.dispose()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pg_read_only_blocks_write() -> None:
    cfg = Config(database={"url": PG_DSN})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        with pytest.raises(SQLAlchemyError):
            await conn.execute(text("INSERT INTO customers (name) VALUES ('x')"))
            await conn.commit()
    await engine.dispose()
