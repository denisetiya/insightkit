"""Model routing — cheap model for simple questions, big model for complex ones."""

from __future__ import annotations

import re

from insightkit.config import Config

_COMPLEX_HINTS = re.compile(
    r"\b(compare|comparison|trend|versus|monthly|quarterly|rolling|cumulative|"
    r"ratio|percentage|correlation|cohort|churn|attribution|forecast|outlier|"
    r"bandingkan|perbandingan|tren|bulanan|triwulan|kuartal|kumulatif|persentase|"
    r"korelasi|prediksi|pertumbuhan|year[ -]?over[ -]?year|\bmom\b|\bqoq\b)\b",
    re.IGNORECASE,
)

_SIMPLE_QUESTION_MAX_CHARS = 80
_SIMPLE_QUESTION_MAX_WORDS = 15
_COMPLEX_TABLE_THRESHOLD = 5
_COMPLEX_SCORE_THRESHOLD = 2


def complexity_score(question: str, table_count: int) -> int:
    text = question.strip()
    if not text:
        return 0
    score = 0
    if len(text) > _SIMPLE_QUESTION_MAX_CHARS:
        score += 1
    if _COMPLEX_HINTS.search(text):
        score += 1
    if len(text.split()) > _SIMPLE_QUESTION_MAX_WORDS:
        score += 1
    if table_count > _COMPLEX_TABLE_THRESHOLD:
        score += 1
    return score


def pick_model(cfg: Config, question: str, table_count: int) -> str:
    """Route to fast model when simple, full model when complex."""
    if complexity_score(question, table_count) >= _COMPLEX_SCORE_THRESHOLD:
        return cfg.llm.model
    return cfg.llm.fast_model or cfg.llm.model
