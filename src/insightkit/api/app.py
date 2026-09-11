"""FastAPI application — streaming /ask, schema, health, audit, metrics."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from insightkit.api.auth import RateLimiter, create_jwt, require_role
from insightkit.api.metrics import Metrics
from insightkit.config import Config
from insightkit.pipeline import InsightKit
from insightkit.security.users import UserStore
from insightkit.semantic import SemanticLayer


class AskBody(BaseModel):
    question: str
    model: str | None = None
    role_override: str | None = None  # reserved for future per-request role scoping


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(
    cfg: Config,
    semantic: SemanticLayer | None = None,
    client: AsyncOpenAI | None = None,
) -> FastAPI:
    app = FastAPI(title="InsightKit API", version="0.1.0")
    # open CORS: API key auth protects the endpoints; UI dijalankan dari file:// / origin lain
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _init_state() -> None:
        app.state.kit = InsightKit(cfg, semantic=semantic, client=client)
        app.state.cfg = cfg
        app.state.metrics = Metrics()
        app.state.rate_limiter = RateLimiter(cfg.api.rate_limit_per_min)

    _init_state()  # eager init — works with ASGI transports that skip lifespan

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.kit.close()

    app.router.lifespan_context = lifespan

    @app.post("/api/v1/auth/token")
    async def exchange_api_key(x_api_key: str = Query(...)) -> dict:
        """Exchange an API key for a short-lived JWT."""
        cfg: Config = app.state.cfg
        user = await UserStore(cfg).verify(x_api_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        token = create_jwt(cfg, user["username"], user["role"])
        return {
            "token": token,
            "username": user["username"],
            "role": user["role"],
            "expires_in_min": cfg.api.jwt_expire_min,
        }

    @app.post("/api/v1/ask")
    async def ask(
        body: AskBody,
        auth: dict = Depends(require_role("viewer")),
    ) -> StreamingResponse:
        """Streamed natural-language question → insight (SSE events)."""
        kit: InsightKit = app.state.kit
        metrics: Metrics = app.state.metrics

        async def event_generator():
            queue: asyncio.Queue = asyncio.Queue()
            result_holder: dict = {}

            async def cb(event: str, data: dict) -> None:
                if event == "done":
                    result_holder["result"] = data
                await queue.put((event, data))

            task = asyncio.create_task(
                kit.ask(
                    body.question,
                    user=auth["username"],
                    role=auth["role"],
                    stream=cb,
                    model=body.model,
                )
            )

            try:
                while True:
                    try:
                        event, data = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except TimeoutError:
                        if task.done() and queue.empty():
                            break
                        continue
                    if event == "done":
                        metrics.record(
                            latency_ms=int(data.get("latency_ms", 0)),
                            tokens=int(data.get("tokens", 0)),
                            cached=bool(data.get("cached", False)),
                            ok=data.get("status") == "ok",
                        )
                        yield _sse("done", data)
                        break
                    yield _sse(event, data)
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/api/v1/schema")
    async def schema_view(auth: dict = Depends(require_role("viewer"))) -> dict:
        kit: InsightKit = app.state.kit
        schema = await kit.get_schema()
        return {
            "db_key": kit.db_key,
            "dialect": schema.dialect,
            "tables": [
                {
                    "name": t.name,
                    "row_count": t.row_count,
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.data_type,
                            "nullable": c.nullable,
                            "pk": c.is_pk,
                            "fk_ref": c.fk_ref,
                        }
                        for c in t.columns
                    ],
                }
                for t in schema.tables
            ],
        }

    @app.post("/api/v1/schema/refresh")
    async def schema_refresh(auth: dict = Depends(require_role("admin"))) -> dict:
        kit: InsightKit = app.state.kit
        await kit.refresh_schema()
        return {"status": "ok", "db_key": kit.db_key}

    @app.get("/api/v1/health")
    async def health() -> dict:
        kit: InsightKit = app.state.kit
        db_ok = False
        try:
            db_ok = await kit.backend.ping()
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "model": kit.cfg.llm.model,
            "schema_cached": kit._schema is not None,
        }

    @app.get("/api/v1/audit")
    async def audit(
        user: str | None = Query(default=None),
        since: str | None = Query(default=None),
        limit: int = Query(default=100, le=1000),
        auth: dict = Depends(require_role("admin")),
    ) -> list[dict]:
        kit: InsightKit = app.state.kit
        return await kit.audit.query(user=user, since=since, limit=limit)

    @app.get("/api/v1/metrics")
    async def metrics_view(auth: dict = Depends(require_role("analyst"))) -> dict:
        metrics: Metrics = app.state.metrics
        return metrics.snapshot()

    return app


def run_server(
    cfg: Config,
    semantic_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Start uvicorn with the configured app (used by `insightkit serve`)."""
    semantic = SemanticLayer.load(semantic_path) if semantic_path else None
    app = create_app(cfg, semantic=semantic)
    uvicorn.run(
        app,
        host=host or cfg.api.host,
        port=port or cfg.api.port,
        log_level="info",
    )
