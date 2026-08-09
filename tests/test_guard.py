"""Guardrail tests."""

from __future__ import annotations

import pytest

from insightkit.security.guard import (
    GuardError,
    check_forbidden_tables,
    check_read_only,
    enforce_row_limit,
    mask_pii,
    validate,
)


def test_blocks_write_statements() -> None:
    for sql in [
        "DELETE FROM orders",
        "DROP TABLE orders",
        "UPDATE orders SET x=1",
        "INSERT INTO x VALUES (1)",
    ]:
        with pytest.raises(GuardError):
            check_read_only(sql)


def test_allows_select_and_with() -> None:
    assert check_read_only("SELECT * FROM orders").startswith("SELECT")
    assert check_read_only("WITH t AS (SELECT 1) SELECT * FROM t").startswith("WITH")


def test_blocks_multi_statement() -> None:
    with pytest.raises(GuardError, match="Multiple statements"):
        check_read_only("SELECT 1; DELETE FROM orders")


def test_blocks_forbidden_keyword_in_subquery() -> None:
    with pytest.raises(GuardError, match="delete"):
        check_read_only("SELECT * FROM orders JOIN (SELECT 1) t ON true DELETE FROM x")


def test_enforce_row_limit_appends() -> None:
    assert enforce_row_limit("SELECT * FROM orders", 100) == "SELECT * FROM orders LIMIT 100"


def test_enforce_row_limit_clamps_existing() -> None:
    assert enforce_row_limit("SELECT * FROM orders LIMIT 99999", 100) == (
        "SELECT * FROM orders LIMIT 100"
    )
    assert enforce_row_limit("SELECT * FROM orders LIMIT 5", 100) == "SELECT * FROM orders LIMIT 5"


def test_forbidden_tables() -> None:
    with pytest.raises(GuardError, match="salaries"):
        check_forbidden_tables("SELECT * FROM salaries", ["salaries"])
    assert check_forbidden_tables("SELECT * FROM orders", ["salaries"]) == "SELECT * FROM orders"


def test_pii_mask() -> None:
    text = "contact alice@example.com or 081234567890 or 3201010203040005 or 4111 1111 1111 1111"
    masked = mask_pii(text)
    assert "alice@example.com" not in masked
    assert "081234567890" not in masked
    assert "3201010203040005" not in masked
    assert masked.count("[REDACTED]") == 4


def test_validate_full_pipeline() -> None:
    cleaned = validate("select * from orders", limit=50, forbidden_tables=[])
    assert cleaned.endswith("LIMIT 50")
    with pytest.raises(GuardError):
        validate("DROP TABLE orders", limit=50, forbidden_tables=[])
    with pytest.raises(GuardError):
        validate("SELECT * FROM salaries", limit=50, forbidden_tables=["salaries"])
