"""Shared fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_db(tmp_path: Path) -> Path:
    """Materialize demo.sql into a file-based SQLite DB."""
    db = tmp_path / "demo.db"
    conn = sqlite3.connect(db)
    conn.executescript((FIXTURES / "demo.sql").read_text())
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def demo_config(demo_db: Path, tmp_path: Path) -> dict:
    """Minimal config dict pointing at the demo DB + mock-friendly LLM settings."""
    return {
        "database": {"url": f"sqlite+aiosqlite:///{demo_db}"},
        "llm": {"base_url": "http://localhost:9/v1", "api_key": "test", "model": "test-model"},
        "storage": {"path": str(tmp_path / "ik"), "meta_db": "meta.db"},
        "security": {"row_limit": 1000, "query_timeout_s": 10},
        "insight": {"language": "en"},
    }
