"""MongoDB + OpenSearch backend E2E — requires docker containers (see README/test)."""

from __future__ import annotations

import json
import os

import pytest

from insightkit.config import Config
from insightkit.db.backends import MongoBackend, OpenSearchBackend, get_backend
from insightkit.security.guard import GuardError, validate_mongo

MONGO_URL = os.environ.get("INSIGHTKIT_TEST_MONGO", "mongodb://127.0.0.1:27017/shop")
OS_URL = os.environ.get(
    "INSIGHTKIT_TEST_OPENSEARCH",
    "opensearchs://admin:InsightKit%232026@127.0.0.1:9200",
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongo_backend_ping_introspect() -> None:
    cfg = Config(database={"url": MONGO_URL})
    backend = get_backend(cfg)
    assert isinstance(backend, MongoBackend)
    assert await backend.ping() is True

    meta = await backend.introspect("shop")
    names = {t.name for t in meta.tables}
    assert {"orders", "customers"} <= names
    orders = meta.table("orders")
    assert orders is not None
    assert any(c.name == "amount" for c in orders.columns)
    assert orders.row_count == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongo_backend_execute_aggregation() -> None:
    cfg = Config(database={"url": MONGO_URL})
    backend = get_backend(cfg)
    payload = json.dumps(
        {
            "collection": "orders",
            "pipeline": [
                {"$match": {"status": "paid"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ],
        }
    )
    df = await backend.execute(payload, timeout_s=10)
    assert df.height == 1
    assert df["total"][0] == 150.0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongo_guard_blocks_write_stages() -> None:
    bad = json.dumps(
        {
            "collection": "orders",
            "pipeline": [{"$match": {"status": "paid"}}, {"$out": "backup"}],
        }
    )
    with pytest.raises(GuardError, match="\\$out"):
        validate_mongo(bad, limit=100)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongo_guard_adds_limit() -> None:
    payload = json.dumps({"collection": "orders", "pipeline": [{"$match": {}}]})
    cleaned = json.loads(validate_mongo(payload, limit=5))
    assert cleaned["pipeline"][-1] == {"$limit": 5}


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opensearch_backend_ping_introspect() -> None:
    cfg = Config(database={"url": OS_URL})
    backend = get_backend(cfg)
    assert isinstance(backend, OpenSearchBackend)
    assert await backend.ping() is True

    meta = await backend.introspect("os")
    names = {t.name for t in meta.tables}
    assert "orders" in names
    orders = meta.table("orders")
    assert orders is not None
    assert any(c.name == "status" for c in orders.columns)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opensearch_backend_execute_sql() -> None:
    cfg = Config(database={"url": OS_URL})
    backend = get_backend(cfg)
    df = await backend.execute(
        "SELECT status, COUNT(*) AS n FROM orders GROUP BY status", timeout_s=10
    )
    assert df.height == 3
    assert df["n"].sum() == 3
