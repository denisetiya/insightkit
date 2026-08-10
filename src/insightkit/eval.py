"""Evaluation — golden set accuracy gate (regression detection).

Comparison strategy: execute the expected SQL and the generated SQL, then compare
result sets (order-insensitive). SQL text comparison is only a fallback when the
expected SQL cannot be executed — real LLM output varies in aliases/formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml
from openai import AsyncOpenAI

from insightkit.config import Config
from insightkit.pipeline import InsightKit

_NORM_RE = re.compile(r"\s+")
_TRAILING_LIMIT_RE = re.compile(r"\s+limit\s+\d+$", re.IGNORECASE)


def normalize_sql(sql: str) -> str:
    """Lowercase, collapse whitespace, drop trailing guard-inserted LIMIT."""
    cleaned = _TRAILING_LIMIT_RE.sub("", sql.strip())
    return _NORM_RE.sub(" ", cleaned.rstrip(";").lower())


def _norm_value(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    return str(v)


def _rows(df: pl.DataFrame) -> list[tuple]:
    return sorted(tuple(_norm_value(v) for v in row) for row in df.iter_rows())


@dataclass
class GoldenCase:
    question: str
    sql_expected: str | None = None
    result_keywords: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    total: int
    correct: int
    failures: list[dict] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_golden(path: str | Path) -> list[GoldenCase]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Golden set not found: {p}")
    data = yaml.safe_load(p.read_text()) or []
    return [GoldenCase(**case) for case in data]


async def run_eval(
    cfg: Config,
    golden: list[GoldenCase],
    client: AsyncOpenAI | None = None,
) -> EvalResult:
    kit = InsightKit(cfg, client=client)
    await kit._get_schema()  # ensure schema cached before eval

    result = EvalResult(total=len(golden), correct=0)
    for case in golden:
        try:
            ask = await kit.ask(case.question, user="eval", role="analyst")
        except Exception as exc:  # noqa: BLE001 — eval must collect failures, not crash
            result.failures.append({"question": case.question, "reason": f"pipeline error: {exc}"})
            continue

        ok = False
        reason = ""
        if case.sql_expected:
            ok, reason = await _compare_sql(kit, ask.sql, case.sql_expected)
        elif case.result_keywords:
            ok = all(kw in ask.insight.lower() for kw in case.result_keywords)
            reason = f"insight={ask.insight[:120]!r}"
        else:
            ok = ask.status == "ok"
            reason = f"status={ask.status} error={ask.error}"

        if ok:
            result.correct += 1
        else:
            result.failures.append({"question": case.question, "reason": reason})
    await kit.close()
    return result


async def _compare_sql(kit: InsightKit, generated: str, expected: str) -> tuple[bool, str]:
    """Compare by executed result set; fall back to normalized SQL text."""
    if not generated:
        return False, f"no SQL generated (expected {expected!r})"
    try:
        df_gen = await kit.backend.execute(generated, kit.cfg.security.query_timeout_s)
        df_exp = await kit.backend.execute(expected, kit.cfg.security.query_timeout_s)
    except Exception as exc:  # noqa: BLE001 — expected SQL may not be executable
        return normalize_sql(generated) == normalize_sql(expected), (
            f"exec failed, text-compare: {exc}"
        )
    if df_gen.height != df_exp.height:
        return False, f"row count {df_gen.height} != expected {df_exp.height}"
    if _rows(df_gen) != _rows(df_exp):
        return False, f"result mismatch: got {_rows(df_gen)[:5]} expected {_rows(df_exp)[:5]}"
    return True, ""

