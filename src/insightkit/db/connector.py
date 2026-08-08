"""Database connectors — async SQLAlchemy, read-only enforced at engine level."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from insightkit.config import Config


def _sqlite_read_only(url: str) -> str:
    """Force SQLite file connection into read-only URI mode."""
    if "mode=ro" in url or ":memory:" in url:
        return url
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return url
    rest = url[len(prefix) :]
    sep = "?" if "?" not in rest else "&"
    return f"{prefix}file:{rest}{sep}mode=ro&uri=true"


def build_engine(cfg: Config) -> AsyncEngine:
    """Create an async engine with read-only enforcement per dialect.

    Layer 1 of the guardrail (layer 2 is query-level checks in security/guard.py).
    """
    url = _sqlite_read_only(cfg.database.url)
    parsed = URL.create(url)
    scheme = parsed.get_backend_name()
    if scheme not in {"postgresql", "mysql", "sqlite"}:
        raise ValueError(
            f"Unsupported database backend: {scheme} (supported: postgresql, mysql, sqlite)"
        )

    connect_args: dict = {}
    if scheme == "postgresql":
        connect_args = {"options": "-c default_transaction_read_only=on"}
    elif scheme == "mysql":
        connect_args = {"init_command": "SET SESSION TRANSACTION READ ONLY"}

    return create_async_engine(
        url, connect_args=connect_args, pool_pre_ping=True, pool_recycle=1800
    )


async def ping(engine: AsyncEngine) -> bool:
    """Health check: SELECT 1."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar_one() == 1
