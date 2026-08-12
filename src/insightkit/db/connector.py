"""Database connectors — async SQLAlchemy, read-only enforced at engine level."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from insightkit.config import Config

SUPPORTED_BACKENDS = frozenset({"postgresql", "mysql", "sqlite"})
_SQLITE_PREFIX = "sqlite+aiosqlite:///"


def _sqlite_read_only(url: str) -> str:
    """Force SQLite file connection into read-only URI mode."""
    if not url.startswith(_SQLITE_PREFIX):
        return url
    path_part = url[len(_SQLITE_PREFIX):]
    if not path_part or path_part == ":memory:" or "mode=ro" in path_part:
        return url
    if path_part.startswith("file:"):
        return url
    sep = "&" if "?" in path_part else "?"
    return f"{_SQLITE_PREFIX}file:{path_part}{sep}mode=ro&uri=true"


def build_engine(cfg: Config) -> AsyncEngine:
    """Create an async engine with read-only enforcement per dialect.

    Layer 1 of the guardrail (layer 2 is query-level checks in security/guard.py).
    """
    raw_url = cfg.database.url.strip()
    if not raw_url:
        raise ValueError("database.url is empty")
    url = _sqlite_read_only(raw_url)
    try:
        parsed = URL.create(url)
    except Exception as exc:
        raise ValueError(f"Invalid database URL: {exc}") from exc
    scheme = parsed.get_backend_name()
    if scheme not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported database backend: {scheme} (supported: postgresql, mysql, sqlite)"
        )

    connect_args: dict = {}
    if scheme == "postgresql":
        connect_args = {"options": "-c default_transaction_read_only=on"}
    elif scheme == "mysql":
        connect_args = {"init_command": "SET SESSION TRANSACTION READ ONLY"}

    return create_async_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
    )


async def ping(engine: AsyncEngine) -> bool:
    """Health check: SELECT 1."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar_one() == 1
