"""Prompt builder tests."""

from __future__ import annotations

from insightkit.config import Config
from insightkit.db.schema import ColumnMeta, SchemaMetadata, TableMeta
from insightkit.llm.prompt import build_prompt, estimate_tokens


def _schema() -> SchemaMetadata:
    return SchemaMetadata(
        db_key="d",
        dialect="sqlite",
        tables=[
            TableMeta(
                name="orders",
                columns=[
                    ColumnMeta(name="id", data_type="INTEGER", is_pk=True),
                    ColumnMeta(name="status", data_type="TEXT"),
                    ColumnMeta(name="amount", data_type="REAL"),
                    ColumnMeta(name="customer_id", data_type="INTEGER", fk_ref="customers.id"),
                ],
                row_count=5,
                sample={"status": ["paid", "pending", "refunded"]},
            ),
            TableMeta(
                name="customers",
                columns=[
                    ColumnMeta(name="id", data_type="INTEGER", is_pk=True),
                    ColumnMeta(name="name", data_type="TEXT"),
                ],
                row_count=3,
            ),
        ],
    )


def test_build_prompt_contains_schema_and_question() -> None:
    cfg = Config(database={"url": "sqlite+aiosqlite:///:memory:"})
    prompt = build_prompt(
        "total revenue?",
        _schema(),
        language="en",
        max_tokens=cfg.prompt.max_tokens,
    )
    assert "DATABASE SCHEMA" in prompt
    assert "TABLE orders" in prompt
    assert "QUESTION: total revenue?" in prompt
    assert "FK->customers.id" in prompt


def test_build_prompt_semantic_and_fewshots() -> None:
    prompt = build_prompt(
        "revenue",
        _schema(),
        semantic_text="revenue = SUM(amount) WHERE status='paid'",
        few_shots=[("total orders", "SELECT COUNT(*) FROM orders")],
    )
    assert "METRIC DEFINITIONS" in prompt
    assert "revenue = SUM(amount)" in prompt
    assert "EXAMPLE QUERIES" in prompt
    assert "SELECT COUNT(*) FROM orders" in prompt


def test_token_budget_trim() -> None:
    big = SchemaMetadata(
        db_key="d",
        dialect="sqlite",
        tables=[
            TableMeta(
                name=f"t{i}",
                columns=[ColumnMeta(name=f"c{j}", data_type="TEXT") for j in range(50)],
            )
            for i in range(40)
        ],
    )
    prompt = build_prompt("x", big, max_tokens=300)
    assert estimate_tokens(prompt) <= 320


def test_language_hint() -> None:
    id_prompt = build_prompt("q", _schema(), language="id")
    assert "Bahasa Indonesia" in id_prompt
    en_prompt = build_prompt("q", _schema(), language="en")
    assert "Answer in English" in en_prompt
