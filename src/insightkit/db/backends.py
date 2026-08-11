"""Backend abstraction — one interface for every database type.

- SQL backends (Postgres/MySQL/SQLite/…): SQLAlchemy async
- MongoDB: aggregation pipelines (motor)
- OpenSearch: SQL plugin over REST (httpx)
- Trino: REST statement API (httpx)

The pipeline only talks to `Backend` — adding a database type = adding one class.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import httpx
import polars as pl

from insightkit.config import Config
from insightkit.db.schema import ColumnMeta, SchemaMetadata, TableMeta


class Backend(ABC):
    dialect: str = ""

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def introspect(self, db_key: str) -> SchemaMetadata: ...

    @abstractmethod
    async def execute(self, query: str, timeout_s: float = 30.0) -> pl.DataFrame: ...


# --------------------------------------------------------------------------- SQL


class SQLBackend(Backend):
    """SQLAlchemy async backend — Postgres, MySQL, SQLite."""

    def __init__(self, cfg: Config) -> None:
        from insightkit.db.connector import build_engine

        self.cfg = cfg
        self.engine = build_engine(cfg)
        self.dialect = self.engine.url.get_backend_name()

    async def ping(self) -> bool:
        from insightkit.db.connector import ping

        return await ping(self.engine)

    async def introspect(self, db_key: str) -> SchemaMetadata:
        from insightkit.db.introspect import introspect

        async with self.engine.connect() as conn:
            return await introspect(conn, db_key, self.dialect)

    async def execute(self, query: str, timeout_s: float = 30.0) -> pl.DataFrame:
        from insightkit.db.executor import execute_query

        return await execute_query(self.engine, query, timeout_s)


# ----------------------------------------------------------------------- MongoDB


class MongoBackend(Backend):
    """MongoDB — LLM generates an aggregation pipeline: {"collection", "pipeline"}."""

    dialect = "mongodb"

    def __init__(self, cfg: Config) -> None:
        import motor.motor_asyncio

        parsed = urlparse(cfg.database.url)
        if parsed.scheme not in {"mongodb", "mongodb+srv"}:
            raise ValueError(f"Invalid MongoDB URL: {cfg.database.url}")
        dbname = (parsed.path or "/").lstrip("/") or "test"
        self._dbname = dbname
        uri = cfg.database.url
        if parsed.scheme == "mongodb" and parsed.path:
            # strip db name from path so client connects to server
            uri = uri.replace(f"/{dbname}", "", 1)
        self._client: Any = motor.motor_asyncio.AsyncIOMotorClient(
            uri, serverSelectionTimeoutMS=5000
        )
        self._db = self._client[dbname]

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def introspect(self, db_key: str) -> SchemaMetadata:
        names = await self._db.list_collection_names()
        tables: list[TableMeta] = []
        for name in sorted(names):
            sample = await self._db[name].find_one({})
            count = await self._db[name].estimated_document_count()
            columns: list[ColumnMeta] = []
            sample_values: dict[str, list[str]] = {}
            if sample:
                for key, value in sample.items():
                    if key == "_id":
                        continue
                    columns.append(
                        ColumnMeta(name=key, data_type=_mongo_type(value), nullable=True)
                    )
                    if isinstance(value, (str, int, float, bool)):
                        sample_values[key] = [str(value)]
            tables.append(
                TableMeta(name=name, columns=columns, row_count=count, sample=sample_values)
            )
        return SchemaMetadata(db_key=db_key, dialect=self.dialect, tables=tables)

    async def execute(self, query: str, timeout_s: float = 30.0) -> pl.DataFrame:
        import asyncio

        payload = json.loads(query)
        collection = payload.get("collection")
        pipeline = payload.get("pipeline")
        if not collection or not isinstance(pipeline, list):
            raise ValueError("MongoDB query must be {\"collection\": ..., \"pipeline\": [...]}")
        cursor = self._db[collection].aggregate(pipeline)
        docs = await asyncio.wait_for(cursor.to_list(length=None), timeout=timeout_s)
        if not docs:
            return pl.DataFrame()
        # flatten one level; nested → JSON string
        keys: list[str] = []
        for doc in docs:
            for k in doc:
                if k not in keys:
                    keys.append(k)
        data = {
            k: [_flatten(doc.get(k)) for doc in docs]
            for k in keys
        }
        return pl.DataFrame(data)


def _mongo_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, dict):
        return "OBJECT"
    if isinstance(value, list):
        return "ARRAY"
    return "STRING"


def _flatten(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


# --------------------------------------------------------------------- OpenSearch


class OpenSearchBackend(Backend):
    """OpenSearch — SQL plugin over REST (SELECT only by design)."""

    dialect = "opensearch"

    def __init__(self, cfg: Config) -> None:
        parsed = urlparse(cfg.database.url)
        if parsed.scheme not in {"opensearch", "opensearchs"}:
            raise ValueError(f"Invalid OpenSearch URL: {cfg.database.url}")
        http_scheme = "https" if parsed.scheme == "opensearchs" else "http"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9200
        self._base = f"{http_scheme}://{host}:{port}"
        self._index = (parsed.path or "/").lstrip("/") or None
        auth = None
        if parsed.username:
            from urllib.parse import unquote

            auth = (parsed.username, unquote(parsed.password or ""))
        # verify=False: OpenSearch ships a self-signed cert by default
        self._client = httpx.AsyncClient(
            base_url=self._base, auth=auth, timeout=15.0, verify=False
        )
        self._sql_endpoint = "/_plugins/_sql"

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/")
            return r.status_code < 500
        except Exception:
            return False

    async def introspect(self, db_key: str) -> SchemaMetadata:
        r = await self._client.get("/_cat/indices", params={"format": "json"})
        r.raise_for_status()
        indices = r.json()
        tables: list[TableMeta] = []
        for idx in indices:
            name = idx.get("index")
            if not name or name.startswith("."):
                continue
            if self._index and name != self._index:
                continue
            count = idx.get("docs.count")
            mapping = await self._mapping(name)
            columns = [
                ColumnMeta(name=fld, data_type=meta.get("type", "keyword").upper(), nullable=True)
                for fld, meta in mapping.get("properties", {}).items()
            ]
            tables.append(
                TableMeta(
                    name=name,
                    columns=columns,
                    row_count=int(count) if count else None,
                )
            )
        return SchemaMetadata(db_key=db_key, dialect=self.dialect, tables=tables)

    async def _mapping(self, index: str) -> dict:
        r = await self._client.get(f"/{index}/_mapping")
        r.raise_for_status()
        data = r.json()
        for idx_meta in data.values():
            if isinstance(idx_meta, dict) and "mappings" in idx_meta:
                return idx_meta["mappings"]
        return {}

    async def execute(self, query: str, timeout_s: float = 30.0) -> pl.DataFrame:
        rows, cols = await self._run_sql(query, timeout_s)
        if not cols:
            return pl.DataFrame()
        if not rows:
            return pl.DataFrame(schema=[(c, pl.Utf8) for c in cols])
        return pl.DataFrame({c: [r[i] for r in rows] for i, c in enumerate(cols)})

    async def _run_sql(self, sql: str, timeout_s: float = 15.0) -> tuple[list[list], list[str]]:
        r = await self._client.post(
            self._sql_endpoint, params={"format": "json"}, json={"query": sql}, timeout=timeout_s
        )
        r.raise_for_status()
        data = r.json()
        cols = [c["name"] for c in data.get("columns", [])]
        rows = [
            list(row.values()) if isinstance(row, dict) else list(row)
            for row in data.get("datarows", [])
        ]
        if not rows and data.get("aggregations"):
            rows, cols = self._parse_aggregations(data["aggregations"], cols)
        return rows, cols

    @staticmethod
    def _parse_aggregations(agg: dict, cols: list[str]) -> tuple[list[list], list[str]]:
        """OpenSearch JSON format returns GROUP BY results under `aggregations`."""
        rows: list[list] = []
        for v in agg.values():
            if isinstance(v, dict) and "buckets" in v:
                metrics = [
                    k for k in v["buckets"][0]
                    if k not in {"key", "key_as_string"} and isinstance(v["buckets"][0][k], dict)
                ] if v["buckets"] else []
                if cols:
                    cols = [cols[0]] + cols[1:] if len(cols) > 1 else ["key"] + metrics
                else:
                    cols = ["key"] + metrics
                for bucket in v["buckets"]:
                    row = [bucket.get("key")]
                    for m in metrics:
                        val = bucket.get(m)
                        row.append(val.get("value") if isinstance(val, dict) else val)
                    rows.append(row)
                break
            if isinstance(v, dict) and "value" in v:
                if not cols:
                    cols = [k for k in agg if isinstance(agg[k], dict) and "value" in agg[k]]
                rows.append(
                    [
                        x["value"] if isinstance(x, dict) and "value" in x else x
                        for x in agg.values()
                    ]
                )
                break
        return rows, cols


# ------------------------------------------------------------------------- Trino


class TrinoBackend(Backend):
    """Trino — REST statement API (POST /v1/statement, poll nextUri)."""

    dialect = "trino"

    def __init__(self, cfg: Config) -> None:
        parsed = urlparse(cfg.database.url)
        if parsed.scheme != "trino":
            raise ValueError(f"Invalid Trino URL: {cfg.database.url}")
        self._base = f"http://{parsed.netloc}"
        path_parts = (parsed.path or "").strip("/").split("/")
        self._catalog = path_parts[0] if path_parts and path_parts[0] else "memory"
        self._schema = path_parts[1] if len(path_parts) > 1 else "default"
        self._client = httpx.AsyncClient(base_url=self._base, timeout=20.0)

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/v1/info")
            return r.status_code == 200
        except Exception:
            return False

    async def introspect(self, db_key: str) -> SchemaMetadata:
        rows, cols = await self._query(
            f"SELECT table_schema, table_name FROM information_schema.tables "
            f"WHERE table_catalog = '{self._catalog}' ORDER BY table_name"
        )
        s_idx = cols.index("table_schema") if "table_schema" in cols else 0
        n_idx = cols.index("table_name") if "table_name" in cols else 1
        tables: list[TableMeta] = []
        for r in rows:
            schema = r[s_idx] if s_idx < len(r) else self._schema
            name = r[n_idx] if n_idx < len(r) else ""
            col_rows, col_cols = await self._query(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_catalog = '{self._catalog}' AND table_schema = '{schema}' "
                f"AND table_name = '{name}'"
            )
            c_name = col_cols.index("column_name") if "column_name" in col_cols else 0
            c_type = col_cols.index("data_type") if "data_type" in col_cols else 1
            columns = [
                ColumnMeta(name=cr[c_name], data_type=str(cr[c_type]))
                for cr in col_rows
            ]
            tables.append(TableMeta(name=name, columns=columns))
        return SchemaMetadata(db_key=db_key, dialect=self.dialect, tables=tables)

    async def execute(self, query: str, timeout_s: float = 30.0) -> pl.DataFrame:
        rows, cols = await self._query(query, timeout_s)
        if not cols:
            return pl.DataFrame()
        if not rows:
            return pl.DataFrame(schema=[(c, pl.Utf8) for c in cols])
        return pl.DataFrame({c: [r[i] for r in rows] for i, c in enumerate(cols)})

    async def _query(self, sql: str, timeout_s: float = 30.0) -> tuple[list[list], list[str]]:
        import asyncio

        r = await self._client.post("/v1/statement", json={"query": sql})
        r.raise_for_status()
        state = r.json()
        cols: list[str] = []
        rows: list[list] = []
        async with asyncio.timeout(timeout_s):
            while True:
                if state.get("columns"):
                    cols = [c["name"] for c in state["columns"]]
                for data_row in state.get("data", []):
                    rows.append(list(data_row))
                uri = state.get("nextUri")
                if not uri:
                    break
                r = await self._client.get(uri)
                r.raise_for_status()
                state = r.json()
        return rows, cols


# ---------------------------------------------------------------------- factory


def get_backend(cfg: Config) -> Backend:
    scheme = urlparse(cfg.database.url).scheme
    if scheme in {"mongodb", "mongodb+srv"}:
        return MongoBackend(cfg)
    if scheme in {"opensearch", "opensearchs"}:
        return OpenSearchBackend(cfg)
    if scheme == "trino":
        return TrinoBackend(cfg)
    return SQLBackend(cfg)
