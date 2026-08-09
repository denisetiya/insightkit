"""Schema cache round-trip tests."""

from __future__ import annotations

import pytest

from insightkit.config import Config
from insightkit.db.cache import init_meta_db, load_schema, save_schema
from insightkit.db.connector import build_engine
from insightkit.db.introspect import introspect
from insightkit.db.schema import SchemaMetadata


@pytest.mark.asyncio
async def test_schema_cache_roundtrip(demo_db, tmp_path) -> None:
    cfg = Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        storage={"path": str(tmp_path / "ik")},
    )
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        meta = await introspect(conn, db_key="demo", dialect="sqlite")
    await engine.dispose()

    await save_schema(cfg, meta)
    loaded = await load_schema(cfg, "demo")
    assert loaded is not None
    assert [t.name for t in loaded.tables] == [t.name for t in meta.tables]
    orders = loaded.table("orders")
    assert orders is not None
    customer_id = orders.column("customer_id")
    assert customer_id is not None and customer_id.fk_ref == "customers.id"
    assert "paid" in orders.sample.get("status", [])

    # refresh replaces
    meta2 = SchemaMetadata(db_key="demo", dialect="sqlite", tables=[meta.tables[0]])
    await save_schema(cfg, meta2)
    loaded2 = await load_schema(cfg, "demo")
    assert loaded2 is not None and len(loaded2.tables) == 1


@pytest.mark.asyncio
async def test_load_schema_missing(tmp_path) -> None:
    cfg = Config(
        database={"url": "sqlite+aiosqlite:///:memory:"},
        storage={"path": str(tmp_path / "ik")},
    )
    assert await load_schema(cfg, "nope") is None


@pytest.mark.asyncio
async def test_init_meta_db_creates_file(tmp_path) -> None:
    cfg = Config(
        database={"url": "sqlite+aiosqlite:///:memory:"},
        storage={"path": str(tmp_path / "ik")},
    )
    await init_meta_db(cfg)
    assert (tmp_path / "ik" / "meta.db").exists()
