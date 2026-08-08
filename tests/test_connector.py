from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from insightkit.config import Config
from insightkit.db.connector import _sqlite_read_only, build_engine, ping


def test_sqlite_read_only_url_transform() -> None:
    assert _sqlite_read_only("sqlite+aiosqlite:///demo.db") == (
        "sqlite+aiosqlite:///file:demo.db?mode=ro&uri=true"
    )
    assert _sqlite_read_only("sqlite+aiosqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"
    # idempotent
    ro = _sqlite_read_only("sqlite+aiosqlite:///demo.db")
    assert _sqlite_read_only(ro) == ro


def test_unsupported_backend() -> None:
    cfg = Config(database={"url": "oracle://user:pass@host/db"})
    with pytest.raises(ValueError, match="Unsupported database backend"):
        build_engine(cfg)


@pytest.mark.asyncio
async def test_engine_read_only_blocks_writes(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    assert await ping(engine) is True
    async with engine.connect() as conn:
        with pytest.raises(OperationalError):  # readonly database
            await conn.execute(text("INSERT INTO customers (id, name) VALUES (99, 'X')"))
            await conn.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_engine_reads_ok(demo_db) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{demo_db}"})
    engine = build_engine(cfg)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM customers"))
        assert result.scalar_one() == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_ping_false_on_bad_db(tmp_path) -> None:
    cfg = Config(database={"url": f"sqlite+aiosqlite:///{tmp_path}/missing.db"})
    engine = build_engine(cfg)  # read-only file: URI — missing file must fail
    with pytest.raises(OperationalError):
        await ping(engine)
    await engine.dispose()
