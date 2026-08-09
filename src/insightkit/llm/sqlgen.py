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


class SqlGenError(RuntimeError):
    """LLM output could not be parsed as a valid SQL plan."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def parse_sql_plan(raw: str) -> SqlPlan:
    """Parse LLM text into SqlPlan (tolerates markdown fences + stray text)."""
    text = raw.strip()
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        if start == -1:
            raise SqlGenError("No JSON object in LLM response", raw)
        text = text[start:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SqlGenError(f"Invalid JSON from LLM: {exc}", raw) from exc
    if "sql" not in data:
        raise SqlGenError("LLM response missing 'sql' field", raw)
    return SqlPlan(
        sql=str(data.get("sql", "")).strip(),
        reasoning=str(data.get("reasoning", "")),
        needs_data=bool(data.get("needs_data", True)),
    )


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
