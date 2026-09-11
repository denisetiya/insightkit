"""API tests — ASGI via httpx, mock LLM, real SQLite demo DB."""

from __future__ import annotations

import httpx
import pytest
from test_pipeline import make_mock_llm

from insightkit.api.app import create_app
from insightkit.config import Config
from insightkit.security.users import UserStore


def _cfg(demo_db, tmp_path) -> Config:
    return Config(
        database={"url": f"sqlite+aiosqlite:///{demo_db}"},
        llm={"base_url": "http://mock/v1", "api_key": "k", "model": "m", "max_retries": 0},
        storage={"path": str(tmp_path / "ik")},
        api={"jwt_secret": "test-secret"},
    )


@pytest.fixture
def app_and_key(demo_db, tmp_path):
    cfg = _cfg(demo_db, tmp_path)
    # seed admin + viewer users
    import asyncio

    store = UserStore(cfg)
    admin_key = asyncio.run(store.create("admin", "admin"))
    viewer_key = asyncio.run(store.create("viewer", "viewer"))
    client, transport = make_mock_llm(lambda content, msgs: ("SELECT 1", True))
    app = create_app(cfg, client=client)
    return app, admin_key, viewer_key


@pytest.mark.asyncio
async def test_health(app_and_key, tmp_path) -> None:
    app, _, _ = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_required(app_and_key) -> None:
    app, _, _ = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/v1/schema")
        assert r.status_code == 401
        r = await ac.get("/api/v1/schema", headers={"X-API-Key": "bogus"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_token_exchange_and_rbac(app_and_key) -> None:
    app, admin_key, viewer_key = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        # exchange
        r = await ac.post("/api/v1/auth/token", params={"x_api_key": admin_key})
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["role"] == "admin"

        # admin: audit OK
        r = await ac.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

        # viewer: audit forbidden
        rv = await ac.post("/api/v1/auth/token", params={"x_api_key": viewer_key})
        vtoken = rv.json()["token"]
        r = await ac.get("/api/v1/audit", headers={"Authorization": f"Bearer {vtoken}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_ask_sse_stream(app_and_key) -> None:
    app, admin_key, _ = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post(
            "/api/v1/ask",
            json={"question": "berapa total revenue?", "model": "custom-model-test"},
            headers={"X-API-Key": admin_key},
        )
    assert r.status_code == 200
    body = r.text
    assert "event: plan" in body
    assert "custom-model-test" in body
    assert "event: sql" in body
    assert "event: insight" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_schema_and_refresh_rbac(app_and_key) -> None:
    app, admin_key, viewer_key = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/v1/schema", headers={"X-API-Key": viewer_key})
        assert r.status_code == 200
        tables = {t["name"] for t in r.json()["tables"]}
        assert "orders" in tables and "customers" in tables

        # refresh requires admin
        r = await ac.post("/api/v1/schema/refresh", headers={"X-API-Key": viewer_key})
        assert r.status_code == 403
        r = await ac.post("/api/v1/schema/refresh", headers={"X-API-Key": admin_key})
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_metrics_recorded(app_and_key) -> None:
    app, admin_key, _ = app_and_key
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        await ac.post("/api/v1/ask", json={"question": "q1"}, headers={"X-API-Key": admin_key})
        r = await ac.get("/api/v1/metrics", headers={"X-API-Key": admin_key})
    data = r.json()
    assert data["requests"] == 1
    assert "p95" in data["latency_ms"]
