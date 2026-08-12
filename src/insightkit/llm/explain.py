"""Insight generation — turn query results into a concise, evidence-based insight."""

from __future__ import annotations

import polars as pl
from openai import AsyncOpenAI

from insightkit.config import Config
from insightkit.llm.client import complete
from insightkit.security.guard import mask_pii

_LANG = {
    "en": "Answer in English. Be concise (3-5 sentences). Include the key numbers from the result.",
    "id": "Jawab dalam Bahasa Indonesia. Ringkas (3-5 kalimat). Sertakan angka kunci dari hasil.",
}

_NO_DATA = {
    "en": "No data returned for this question. The query matched zero rows.",
    "id": "Tidak ada data untuk pertanyaan ini. Query tidak menghasilkan baris.",
}


_EXPLAIN_ROW_LIMIT = 20
_EXPLAIN_MAX_TOKENS = 600
_EXPLAIN_MAX_CELL_CHARS = 500


def _mask_value(value: object) -> object:
    if isinstance(value, str):
        return mask_pii(value[:_EXPLAIN_MAX_CELL_CHARS])
    text = str(value)
    masked = mask_pii(text)
    return masked if masked != text else value


def _mask_rows(df: pl.DataFrame, limit: int = _EXPLAIN_ROW_LIMIT) -> list[dict]:
    rows = df.head(limit).to_dicts()
    return [{k: _mask_value(v) for k, v in row.items()} for row in rows]


async def explain(
    cfg: Config,
    question: str,
    df: pl.DataFrame | None,
    model: str | None = None,
    client: AsyncOpenAI | None = None,
) -> str:
    """Produce an insight from the result set. Never hallucinates on empty results."""
    if df is None or df.height == 0:
        return _NO_DATA.get(cfg.insight.language, _NO_DATA["en"])

    rows = _mask_rows(df)
    hint = _LANG.get(cfg.insight.language, _LANG["en"])
    user = (
        f"Question: {question.strip()}\n\n"
        f"RESULT ({df.height} rows, showing first {len(rows)}):\n{rows}\n\n"
        f"{hint}"
    )
    raw = await complete(
        cfg,
        [
            {
                "role": "system",
                "content": (
                    "You are a data analyst. Summarize the "
                    "query result into a concise insight: key numbers, the main "
                    "finding, and one recommendation. "
                    "Only state facts present in the result."
                ),
            },
            {"role": "user", "content": user},
        ],
        model=model,
        client=client,
        max_tokens=_EXPLAIN_MAX_TOKENS,
    )
    stripped = raw.strip()
    if not stripped:
        return _NO_DATA.get(cfg.insight.language, _NO_DATA["en"])
    return stripped
