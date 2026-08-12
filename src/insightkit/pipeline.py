"""Core pipeline — question → SQL → guard → execute → self-correct → insight."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import polars as pl
from openai import AsyncOpenAI

from insightkit.audit import AuditLog
from insightkit.cache import QueryCache, is_cacheable, query_hash
from insightkit.chart import build_chart
from insightkit.config import Config
from insightkit.db.backends import SQLBackend, get_backend
from insightkit.db.cache import load_schema, save_schema
from insightkit.db.executor import DBError, TableNotFoundError
from insightkit.db.schema import SchemaMetadata
from insightkit.fewshot import FewShotStore
from insightkit.llm.client import complete
from insightkit.llm.explain import explain
from insightkit.llm.prompt import (
    build_final_prompt,
    build_prompt,
    is_analysis_question,
    relevant_tables,
    system_prompt_for,
)
from insightkit.llm.router import pick_model
from insightkit.llm.sqlgen import SqlGenError, parse_sql_plan
from insightkit.security.guard import GuardError, mask_pii, validate, validate_mongo
from insightkit.semantic import SemanticLayer

MAX_ATTEMPTS = 3

EventCallback = Callable[[str, dict], Awaitable[None]]


def _parse_analysis_answer(raw: str) -> tuple[str, list[str]]:
    """Tolerant parse of the final analysis JSON → (insight, recommendations)."""
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    if start == -1:
        return text, []  # prose fallback
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return text, []
    insight = str(data.get("insight", "")).strip()
    recs = data.get("recommendations", [])
    recs = [str(r).strip() for r in recs if str(r).strip()] if isinstance(recs, list) else []
    return insight, recs


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
    rows: list[dict] | None = None  # raw result rows (PII-masked, capped)


def _json_safe(v: object) -> object:
    """Make values JSON-serializable (Decimal/date/bytes from DB drivers)."""
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode(errors="replace")
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def _rows_for_output(df: pl.DataFrame, limit: int = 50) -> list[dict]:
    """Result rows as JSON-ready dicts — PII-masked, capped, JSON-safe."""
    from insightkit.security.guard import mask_pii

    out = []
    for row in df.head(limit).to_dicts():
        out.append(
            {k: _json_safe(mask_pii(str(v)) if isinstance(v, str) else v) for k, v in row.items()}
        )
    return out


class InsightKit:
    """Main entry point: connect once, ask many."""

    def __init__(
        self,
        cfg: Config,
        semantic: SemanticLayer | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.cfg = cfg
        self.backend = get_backend(cfg)
        self.engine = self.backend.engine if isinstance(self.backend, SQLBackend) else None
        self.audit = AuditLog(cfg)
        self.cache = QueryCache(cfg)
        self.fewshots = FewShotStore(cfg)
        self.semantic = semantic or SemanticLayer()
        self.client = client
        self._schema: SchemaMetadata | None = None
        self._schema_version = "0"

    @property
    def db_key(self) -> str:
        return hashlib.sha256(self.cfg.database.url.encode()).hexdigest()[:12]

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()

    async def init(self, create_admin: str | None = None, admin_role: str = "admin") -> str | None:
        """Connect, introspect, cache schema. Returns admin API key if created."""
        if not await self.backend.ping():
            raise RuntimeError("Cannot connect to database")
        meta = await self.backend.introspect(self.db_key)
        if self.engine is not None:
            await save_schema(self.cfg, meta)
        self._schema = meta
        self._schema_version = meta.extracted_at.isoformat()

        if create_admin:
            from insightkit.security.users import UserStore

            return await UserStore(self.cfg).create(create_admin, admin_role)
        return None

    async def refresh_schema(self) -> None:
        meta = await self.backend.introspect(self.db_key)
        if self.engine is not None:
            await save_schema(self.cfg, meta)
        self._schema = meta
        self._schema_version = meta.extracted_at.isoformat()

    async def get_schema(self) -> SchemaMetadata:
        """Return cached schema, loading or refreshing it on first use."""
        if self._schema is None:
            if self.engine is not None:
                self._schema = await load_schema(self.cfg, self.db_key)
            if self._schema is None:
                await self.refresh_schema()
            else:
                self._schema_version = self._schema.extracted_at.isoformat()
        assert self._schema is not None
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
        schema = await self.get_schema()
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

        if is_analysis_question(question):
            # recommendation/advice → data-grounded analysis flow (multi-query)
            return await self._ask_analysis(
                question,
                schema=schema,
                key=key,
                model=model,
                user=user,
                role=role,
                stream=stream,
                semantic_text=semantic_text,
                few_shots=few_shots,
                t0=t0,
            )

        if stream:
            await stream("plan", {"model": model, "schema_tables": len(schema.tables)})

        last_error: str | None = None
        previous_raw: str | None = None
        sql: str | None = None
        df: pl.DataFrame | None = None
        tokens = 0
        decline_count = 0

        for attempt in range(MAX_ATTEMPTS):
            result.attempts = attempt + 1
            assert schema is not None
            prompt_schema = relevant_tables(schema, question, self.cfg.prompt.relevant_tables)
            prompt = build_prompt(
                question,
                prompt_schema,
                semantic_text=semantic_text,
                few_shots=few_shots,
                language=self.cfg.insight.language,
                max_tokens=self.cfg.prompt.max_tokens,
            )
            messages = [
                {"role": "system", "content": system_prompt_for(self.backend.dialect)},
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
                max_tokens=1500,  # SQL plans are short — cap speeds generation
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
                decline_count += 1
                if len(plan.reasoning.strip()) >= 60:
                    # substantive non-data answer (recommendations, advice) — surface it
                    result.status = "no_data"
                    result.insight = plan.reasoning.strip()
                    break
                # flaky refusal — nudge once, then accept
                last_error = "Model belum memberikan jawaban — mencoba ulang"
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
                if decline_count >= 2:
                    result.status = "no_data"
                    result.insight = (
                        "This question cannot be answered with the available data schema."
                        if self.cfg.insight.language == "en"
                        else "Pertanyaan ini tidak dapat dijawab dengan skema data yang tersedia."
                    )
                    break
                continue

            try:
                if self.backend.dialect == "mongodb":
                    sql = validate_mongo(plan.sql, self.cfg.security.row_limit)
                else:
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
                df = await self.backend.execute(sql, self.cfg.security.query_timeout_s)
                break
            except TableNotFoundError as exc:
                last_error = str(exc)
                if stream:
                    await stream("schema_refresh", {"error": last_error})
                await self.refresh_schema()
                assert self._schema is not None
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
            result.rows = _rows_for_output(df)
            if stream:
                await stream(
                    "result",
                    {
                        "columns": list(df.columns),
                        "rows": result.rows,
                        "row_count": result.row_count,
                    },
                )
            result.insight = await explain(
                self.cfg, question, df, model=model, client=self.client
            )
            tokens += len(result.insight) // 4
            result.chart = build_chart(df)
            if stream:
                await stream("insight", {"insight": result.insight})
                if result.chart:
                    try:
                        await stream("chart", {"chart": json.loads(result.chart)})
                    except json.JSONDecodeError:
                        await stream("chart", {"chart": result.chart})
        elif result.status == "no_data":
            result.chart = None
            if result.insight and stream:
                await stream("insight", {"insight": result.insight})

        result.tokens = tokens
        return await self._finalize(result, key=key, user=user, role=role, t0=t0, stream=stream)

    async def _ask_analysis(
        self,
        question: str,
        *,
        schema: SchemaMetadata,
        key: str,
        model: str,
        user: str,
        role: str,
        stream: EventCallback | None,
        semantic_text: str,
        few_shots: list[tuple[str, str]],
        t0: float,
    ) -> AskResult:
        """Data-grounded analysis for recommendation/advice questions.

        Phase 1: LLM plans 2-4 read-only analytical queries. Phase 2: queries are
        executed. Phase 3: LLM writes insight + recommendations from the real results.
        """
        result = AskResult(question=question)
        result.model = model
        prompt_schema = relevant_tables(schema, question, self.cfg.prompt.relevant_tables)
        last_error: str | None = None
        previous_raw: str | None = None
        frames: list[dict] = []
        lang = self.cfg.insight.language

        if stream:
            await stream(
                "plan",
                {"model": model, "schema_tables": len(schema.tables), "mode": "analysis"},
            )

        # phase 1+2: plan queries, execute them (nudge + regenerate on failure)
        for attempt in range(MAX_ATTEMPTS):
            result.attempts = attempt + 1
            messages = [
                {"role": "system", "content": system_prompt_for(self.backend.dialect)},
                {
                    "role": "user",
                    "content": build_prompt(
                        question,
                        prompt_schema,
                        semantic_text=semantic_text,
                        few_shots=few_shots,
                        language=lang,
                        max_tokens=self.cfg.prompt.max_tokens,
                    ),
                },
            ]
            if previous_raw and last_error:
                messages.append({"role": "assistant", "content": previous_raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Analysis failed: {last_error}. Return a corrected JSON "
                            'object with a valid "queries" list (read-only SQL).'
                        ),
                    }
                )
            raw = await complete(
                self.cfg,
                messages,
                json_mode=True,
                model=model,
                client=self.client,
                max_tokens=2000,
            )
            result.tokens += len(raw) // 4
            previous_raw = raw

            try:
                plan = parse_sql_plan(raw)
            except SqlGenError as exc:
                last_error = f"Invalid response from model: {exc}"
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
                continue

            if not plan.queries:
                if len(plan.reasoning.strip()) >= 60:
                    # model answered directly in prose (non-data question) — surface it
                    result.status = "no_data"
                    result.insight = plan.reasoning.strip()
                    result.reasoning = plan.reasoning
                    if stream:
                        await stream("insight", {"insight": result.insight})
                    return await self._finalize(
                        result, key=key, user=user, role=role, t0=t0, stream=stream
                    )
                last_error = "No analytical queries in response"
                if stream:
                    await stream("retry", {"attempt": attempt + 1, "error": last_error})
                continue

            # execute all planned queries; any failure → nudge and regenerate the plan
            frames = []
            all_ok = True
            for q in plan.queries[:4]:
                try:
                    qv = (
                        validate_mongo(q, self.cfg.security.row_limit)
                        if self.backend.dialect == "mongodb"
                        else validate(
                            q,
                            self.cfg.security.row_limit,
                            self.cfg.security.forbidden_tables,
                        )
                    )
                    df = await self.backend.execute(qv, self.cfg.security.query_timeout_s)
                    frames.append(
                        {
                            "query": q,
                            "columns": list(df.columns),
                            "rows": _rows_for_output(df)[:20],
                        }
                    )
                except (GuardError, DBError) as exc:
                    all_ok = False
                    last_error = f"Query gagal: {exc}"
                    if stream:
                        await stream("retry", {"attempt": attempt + 1, "error": last_error})
                    break
            if all_ok and frames:
                break
        else:
            result.status = "error"
            result.error = last_error or "Analysis queries failed"
            return await self._finalize(result, key=key, user=user, role=role, t0=t0, stream=stream)

        if result.status == "no_data":
            return result  # already finalized above

        # phase 3: data-grounded insight + recommendations
        result.sql = ""
        fin_prompt = build_final_prompt(question, frames, language=lang)
        raw2 = await complete(
            self.cfg,
            [
                {"role": "system", "content": "You produce JSON."},
                {"role": "user", "content": fin_prompt},
            ],
            json_mode=True,
            model=model,
            client=self.client,
            max_tokens=1200,
        )
        result.tokens += len(raw2) // 4
        insight, recs = _parse_analysis_answer(raw2)
        if not insight and not recs:
            result.status = "error"
            result.error = "Analisis gagal: respon akhir tidak valid"
            return await self._finalize(result, key=key, user=user, role=role, t0=t0, stream=stream)

        rec_text = ""
        if recs:
            numbered = "\n".join(f"{i}. {r}" for i, r in enumerate(recs, 1))
            rec_text = f"\n\n{'Rekomendasi:' if lang == 'id' else 'Recommendations:'}\n{numbered}"
        result.insight = f"{insight}{rec_text}".strip()
        result.status = "ok"
        if stream:
            await stream("insight", {"insight": result.insight})
        return await self._finalize(result, key=key, user=user, role=role, t0=t0, stream=stream)

    async def _finalize(
        self,
        result: AskResult,
        *,
        key: str,
        user: str,
        role: str,
        t0: float,
        stream: EventCallback | None,
    ) -> AskResult:
        """Shared tail: latency, audit, cache, done event."""
        result.latency_ms = int((time.monotonic() - t0) * 1000)

        # audit (PII-masked) + cache
        from contextlib import suppress

        with suppress(Exception):  # audit must never break the answer
            await self.audit.record(
                user=user,
                role=role,
                question=result.question,
                sql=mask_pii(result.sql) if result.sql else None,
                result_summary=result.insight[:200] if result.insight else None,
                latency_ms=result.latency_ms,
                tokens=result.tokens,
                model=result.model,
                status=result.status,
                error=result.error,
            )

        if result.status in ("ok", "no_data") and (not result.sql or is_cacheable(result.sql)):
            await self.cache.set(
                key,
                {
                    "sql": result.sql,
                    "reasoning": result.reasoning,
                    "insight": result.insight,
                    "chart": result.chart,
                    "row_count": result.row_count,
                    "rows": result.rows,
                    "tokens": result.tokens,
                    "model": result.model,
                    "status": result.status,
                    "attempts": result.attempts,
                },
            )
        if stream:
            await stream(
                "done",
                {
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "tokens": result.tokens,
                    "cached": result.cached,
                    "row_count": result.row_count,
                    "error": result.error,
                },
            )
        return result
