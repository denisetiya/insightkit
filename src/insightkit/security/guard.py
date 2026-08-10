"""Guardrails — read-only enforcement, row limits, PII masking, table blacklist.

Layer 2 of the security model (layer 1 is the read-only DB role in db/connector.py).
Also validates MongoDB aggregation pipelines (write stages blocked).
"""

from __future__ import annotations

import json
import re

FORBIDDEN_KEYWORDS = {
    "drop", "delete", "update", "insert", "alter", "truncate", "grant", "revoke",
    "create", "attach", "detach", "vacuum", "reindex", "merge", "replace into",
}
ALLOWED_STARTS = {"select", "with", "explain", "show", "pragma", "values"}

_COMMENT_RE = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)
_KEYWORD_RE = re.compile(r"\b([a-z_ ]+?)\b", re.IGNORECASE)
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)", re.IGNORECASE)

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?62|0)8\d{7,12}(?!\d)")
_NIK_RE = re.compile(r"(?<!\d)\d{16}(?!\d)")
_CC_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

_MASK = "[REDACTED]"


class GuardError(RuntimeError):
    """Query rejected by guardrails."""


def _strip_comments(sql: str) -> str:
    return _COMMENT_RE.sub(" ", sql)


def _statements(sql: str) -> list[str]:
    cleaned = _strip_comments(sql)
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    return parts


def check_read_only(sql: str) -> str:
    """Reject non-read-only statements."""
    statements = _statements(sql)
    if not statements:
        raise GuardError("Empty SQL statement")
    if len(statements) > 1:
        raise GuardError("Multiple statements are not allowed (single SELECT only)")
    stmt = statements[0]
    first_word = stmt.split(None, 1)[0].lower() if stmt.split() else ""
    if first_word not in ALLOWED_STARTS:
        raise GuardError(f"Statement type not allowed: '{first_word}'")
    lowered = stmt.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            raise GuardError(f"Forbidden keyword: '{keyword}'")
    return stmt


def enforce_row_limit(sql: str, limit: int) -> str:
    """Ensure the query returns at most `limit` rows."""
    if limit <= 0:
        raise GuardError("row_limit must be positive")
    match = list(_LIMIT_RE.finditer(sql))
    if match:
        last = match[-1]
        current = int(last.group(1))
        if current > limit:
            return sql[: last.start()] + f"LIMIT {limit}" + sql[last.end() :]
        return sql
    return f"{sql} LIMIT {limit}"


def check_forbidden_tables(sql: str, forbidden: list[str]) -> str:
    """Reject queries touching blacklisted tables."""
    lowered = sql.lower()
    for table in forbidden:
        if re.search(rf"\b{re.escape(table.lower())}\b", lowered):
            raise GuardError(f"Access to table '{table}' is forbidden")
    return sql


def mask_pii(text: str) -> str:
    """Mask PII (email, phone, NIK, card numbers) — applied before LLM/log."""
    out = _EMAIL_RE.sub(_MASK, text)
    out = _PHONE_RE.sub(_MASK, out)
    out = _NIK_RE.sub(_MASK, out)
    out = _CC_RE.sub(_MASK, out)
    return out


def validate(sql: str, limit: int, forbidden_tables: list[str]) -> str:
    """Full guardrail pass — returns the cleaned (row-limited) SQL."""
    stmt = check_read_only(sql)
    stmt = check_forbidden_tables(stmt, forbidden_tables)
    return enforce_row_limit(stmt, limit)


MONGO_WRITE_STAGES = {"$out", "$merge", "$delete"}


def validate_mongo(payload: str, limit: int) -> str:
    """Validate an aggregation pipeline payload; enforces row limit via $limit."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise GuardError(f"Invalid MongoDB query JSON: {exc}") from exc
    collection = data.get("collection")
    pipeline = data.get("pipeline")
    if not collection or not isinstance(pipeline, list):
        raise GuardError('MongoDB query must be {"collection": "...", "pipeline": [...]}')
    for stage in pipeline:
        if not isinstance(stage, dict):
            raise GuardError(f"Invalid aggregation stage: {stage!r}")
        for key in stage:
            if key in MONGO_WRITE_STAGES:
                raise GuardError(f"Forbidden aggregation stage: {key}")
    if limit > 0 and not any("$limit" in s for s in pipeline):
        pipeline.append({"$limit": limit})
    return json.dumps(data)
