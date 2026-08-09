"""Schema cache — persist SchemaMetadata to the internal meta DB (SQLite)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from insightkit.config import Config
from insightkit.db.schema import ColumnMeta, SchemaMetadata, TableMeta


def meta_db_path(cfg: Config) -> Path:
    cfg.storage.ensure()
    return cfg.storage.path / cfg.storage.meta_db


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
  db_key TEXT NOT NULL,
  table_name TEXT NOT NULL,
  column_name TEXT NOT NULL,
  data_type TEXT,
  nullable INTEGER,
  is_pk INTEGER,
  fk_ref TEXT,
  sample_values TEXT,
  row_count INTEGER,
  PRIMARY KEY (db_key, table_name, column_name)
);
"""


async def init_meta_db(cfg: Config) -> None:
    path = meta_db_path(cfg)
    async with aiosqlite.connect(path) as db:
        await db.execute(_SCHEMA_DDL)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS meta_info (key TEXT PRIMARY KEY, value TEXT)"
        )
        await db.commit()


async def save_schema(cfg: Config, meta: SchemaMetadata) -> None:
    await init_meta_db(cfg)
    path = meta_db_path(cfg)
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM schema_meta WHERE db_key = ?", (meta.db_key,))
        for t in meta.tables:
            for c in t.columns:
                await db.execute(
                    "INSERT OR REPLACE INTO schema_meta "
                    "(db_key, table_name, column_name, data_type, nullable, is_pk, "
                    "fk_ref, sample_values, row_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        meta.db_key,
                        t.name,
                        c.name,
                        c.data_type,
                        int(c.nullable),
                        int(c.is_pk),
                        c.fk_ref,
                        json.dumps(t.sample.get(c.name, [])),
                        t.row_count,
                    ),
                )
        await db.execute(
            "INSERT OR REPLACE INTO meta_info (key, value) VALUES ('schema_extracted_at', ?)",
            (meta.extracted_at.isoformat(),),
        )
        await db.commit()


async def load_schema(cfg: Config, db_key: str) -> SchemaMetadata | None:
    path = meta_db_path(cfg)
    if not path.exists():
        return None
    async with aiosqlite.connect(path) as db:
        await db.execute(_SCHEMA_DDL)
        cursor = await db.execute(
            "SELECT table_name, column_name, data_type, nullable, is_pk, fk_ref, "
            "sample_values, row_count "
            "FROM schema_meta WHERE db_key = ? ORDER BY table_name, column_name",
            (db_key,),
        )
        rows = await cursor.fetchall()
        row = await db.execute("SELECT value FROM meta_info WHERE key = 'schema_extracted_at'")
        extracted = await row.fetchone()
    if not rows:
        return None

    tables: dict[str, TableMeta] = {}
    for table_name, column_name, data_type, nullable, is_pk, fk_ref, samples, row_count in rows:
        t = tables.setdefault(
            table_name,
            TableMeta(name=table_name, row_count=row_count),
        )
        t.columns.append(
            ColumnMeta(
                name=column_name,
                data_type=data_type or "",
                nullable=bool(nullable),
                is_pk=bool(is_pk),
                fk_ref=fk_ref,
            )
        )
        if samples:
            t.sample[column_name] = json.loads(samples)
    return SchemaMetadata(
        db_key=db_key,
        dialect="",
        tables=list(tables.values()),
        extracted_at=datetime.fromisoformat(extracted[0]) if extracted else datetime.now(UTC),
    )
