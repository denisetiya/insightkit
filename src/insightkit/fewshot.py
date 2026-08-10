"""Few-shot store — curated question→SQL pairs that improve future generations."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from insightkit.config import Config
from insightkit.db.cache import MetaDB, meta_db_path

_DDL = """
CREATE TABLE IF NOT EXISTS few_shots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_hash TEXT UNIQUE NOT NULL,
  question TEXT NOT NULL,
  sql TEXT NOT NULL,
  tags TEXT,
  source TEXT,
  created_at TEXT NOT NULL
);
"""

_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


class FewShotStore:
    def __init__(self, cfg: Config) -> None:
        self.path: Path = meta_db_path(cfg)

    async def add(self, question: str, sql: str, tags: str = "", source: str = "manual") -> None:
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            await db.execute(
                "INSERT OR IGNORE INTO few_shots "
                "(question_hash, question, sql, tags, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (hashlib.sha256(question.encode()).hexdigest(), question, sql, tags, source),
            )
            await db.commit()

    async def search(self, question: str, k: int = 3) -> list[tuple[str, str]]:
        """Keyword-overlap retrieval (cheap, deterministic — no embeddings needed)."""
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute("SELECT question, sql FROM few_shots")
            rows = await cursor.fetchall()
        if not rows:
            return []
        q_tokens = _tokens(question)
        scored = []
        for stored_q, sql in rows:
            overlap = len(q_tokens & _tokens(stored_q))
            if overlap:
                scored.append((overlap, stored_q, sql))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(q, s) for _, q, s in scored[:k]]

    async def count(self) -> int:
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute("SELECT COUNT(*) FROM few_shots")
            return int((await cursor.fetchone())[0])

    async def list_all(self, limit: int = 100) -> list[dict]:
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute(
                "SELECT question, sql, tags, source, created_at FROM few_shots "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
        cols = ["question", "sql", "tags", "source", "created_at"]
        return [dict(zip(cols, r, strict=True)) for r in rows]
