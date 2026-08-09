"""LLM prompt construction with token budget enforcement."""

from __future__ import annotations

from insightkit.db.schema import SchemaMetadata

SYSTEM_PROMPT = """You are InsightKit, an enterprise data analyst AI.
You answer natural-language questions by writing SQL against a read-only database.
STRICT RULES:
1. Respond with a SINGLE JSON object, no markdown fences, no extra text:
   {"sql": "<read-only SQL or empty string>", "reasoning": "<short reasoning>",
    "needs_data": <true|false>}
2. Use ONLY table and column names that exist in the provided schema. Never invent columns.
3. SQL must be read-only (SELECT / WITH ... SELECT). Never DROP, DELETE, UPDATE, INSERT,
   ALTER, TRUNCATE, GRANT.
4. If the question cannot be answered with the available schema, set needs_data to false
   and sql to "".
5. If metric definitions are provided, use them verbatim for the metric definition.
6. Respect the row limit; add LIMIT if needed.
7. When the question asks for insight over data, prefer aggregations (SUM, COUNT, AVG,
   GROUP BY) over raw rows."""

_LANG_HINTS = {
    "en": "Answer in English.",
    "id": "Answer in Bahasa Indonesia.",
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars/token) — cheap, good enough for budgeting."""
    return max(1, len(text) // 4)


def build_prompt(
    question: str,
    schema: SchemaMetadata | None,
    semantic_text: str = "",
    few_shots: list[tuple[str, str]] | None = None,
    language: str = "en",
    max_tokens: int = 3000,
) -> str:
    """Assemble system + context + question, trimming schema to fit the token budget."""
    parts = [SYSTEM_PROMPT, _LANG_HINTS.get(language, _LANG_HINTS["en"])]

    if semantic_text:
        parts.append(f"METRIC DEFINITIONS:\n{semantic_text}")

    if few_shots:
        shots = "\n".join(f"Q: {q}\nSQL: {s}" for q, s in few_shots[:3])
        parts.append(f"EXAMPLE QUERIES:\n{shots}")

    header = "\n\n".join(parts)
    header_tokens = estimate_tokens(header)
    budget = max_tokens - header_tokens - estimate_tokens(question) - 100

    schema_text = schema.render() if schema else ""
    if schema_text and estimate_tokens(schema_text) > budget:
        assert schema is not None
        schema_text = _trim_schema(schema, budget)
    if schema_text:
        header = f"{header}\n\nDATABASE SCHEMA:\n{schema_text}"

    return f"{header}\n\nQUESTION: {question}"


def _trim_schema(schema: SchemaMetadata, budget: int) -> str:
    """Progressively trim schema: columns first (non-PK/FK), then tables."""
    import copy

    slim = copy.deepcopy(schema)
    for t in slim.tables:
        kept = [c for c in t.columns if c.is_pk or c.fk_ref]
        t.columns = kept + [c for c in t.columns if c not in kept]
        t.sample = {}
    text = slim.render()
    if estimate_tokens(text) <= budget:
        return text

    # drop non-essential columns table by table
    while estimate_tokens(text) > budget and any(len(t.columns) > 1 for t in slim.tables):
        for t in slim.tables:
            if len(t.columns) > 1:
                # drop last (least essential)
                t.columns.pop()
        text = slim.render()

    # still over: drop tables (keep those with FKs)
    tables_with_fk = [t for t in slim.tables if any(c.fk_ref for c in t.columns)]
    while estimate_tokens(text) > budget and len(slim.tables) > len(tables_with_fk):
        drop = [t for t in slim.tables if not any(c.fk_ref for c in t.columns)]
        for t in drop:
            slim.tables.remove(t)
        text = slim.render()
    return text
