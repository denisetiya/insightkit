"""Users + RBAC — API key auth with roles (admin / analyst / viewer)."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

import aiosqlite

from insightkit.config import Config
from insightkit.db.cache import meta_db_path

ROLES = {"admin", "analyst", "viewer"}

_DDL = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL,
  api_key_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return f"ik_{secrets.token_urlsafe(32)}"


class UserStore:
    def __init__(self, cfg: Config) -> None:
        self.path: Path = meta_db_path(cfg)

    async def create(self, username: str, role: str) -> str:
        """Create user, return the plaintext API key (shown once)."""
        if role not in ROLES:
            raise ValueError(f"Invalid role '{role}' (must be one of {sorted(ROLES)})")
        key = generate_api_key()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            await db.execute(
                "INSERT INTO users (username, role, api_key_hash, created_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (username, role, hash_api_key(key)),
            )
            await db.commit()
        return key

    async def verify(self, api_key: str) -> dict | None:
        """Return {username, role} if the API key is valid."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute(
                "SELECT username, role FROM users WHERE api_key_hash = ?",
                (hash_api_key(api_key),),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return {"username": row[0], "role": row[1]}

    async def delete(self, username: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute("DELETE FROM users WHERE username = ?", (username,))
            await db.commit()
        return cursor.rowcount > 0

    async def list_users(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_DDL)
            cursor = await db.execute(
                "SELECT username, role, created_at FROM users ORDER BY id"
            )
            rows = await cursor.fetchall()
        cols = ["username", "role", "created_at"]
        return [dict(zip(cols, r, strict=True)) for r in rows]
