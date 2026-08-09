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


def _mask_rows(df: pl.DataFrame) -> list[dict]:
    rows = df.head(20).to_dicts()
    masked: list[dict] = []
    for row in rows:
        masked.append({k: mask_pii(str(v)) if isinstance(v, str) else v for k, v in row.items()})
    return masked


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
        f"Question: {question}\n\n"
        f"RESULT ({df.height} rows, showing first {len(rows)}):\n{rows}\n\n"
        f"{hint}"
    )
    raw = await complete(
        cfg,
        [
            {
                "role": "system",
                "content": (
                    "You are InsightKit, an enterprise data analyst. Summarize the "
                    "query result into a concise insight: key numbers, the main "
                    "finding, and one recommendation. "
                    "Only state facts present in the result."
                ),
            },
            {"role": "user", "content": user},
        ],
        model=model,
        client=client,
    )
    return raw.strip()
