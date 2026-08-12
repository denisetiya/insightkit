"""LLM prompt construction with token budget enforcement."""

from __future__ import annotations

import re

from insightkit.db.schema import SchemaMetadata, TableMeta

SYSTEM_PROMPT = """You are InsightKit, a data analyst. Write read-only SQL from the schema.
Return one JSON object only, no fences or extra text: {"sql": "<SELECT/WITH or empty>",
"reasoning": "<short>", "needs_data": bool, "queries": [...] optional}.
Use only schema tables/columns, never invent names. SQL must be SELECT or WITH...SELECT.
Never DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/GRANT. Respect row limit, add LIMIT.
Advice questions: do not use general knowledge. Return 2-4 independent read-only queries
in "queries" with sql "" and needs_data true. Non-data questions: answer in "reasoning"
with sql "" and needs_data false. Use provided metric definitions verbatim.
Prefer aggregations over raw rows."""

MONGO_SYSTEM_PROMPT = """You are InsightKit, a data analyst. Write MongoDB aggregation pipelines.
Return one JSON object only, no fences or extra text: {"sql": "<{collection,pipeline} string>",
"reasoning": "<short>", "needs_data": bool, "queries": [...] optional}.
Use only schema collections/fields, never invent names. Read-only: never $out/$merge/$delete.
Pipeline must be valid JSON. Advice questions: do not use general knowledge. Return 2-4
independent pipelines in "queries". Non-data questions: answer in "reasoning" with sql ""
and needs_data false. Prefer $match/$group/$sort/$limit over dumps."""

_LANG_HINTS = {
    "en": "Answer in English.",
    "id": "Answer in Bahasa Indonesia.",
}

# Recommendation/advice questions → analysis mode: model plans 2-4 queries, results
# are executed, then a data-grounded insight + recommendations is produced.
_ANALYSIS_INTENT_RE = re.compile(
    r"\b(rekomendasi|rekomend|saran|tips?|strategi|meningkatkan|tingkatkan|naikkan|"
    r"optimasi|mengoptimalkan|optimize|improve|boost|pertumbuhan|tumbuhkan|grow)\w*\b",
    re.IGNORECASE,
)


def is_analysis_question(question: str) -> bool:
    """Recommendation/advice questions get the multi-query analysis flow."""
    return bool(_ANALYSIS_INTENT_RE.search(question))


_FINAL_PROMPTS = {
    "en": (
        "You are a data analyst. Based ONLY on the query results below, write:\n"
        "1) \"insight\": a concise factual summary of what the data shows "
        "(numbers from the results).\n"
        "2) \"recommendations\": a list of 3-5 concrete, data-driven recommendations.\n"
        "Never invent numbers that are not in the results. Respond with a single JSON object:\n"
        "{\"insight\": \"...\", \"recommendations\": [\"...\", \"...\"]}"
    ),
    "id": (
        "Kamu seorang analis data. Berdasarkan HANYA hasil query di bawah, tulis:\n"
        "1) \"insight\": ringkasan faktual singkat tentang apa yang ditunjukkan data "
        "(angka dari hasil query).\n"
        "2) \"recommendations\": daftar 3-5 rekomendasi konkret berbasis data.\n"
        "Jangan pernah mengarang angka yang tidak ada di hasil. Jawab dengan SATU objek JSON:\n"
        "{\"insight\": \"...\", \"recommendations\": [\"...\", \"...\"]}"
    ),
}


def build_final_prompt(question: str, results: list[dict], language: str = "en") -> str:
    """Phase-2 prompt: question + executed query results → insight + recommendations."""
    lines = [f"QUESTION: {question}", ""]
    for i, res in enumerate(results, 1):
        lines.append(f"QUERY {i}: {res['query']}")
        lines.append(f"RESULT {i}: {res['rows']}")
    body = "\n".join(lines)
    return f"{_FINAL_PROMPTS.get(language, _FINAL_PROMPTS['en'])}\n\n{body}"


def system_prompt_for(dialect: str) -> str:
    return MONGO_SYSTEM_PROMPT if dialect == "mongodb" else SYSTEM_PROMPT


def _tokens(text: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def relevant_tables(schema: SchemaMetadata, question: str, max_tables: int = 8) -> SchemaMetadata:
    """Keep only tables relevant to the question (+ FK closure) — smaller prompt, faster + cheaper.

    Small schemas (<= max_tables) pass through untouched.
    """
    if len(schema.tables) <= max_tables:
        return schema

    q = _tokens(question)

    def score(t: TableMeta) -> int:
        s = 0
        if _tokens(t.name) & q:
            s += 3
        for c in t.columns:
            if _tokens(c.name) & q:
                s += 1
        return s

    scored = sorted(schema.tables, key=score, reverse=True)
    picked = [t for t in scored if score(t) > 0][:max_tables]
    if not picked:
        picked = scored[:max_tables]

    # FK closure: include referenced tables so joins stay valid
    names = {t.name for t in picked}
    changed = True
    while changed:
        changed = False
        for t in list(picked):
            for c in t.columns:
                if c.fk_ref:
                    ref = c.fk_ref.split(".")[0]
                    if ref not in names:
                        ref_table = schema.table(ref)
                        if ref_table is not None:
                            picked.append(ref_table)
                            names.add(ref)
                            changed = True
    return SchemaMetadata(
        db_key=schema.db_key,
        dialect=schema.dialect,
        tables=picked,
        extracted_at=schema.extracted_at,
    )


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
    system = SYSTEM_PROMPT
    lang_hint = _LANG_HINTS.get(language, _LANG_HINTS["en"])
    extras: list[str] = []
    if semantic_text:
        extras.append(f"METRIC DEFINITIONS:\n{semantic_text}")
    if few_shots:
        shots = "\n".join(f"Q: {q}\nSQL: {s}" for q, s in few_shots[:3])
        extras.append(f"EXAMPLE QUERIES:\n{shots}")

    header = "\n\n".join([system, lang_hint, *extras])
    budget = max_tokens - estimate_tokens(header) - estimate_tokens(question) - 100

    schema_text = schema.render() if schema else ""
    if schema_text and estimate_tokens(schema_text) > budget and schema is not None:
        schema_text = _trim_schema(schema, max(budget, 0))
        if estimate_tokens(schema_text) > max(budget, 0):
            schema_text = ""
    if schema_text:
        header = f"{header}\n\nDATABASE SCHEMA:\n{schema_text}"

    prompt = f"{header}\n\nQUESTION: {question}"
    if estimate_tokens(prompt) > max_tokens:
        prompt = f"{system}\n\n{lang_hint}\n\nQUESTION: {question}"
    return prompt


def _trim_schema(schema: SchemaMetadata, budget: int) -> str:
    """Progressively trim schema: columns first (non-PK/FK), then tables."""
    import copy

    if budget <= 0:
        return ""
    slim = copy.deepcopy(schema)
    for t in slim.tables:
        t.sample = {}
    text = slim.render(max_tables=len(slim.tables), max_cols_per_table=10)
    if estimate_tokens(text) <= budget:
        return text

    while estimate_tokens(text) > budget and any(len(t.columns) > 1 for t in slim.tables):
        for t in slim.tables:
            while len(t.columns) > 1 and estimate_tokens(text) > budget:
                t.columns.pop()
                text = slim.render(max_tables=len(slim.tables), max_cols_per_table=len(t.columns))
        text = slim.render()

    while estimate_tokens(text) > budget and len(slim.tables) > 1:
        slim.tables.pop()
        text = slim.render()
    if estimate_tokens(text) > budget:
        return ""
    return text
