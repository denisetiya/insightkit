"""Query result cache — TTL-based, skips volatile queries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from insightkit.config import Config
from insightkit.db.cache import meta_db_path

_VOLATILE_RE = re.compile(
    r"\b(now|current_timestamp|current_date|current_time|random|uuid|newid|getdate|rand)\s*\(",
    re.IGNORECASE,
)

_DDL = """
CREATE TABLE IF NOT EXISTS cache (
  query_hash TEXT PRIMARY KEY,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
"""


def query_hash(question: str, role: str, schema_version: str) -> str:
    return hashlib.sha256(f"{role}|{schema_version}|{question}".encode()).hexdigest()


def is_cacheable(sql: str) -> bool:
    return not _VOLATILE_RE.search(sql)


class QueryCache:
    def __init__(self, cfg: Config) -> None:
        self.path: Path = meta_db_path(cfg)
        self.ttl_s = cfg.cache.ttl_s

    async def get(self, key: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute(
                "SELECT result_json, expires_at FROM cache WHERE query_hash = ?", (key,)
            )
            row = await cursor.fetchone()
        if not row:
            return None
        result_json, expires_at = row
        if datetime.fromisoformat(expires_at) < datetime.now(UTC):
            return None
        return json.loads(result_json)

    async def set(self, key: str, payload: dict) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self.ttl_s)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            await db.execute(
                "INSERT OR REPLACE INTO cache (query_hash, result_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (key, json.dumps(payload), now.isoformat(), expires.isoformat()),
            )
            await db.commit()
