"""MySQL E2E — requires a running MySQL (docker: see README of test). Marked e2e."""

from __future__ import annotations

import os

import pytest

from insightkit.config import Config
from insightkit.db.connector import build_engine, ping
from insightkit.db.introspect import introspect

MYSQL_DSN = os.environ.get(
    "INSIGHTKIT_TEST_MYSQL", "mysql+asyncmy://root:root@127.0.0.1:3306/shop"
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mysql_introspect() -> None:
    cfg = Config(database={"url": MYSQL_DSN})
    engine = build_engine(cfg)
    assert await ping(engine) is True

    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="shop", dialect="mysql")

    names = {t.name for t in meta.tables}
    assert {"orders", "customers"} <= names

    orders = meta.table("orders")
    assert orders is not None
    customer_id = orders.column("customer_id")
    assert customer_id is not None and customer_id.fk_ref == "customers.id"
    assert orders.column("amount") is not None

    customers = meta.table("customers")
    assert customers is not None
    assert customers.column("id").is_pk
    await engine.dispose()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mysql_read_only_blocks_write() -> None:
    cfg = Config(database={"url": MYSQL_DSN})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError

        with pytest.raises(OperationalError):
            await conn.execute(text("INSERT INTO customers (id, name) VALUES (99, 'X')"))
            await conn.commit()
    await engine.dispose()
