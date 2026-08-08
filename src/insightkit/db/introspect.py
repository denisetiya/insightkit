"""Introspection — extract SchemaMetadata from a live database connection."""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from insightkit.db.schema import (
    DATE_TYPES,
    NUMERIC_TYPES,
    ColumnMeta,
    SchemaMetadata,
    TableMeta,
)

_SAMPLE_LIMIT = 20
_COUNT_LIMIT = 100_000_000


async def _table_names_pg(conn: AsyncConnection) -> list[str]:
    rows = await conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
    )
    return [r[0] for r in rows]


async def _columns_pg(conn: AsyncConnection) -> dict[str, list[ColumnMeta]]:
    rows = await conn.execute(
        text(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
        )
    )
    out: dict[str, list[ColumnMeta]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        out.setdefault(table_name, []).append(
            ColumnMeta(name=column_name, data_type=data_type, nullable=is_nullable == "YES")
        )
    return out


async def _fks_pg(conn: AsyncConnection) -> dict[str, dict[str, str]]:
    rows = await conn.execute(
        text(
            "SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "ON tc.constraint_name = ccu.constraint_name AND ccu.table_schema = tc.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY'"
        )
    )
    out: dict[str, dict[str, str]] = {}
    for table_name, column_name, ref_table, ref_column in rows:
        out.setdefault(table_name, {})[column_name] = f"{ref_table}.{ref_column}"
    return out


async def _row_counts_pg(conn: AsyncConnection) -> dict[str, int]:
    """Fast estimate from pg_class.reltuples (no COUNT(*) on big tables)."""
    rows = await conn.execute(
        text(
            "SELECT relname, reltuples::bigint FROM pg_class "
            "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace"
        )
    )
    return {name: count for name, count in rows if count >= 0}


async def _table_names_sqlite(conn: AsyncConnection) -> list[str]:
    rows = await conn.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    return [r[0] for r in rows]


async def _columns_sqlite(conn: AsyncConnection, tables: list[str]) -> dict[str, list[ColumnMeta]]:
    out: dict[str, list[ColumnMeta]] = {}
    for t in tables:
        pragma = await conn.execute(text(f'PRAGMA table_info("{t}")'))
        cols: list[ColumnMeta] = []
        for _cid, name, ctype, notnull, _dflt, pk in pragma:
            cols.append(
                ColumnMeta(
                    name=name,
                    data_type=ctype or "TEXT",
                    nullable=not bool(notnull),
                    is_pk=bool(pk),
                )
            )
        out[t] = cols
    return out


async def _fks_sqlite(conn: AsyncConnection, tables: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for t in tables:
        pragma = await conn.execute(text(f'PRAGMA foreign_key_list("{t}")'))
        refs: dict[str, str] = {}
        for row in pragma:
            # row: id, seq, table, from, to, on_update, on_delete, match
            refs[row[3]] = f"{row[2]}.{row[4] or 'id'}"
        if refs:
            out[t] = refs
    return out


async def _row_counts_sqlite(conn: AsyncConnection, tables: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in tables:
        row = await conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
        out[t] = int(row.scalar_one())
    return out


async def _samples(conn: AsyncConnection, tables: list[TableMeta]) -> None:
    """Sample distinct values for categorical columns (non-numeric, non-date)."""

    async def one(t: TableMeta, c: ColumnMeta) -> None:
        q = f'SELECT DISTINCT "{c.name}" FROM "{t.name}" LIMIT {_SAMPLE_LIMIT}'
        rows = await conn.execute(text(q))
        vals = [str(r[0]) for r in rows if r[0] is not None]
        if vals:
            t.sample[c.name] = vals

    tasks = []
    for t in tables:
        for c in t.columns:
            base = c.data_type.lower()
            if base in NUMERIC_TYPES or base in DATE_TYPES or base.startswith("bool"):
                continue
            tasks.append(one(t, c))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _apply_fks(tables: list[TableMeta], fks: dict[str, dict[str, str]]) -> None:
    for t in tables:
        refs = fks.get(t.name, {})
        for c in t.columns:
            if c.name in refs:
                c.fk_ref = refs[c.name]


async def introspect(conn: AsyncConnection, db_key: str, dialect: str) -> SchemaMetadata:
    """Full introspection: tables, columns, FKs, row counts (parallel), samples."""
    if dialect == "postgresql":
        names, cols, fks, counts = await asyncio.gather(
            _table_names_pg(conn), _columns_pg(conn), _fks_pg(conn), _row_counts_pg(conn)
        )
    elif dialect == "sqlite":
        names = await _table_names_sqlite(conn)
        cols, fks, counts = await asyncio.gather(
            _columns_sqlite(conn, names), _fks_sqlite(conn, names), _row_counts_sqlite(conn, names)
        )
    else:
        raise ValueError(f"Introspection not implemented for dialect: {dialect}")

    tables = [TableMeta(name=n, columns=cols.get(n, []), row_count=counts.get(n)) for n in names]
    _apply_fks(tables, fks)
    await _samples(conn, tables)
    return SchemaMetadata(db_key=db_key, dialect=dialect, tables=tables)
