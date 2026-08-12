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
    """Schema drift: referenced table/column missing, triggers schema refresh."""

    def __init__(self, message: str, table: str | None = None) -> None:
        super().__init__(message)
        self.table = table


_MAX_FETCH_ROWS = 10_000
_MISSING_TABLE_HINTS = frozenset(
    {
        "no such table",
        "no such column",
        "does not exist",
        "undefined table",
        "unknown table",
        "doesn't exist",
    }
)


def _is_missing_table(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in _MISSING_TABLE_HINTS)


def _statement_timeout_sql(engine: AsyncEngine, timeout_s: float) -> str | None:
    """DB-level statement timeout where supported (kills runaway queries server-side)."""
    scheme = engine.url.get_backend_name()
    timeout_ms = max(1, int(timeout_s * 1000))
    if scheme == "postgresql":
        return f"SET LOCAL statement_timeout = {timeout_ms}"
    if scheme == "mysql":
        return f"SET SESSION max_execution_time = {timeout_ms}"
    return None


async def execute_query(engine: AsyncEngine, sql: str, timeout_s: float = 30.0) -> pl.DataFrame:
    """Run a read-only query; returns a polars DataFrame."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise DBError("Empty SQL statement")
    if timeout_s <= 0:
        raise DBError("timeout_s must be positive")

    async def _run() -> pl.DataFrame:
        async with engine.connect() as conn:
            timeout_sql = _statement_timeout_sql(engine, timeout_s)
            if timeout_sql:
                await conn.execute(text(timeout_sql))
            result = await conn.exec_driver_sql(cleaned)
            keys = result.keys()
            columns = list(keys) if keys else []
            if not columns:
                return pl.DataFrame()
            rows = result.fetchmany(_MAX_FETCH_ROWS)
            if not rows:
                return pl.DataFrame(schema=[(c, pl.Utf8) for c in columns])
            return pl.DataFrame(
                {c: [r[i] for r in rows] for i, c in enumerate(columns)},
                orient="col",
            )

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_s)
    except (TimeoutError, asyncio.CancelledError) as exc:
        raise DBError(f"Query timed out after {timeout_s}s") from exc
    except OperationalError as exc:
        if _is_missing_table(str(exc)):
            raise TableNotFoundError(str(exc)) from exc
        raise DBError("Query execution failed") from exc
    except SQLAlchemyError as exc:
        if _is_missing_table(str(exc)):
            raise TableNotFoundError(str(exc)) from exc
        raise DBError("Query execution failed") from exc
