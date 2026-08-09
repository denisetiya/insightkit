"""Query executor — run guarded SQL, return polars DataFrame."""

from __future__ import annotations

import asyncio

import polars as pl
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


class DBError(RuntimeError):
    """Query execution failed."""


class TableNotFoundError(DBError):
    """Schema drift: referenced table/column missing — triggers schema refresh."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _statement_timeout_sql(engine: AsyncEngine, timeout_s: float) -> str | None:
    """DB-level statement timeout where supported (kills runaway queries server-side)."""
    scheme = engine.url.get_backend_name()
    if scheme == "postgresql":
        return f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}"
    if scheme == "mysql":
        return f"SET SESSION max_execution_time = {int(timeout_s * 1000)}"
    return None  # sqlite: best-effort via asyncio.wait_for only


async def execute_query(engine: AsyncEngine, sql: str, timeout_s: float = 30.0) -> pl.DataFrame:
    """Run a read-only query; returns a polars DataFrame."""

    async def _run() -> pl.DataFrame:
        async with engine.connect() as conn:
            timeout_sql = _statement_timeout_sql(engine, timeout_s)
            if timeout_sql:
                await conn.execute(text(timeout_sql))
            result = await conn.exec_driver_sql(sql)
            columns = list(result.keys()) if result.keys() else []
            rows = result.fetchall()
            if not columns:
                return pl.DataFrame()
            if not rows:
                return pl.DataFrame(schema=[(c, pl.Utf8) for c in columns])
            data = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
            return pl.DataFrame(data)

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_s)
    except TimeoutError as exc:
        raise DBError(f"Query timed out after {timeout_s}s") from exc
    except OperationalError as exc:
        msg = str(exc).lower()
        if "no such table" in msg or "no such column" in msg or "does not exist" in msg:
            raise TableNotFoundError(str(exc)) from exc
        raise DBError(f"Query execution failed: {exc}") from exc
    except SQLAlchemyError as exc:
        raise DBError(f"Query execution failed: {exc}") from exc
