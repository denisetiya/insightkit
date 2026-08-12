"""SQL generation — parse structured LLM output into a validated SqlPlan."""

from __future__ import annotations

import json
import re

from openai import AsyncOpenAI
from pydantic import BaseModel

from insightkit.config import Config
from insightkit.llm.client import complete

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class SqlPlan(BaseModel):
    sql: str = ""
    reasoning: str = ""
    needs_data: bool = True
    queries: list[str] | None = None


MAX_ANALYSIS_QUERIES = 4


class SqlGenError(RuntimeError):
    """LLM output could not be parsed as a valid SQL plan."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def parse_sql_plan(raw: str) -> SqlPlan:
    """Parse LLM text into SqlPlan (tolerates markdown fences and stray text)."""
    text = raw.strip()
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        if start == -1:
            return SqlPlan(sql="", reasoning=text, needs_data=False)
        text = text[start:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SqlGenError(f"Invalid JSON from LLM: {exc}", raw) from exc
    if not isinstance(data, dict):
        raise SqlGenError("LLM response JSON must be an object", raw)
    sql = data.get("sql", "")
    reasoning = data.get("reasoning", "")
    needs_data = data.get("needs_data", True)
    sql = sql.strip() if isinstance(sql, str) else ""
    reasoning = reasoning.strip() if isinstance(reasoning, str) else str(reasoning)
    needs_data = needs_data if isinstance(needs_data, bool) else True
    raw_queries = data.get("queries")
    queries: list[str] | None = None
    if isinstance(raw_queries, list):
        cleaned = [q.strip() for q in raw_queries if isinstance(q, str) and q.strip()]
        queries = cleaned[:MAX_ANALYSIS_QUERIES] or None
    if needs_data and not sql and not queries:
        raise SqlGenError("LLM response missing 'sql' field", raw)
    return SqlPlan(sql=sql, reasoning=reasoning, needs_data=needs_data, queries=queries)


async def generate_sql(
    cfg: Config,
    prompt: str,
    model: str | None = None,
    client: AsyncOpenAI | None = None,
) -> SqlPlan:
    """Call the LLM and return a validated SqlPlan."""
    raw = await complete(
        cfg,
        [{"role": "system", "content": "You produce JSON."}, {"role": "user", "content": prompt}],
        json_mode=True,
        model=model,
        client=client,
    )
    return parse_sql_plan(raw)
