# API Reference

Base URL: `http://<host>:<port>`. Semua endpoint (kecuali `/health`) butuh auth. Format error: `{"detail": "..."}`.

**Auth — dua cara:**
1. **API key langsung**: header `X-API-Key: ik_...`
2. **JWT**: `POST /api/v1/auth/token` → `Authorization: Bearer <token>` (expiry `api.jwt_expire_min`)

**Role:** `viewer` (ask, schema, health) < `analyst` (+ metrics) < `admin` (+ audit, refresh, user).

---

## `POST /api/v1/auth/token`

Tukar API key → JWT.

| | |
|---|---|
| **Query param** | `x_api_key` (wajib) |
| **Auth** | tidak perlu |

**Contoh curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/token?x_api_key=ik_xxx"
```

**Contoh TypeScript:**
```ts
const res = await fetch(`${BASE}/api/v1/auth/token?x_api_key=${apiKey}`, { method: "POST" });
const { token, role } = await res.json(); // token: string, role: "admin"|"analyst"|"viewer"
```

**Response:** `{"token": "...", "username": "...", "role": "...", "expires_in_min": 60}`

---

## `POST /api/v1/ask`

Tanya bahasa natural → **SSE stream** (event: `plan`, `retry`, `schema_refresh`, `sql`, `result`, `insight`, `chart`, `done`).

| | |
|---|---|
| **Body (JSON)** | `{"question": string, "role_override": string|null}` |
| **Auth** | viewer+ |
| **Response** | `text/event-stream` |

**Contoh curl:**
```bash
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue bulan lalu?"}'
```

**Contoh TypeScript (SSE):**
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

**Event `result` payload:** `{"columns": [...], "rows": [{...}], "row_count": n}` — raw query result (PII-masked, max 50 baris, JSON-safe: Decimal→float, date→ISO string).

**Event `chart` payload:** `{"chart": {"data": [...], "layout": {...}}}` — plotly figure sebagai object (bukan string). Render dengan Plotly.js.

**Event `done` payload:** `{"status": "ok"|"no_data"|"error", "latency_ms", "tokens", "cached", "row_count", "error"}`

---

## `GET /api/v1/schema`

Schema yang ter-cache (tabel, kolom, tipe, PK/FK, row count).

| | |
|---|---|
| **Auth** | viewer+ |
| **Response** | `{"db_key", "dialect", "tables": [{name, row_count, columns: [{name, type, nullable, pk, fk_ref}]}]}` |

**Contoh curl:**
```bash
curl http://localhost:8000/api/v1/schema -H "X-API-Key: ik_xxx"
```

---

## `POST /api/v1/schema/refresh`

Re-introspect database.

| | |
|---|---|
| **Auth** | **admin** |
| **Response** | `{"status": "ok", "db_key": "..."}` |

---

## `GET /api/v1/health`

Status: database reachable, model, schema cache.

**Response:** `{"status": "ok"|"degraded", "database": bool, "model": "...", "schema_cached": bool}`

---

## `GET /api/v1/audit`

Audit trail (append-only). 

| | |
|---|---|
| **Query param** | `user`, `since` (ISO), `limit` (default 100, max 1000) |
| **Auth** | **admin** |

**Response:** `[{ts, user, role, question, sql, result_summary, latency_ms, tokens, model, status, error}]`

---

## `GET /api/v1/metrics`

Latency, token spend, cache hit rate.

| | |
|---|---|
| **Auth** | analyst+ |

**Response:** `{"requests", "errors", "latency_ms": {p50, p95, mean}, "tokens_total", "cache_hit_rate", "uptime_s"}`

---

## Rate limit

Per-user sliding window: `api.rate_limit_per_min` (default 60). Berlebih → `429 {"detail": "Rate limit exceeded"}`.
