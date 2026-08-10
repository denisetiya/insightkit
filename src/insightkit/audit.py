"""Audit log — append-only; every ask is recorded for enterprise compliance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from insightkit.config import Config
from insightkit.db.cache import MetaDB, meta_db_path

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user TEXT NOT NULL,
  role TEXT NOT NULL,
  question TEXT NOT NULL,
  sql TEXT,
  result_summary TEXT,
  latency_ms INTEGER,
  tokens INTEGER,
  model TEXT,
  status TEXT NOT NULL,
  error TEXT
);
"""


class AuditLog:
    """Append-only audit trail. No update/delete methods exist by design."""

    def __init__(self, cfg: Config) -> None:
        self.path: Path = meta_db_path(cfg)

    async def record(
        self,
        *,
        user: str,
        role: str,
        question: str,
        sql: str | None = None,
        result_summary: str | None = None,
        latency_ms: int = 0,
        tokens: int = 0,
        model: str = "",
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            await db.execute(
                "INSERT INTO audit_log "
                "(ts, user, role, question, sql, result_summary, latency_ms, "
                "tokens, model, status, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(UTC).isoformat(),
                    user,
                    role,
                    question,
                    sql,
                    result_summary,
                    latency_ms,
                    tokens,
                    model,
                    status,
                    error,
                ),
            )
            await db.commit()

    async def query(
        self, user: str | None = None, since: str | None = None, limit: int = 100
    ) -> list[dict]:
        async with MetaDB(self.path) as db:
            await db.execute(_DDL)
            sql = (
                "SELECT ts, user, role, question, sql, result_summary, latency_ms, "
                "tokens, model, status, error FROM audit_log"
            )
            conds: list[str] = []
            params: list = []
            if user:
                conds.append("user = ?")
                params.append(user)
            if since:
                conds.append("ts >= ?")
                params.append(since)
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
        cols = [
            "ts", "user", "role", "question", "sql", "result_summary",
            "latency_ms", "tokens", "model", "status", "error",
        ]
        return [dict(zip(cols, r, strict=True)) for r in rows]
