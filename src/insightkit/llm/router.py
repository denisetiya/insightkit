"""Model routing — cheap model for simple questions, big model for complex ones."""

from __future__ import annotations

import re

from insightkit.config import Config

_COMPLEX_HINTS = re.compile(
    r"\b(compare|comparison|trend|vs|versus|per\s+month|monthly|quarterly|rolling|cumulative|"
    r"ratio|percentage|correlation|cohort|churn|attribution|forecast|outlier|"
    r"year[ -]?over[ -]?year|m[oO][mM]|q[oO][qQ])\b"
)


def complexity_score(question: str, table_count: int) -> int:
    score = 0
    if len(question) > 80:
        score += 1
    if _COMPLEX_HINTS.search(question.lower()):
        score += 1
    if len(question.split()) > 15:
        score += 1
    if table_count > 5:
        score += 1
    return score


def pick_model(cfg: Config, question: str, table_count: int) -> str:
    """Route to fast model when simple, full model when complex."""
    if complexity_score(question, table_count) >= 2:
        return cfg.llm.model
    return cfg.llm.fast_model or cfg.llm.model
