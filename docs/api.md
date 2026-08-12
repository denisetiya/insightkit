# Referensi API

Base URL: `http://<host>:<port>`. Semua endpoint kecuali `/health` butuh auth. Format error: `{"detail": "..."}`.

Auth ada dua cara:

1. API key langsung di header `X-API-Key: ik_...`
2. JWT via `POST /api/v1/auth/token`, lalu pakai header `Authorization: Bearer <token>`. Masa berlaku diatur `api.jwt_expire_min`.

Role berjenjang: `viewer` bisa ask, schema, health. `analyst` tambah metrics. `admin` tambah audit, refresh, dan manajemen user.

## POST /api/v1/auth/token

Tukar API key menjadi JWT.

Query param: `x_api_key` (wajib). Tanpa auth.

```bash
curl -X POST "http://localhost:8000/api/v1/auth/token?x_api_key=ik_xxx"
```

```ts
const res = await fetch(`${BASE}/api/v1/auth/token?x_api_key=${apiKey}`, { method: "POST" });
const { token, role } = await res.json();
```

Response: `{"token": "...", "username": "...", "role": "...", "expires_in_min": 60}`

## POST /api/v1/ask

Pertanyaan bahasa natural dengan SSE stream. Event: `plan`, `retry`, `schema_refresh`, `sql`, `result`, `insight`, `chart`, `done`.

Body JSON: `{"question": string}`. Auth minimal viewer. Response `text/event-stream`.

```bash
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue bulan lalu?"}'
```

```ts
const res = await fetch(`${BASE}/api/v1/ask`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ question: "berapa total revenue bulan lalu?" }),
});
const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  for (const block of buffer.split("\n\n")) {
    if (!block.includes("event:")) continue;
    const event = block.match(/event: (\w+)/)?.[1];
    const data = JSON.parse(block.match(/data: (.+)/s)?.[1] ?? "{}");
    if (event === "insight") console.log(data.insight);
    if (event === "done") { console.log(data.status, data.latency_ms); return; }
  }
}
```

Event `result`: `{"columns": [...], "rows": [{...}], "row_count": n}`. Isi result sudah PII-mask, maksimal 50 baris, JSON-safe (Decimal ke float, date ke string ISO).

Event `chart`: `{"chart": {"data": [...], "layout": {...}}}`. Plotly figure sebagai object. Render dengan Plotly.js.

Event `done`: `{"status": "ok" atau "no_data" atau "error", "latency_ms", "tokens", "cached", "row_count", "error"}`

## GET /api/v1/schema

Schema yang ter-cache: tabel, kolom, tipe, PK dan FK, row count. Auth minimal viewer.

```bash
curl http://localhost:8000/api/v1/schema -H "X-API-Key: ik_xxx"
```

Response: `{"db_key", "dialect", "tables": [{name, row_count, columns: [{name, type, nullable, pk, fk_ref}]}]}`

## POST /api/v1/schema/refresh

Baca ulang schema database. Auth khusus admin.

Response: `{"status": "ok", "db_key": "..."}`

## GET /api/v1/health

Status database, model, dan schema cache. Tanpa auth.

Response: `{"status": "ok" atau "degraded", "database": bool, "model": "...", "schema_cached": bool}`

## GET /api/v1/audit

Audit trail append-only. Auth khusus admin.

Query param: `user`, `since` (ISO), `limit` (default 100, maksimal 1000).

Response: array berisi `ts, user, role, question, sql, result_summary, latency_ms, tokens, model, status, error`.

## GET /api/v1/metrics

Latency, token spend, cache hit rate. Auth minimal analyst.

Response: `{"requests", "errors", "latency_ms": {p50, p95, mean}, "tokens_total", "cache_hit_rate", "uptime_s"}`

## Rate limit

Per user sliding window sesuai `api.rate_limit_per_min` (default 60). Kelebihan limit mengembalikan `429 {"detail": "Rate limit exceeded"}`.
