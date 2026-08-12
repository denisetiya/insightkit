# Changelog

## 0.1.0 (2026-08-08): rilis awal

Core pipeline:

* Schema extraction Postgres, MySQL, SQLite: tabel, kolom, PK, FK, row count, sample values
* Text-to-SQL: prompt builder dengan token budget, LLM OpenAI-compatible, JSON mode
* Self-correction maksimal 3 kali untuk SQL error dan guardrail reject
* Guardrail dua lapis: engine read-only plus validasi query
* Insight bahasa Inggris dan Indonesia plus chart Plotly
* PII masking sebelum ke LLM dan log

Akses dan eval:

* Audit log append-only, RBAC viewer/analyst/admin, API key hash plus JWT, rate limit
* Semantic layer YAML (metrik, glossary, alias)
* Few-shot store dengan retrieval keyword overlap
* Model routing untuk pertanyaan simpel
* Golden set eval dengan result-set comparison
* Cache hasil query dengan TTL, query volatile tidak di-cache

Interface:

* CLI: init, ask, serve, refresh, eval, golden, semantic, user, example-config
* REST API FastAPI plus SSE: auth token, ask, schema, schema refresh, health, audit, metrics
* Web UI satu file di `web/index.html`

Ops:

* Docker image non-root dengan healthcheck
* CI: lint, type check, test, build
* Konektor MongoDB (aggregation), OpenSearch (SQL plugin), Trino (REST)
