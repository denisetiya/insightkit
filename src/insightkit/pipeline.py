"""Core pipeline — question → SQL → guard → execute → self-correct → insight."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import polars as pl
from openai import AsyncOpenAI

from insightkit.audit import AuditLog
from insightkit.cache import QueryCache, is_cacheable, query_hash
from insightkit.chart import build_chart
from insightkit.config import Config
from insightkit.db.cache import load_schema, save_schema
from insightkit.db.connector import build_engine, ping
from insightkit.db.executor import DBError, TableNotFoundError, execute_query
from insightkit.db.introspect import introspect
from insightkit.fewshot import FewShotStore
from insightkit.llm.client import complete
from insightkit.llm.explain import explain
from insightkit.llm.prompt import SYSTEM_PROMPT, build_prompt
from insightkit.llm.router import pick_model
from insightkit.llm.sqlgen import SqlGenError, parse_sql_plan
from insightkit.security.guard import GuardError, mask_pii, validate
from insightkit.semantic import SemanticLayer

MAX_ATTEMPTS = 3

EventCallback = Callable[[str, dict], Awaitable[None]]


@dataclass
class AskResult:
    question: str
    sql: str = ""
    reasoning: str = ""
    insight: str = ""
    chart: str | None = None
    row_count: int = 0
    latency_ms: int = 0
    tokens: int = 0
    model: str = ""
    status: str = "ok"  # ok | no_data | error
    error: str | None = None
    cached: bool = False
    attempts: int = 1


class InsightKit:
    """Main entry point: connect once, ask many."""

    def __init__(
        self,
        cfg: Config,
        semantic: SemanticLayer | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.cfg = cfg
        self.engine = build_engine(cfg)
        self.audit = AuditLog(cfg)
        self.cache = QueryCache(cfg)
        self.fewshots = FewShotStore(cfg)
        self.semantic = semantic or SemanticLayer()
        self.client = client
        self._schema = None
        self._schema_version = "0"

    @property
    def db_key(self) -> str:
        return hashlib.sha256(self.cfg.database.url.encode()).hexdigest()[:12]

    async def close(self) -> None:
        await self.engine.dispose()

    async def init(self, create_admin: str | None = None, admin_role: str = "admin") -> str | None:
        """Connect, introspect, cache schema. Returns admin API key if created."""
        if not await ping(self.engine):
            raise RuntimeError("Cannot connect to database")
        async with self.engine.connect() as conn:
            meta = await introspect(conn, self.db_key, self.engine.url.get_backend_name())
        await save_schema(self.cfg, meta)
        self._schema = meta
        self._schema_version = meta.extracted_at.isoformat()

        if create_admin:
            from insightkit.security.users import UserStore

            return await UserStore(self.cfg).create(create_admin, admin_role)
        return None

    async def refresh_schema(self) -> None:
        async with self.engine.connect() as conn:
            meta = await introspect(conn, self.db_key, self.engine.url.get_backend_name())
        await save_schema(self.cfg, meta)
        self._schema = meta
        self._schema_version = meta.extracted_at.isoformat()

    async def _get_schema(self):
        if self._schema is None:
            self._schema = await load_schema(self.cfg, self.db_key)
            if self._schema is None:
                await self.refresh_schema()
            else:
                self._schema_version = self._schema.extracted_at.isoformat()
        return self._schema

    async def ask(
        self,
        question: str,
        user: str = "cli",
        role: str = "analyst",
        stream: EventCallback | None = None,
    ) -> AskResult:
        """Full pipeline with self-correction. Streams progress events when `stream` given."""
        t0 = time.monotonic()
        result = AskResult(question=question)

        # 1. cache
        schema = await self._get_schema()
        key = query_hash(question, role, self._schema_version)
        cached = await self.cache.get(key)
        if cached:
            result = AskResult(**{**cached, "question": question, "cached": True})
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            if stream:
                await stream("cached", {"insight": result.insight})
            return result

        model = pick_model(self.cfg, question, len(schema.tables))
        result.model = model
        semantic_text = self.semantic.render()
        few_shots = await self.fewshots.search(question)

        if stream:
            await stream("plan", {"model": model, "schema_tables": len(schema.tables)})

        last_error: str | None = None
        previous_raw: str | None = None
        sql: str | None = None
        df: pl.DataFrame | None = None
        tokens = 0

        for attempt in range(MAX_ATTEMPTS):
            result.attempts = attempt + 1
            prompt = build_prompt(
                question,
                schema,
                semantic_text=semantic_text,
                few_shots=few_shots,
                language=self.cfg.insight.language,
                max_tokens=self.cfg.prompt.max_tokens,
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            if previous_raw and last_error:
                messages.append({"role": "assistant", "content": previous_raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The SQL above failed: {last_error}. "
                            "Fix it and return a corrected JSON object."
                        ),
                    }
                )
            raw = await complete(
                self.cfg,
                messages,
                json_mode=True,
                model=model,
                client=self.client,
            )
            tokens += len(prompt) // 4 + len(raw) // 4
            previous_raw = raw

            try:
                plan = parse_sql_plan(raw)
            except SqlGenError as exc:
                last_error = f"Invalid response from model: {exc}"
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
                continue

            result.reasoning = plan.reasoning
            if not plan.needs_data or not plan.sql.strip():
                result.status = "no_data"
                result.insight = (
                    "This question cannot be answered with the available data schema."
                    if self.cfg.insight.language == "en"
                    else "Pertanyaan ini tidak dapat dijawab dengan skema data yang tersedia."
                )
                break

            try:
                sql = validate(
                    plan.sql, self.cfg.security.row_limit, self.cfg.security.forbidden_tables
                )
            except GuardError as exc:
                last_error = str(exc)
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
                continue

            result.sql = sql
            if stream:
                await stream("sql", {"sql": sql})

            try:
                df = await execute_query(self.engine, sql, self.cfg.security.query_timeout_s)
                break
            except TableNotFoundError as exc:
                # schema drift — refresh once, then retry
                last_error = str(exc)
                if stream:
                    await stream("schema_refresh", {"error": last_error})
                await self.refresh_schema()
                schema = self._schema
            except DBError as exc:
                last_error = str(exc)
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
        else:
            result.status = "error"
            result.error = last_error or "Query failed after retries"

        if result.status == "ok" and df is not None:
            result.row_count = df.height
            result.insight = await explain(
                self.cfg, question, df, model=model, client=self.client
            )
            tokens += len(result.insight) // 4
            result.chart = build_chart(df)
            if stream:
                await stream("insight", {"insight": result.insight})
                if result.chart:
                    await stream("chart", {"chart": result.chart})
        elif result.status == "no_data":
            result.chart = None

        result.tokens = tokens
        result.latency_ms = int((time.monotonic() - t0) * 1000)

        # audit (PII-masked) + cache
        from contextlib import suppress

        with suppress(Exception):  # audit must never break the answer
            await self.audit.record(
                user=user,
                role=role,
                question=question,
                sql=mask_pii(result.sql) if result.sql else None,
                result_summary=result.insight[:200] if result.insight else None,
                latency_ms=result.latency_ms,
                tokens=result.tokens,
                model=result.model,
                status=result.status,
                error=result.error,
            )

        if result.status == "ok" and result.sql and is_cacheable(result.sql):
            await self.cache.set(
                key,
                {
                    "sql": result.sql,
                    "reasoning": result.reasoning,
                    "insight": result.insight,
                    "chart": result.chart,
                    "row_count": result.row_count,
                    "tokens": result.tokens,
                    "model": result.model,
                    "status": result.status,
                    "attempts": result.attempts,
                },
            )
        if stream:
            await stream("done", {"status": result.status, "latency_ms": result.latency_ms})
        return result
