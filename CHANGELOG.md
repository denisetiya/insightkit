# Changelog

## 0.1.0 (2026-08-08) — MVP

**Core pipeline**
- Auto schema extraction (introspection paralel): Postgres + SQLite (tabel, kolom, PK/FK, row count, sample values)
- Text-to-SQL hand-rolled: prompt builder dengan token budget, LLM OpenAI-compatible (Ollama/vLLM/OpenAI/DeepSeek), JSON mode
- Self-correction loop (max 3x): SQL error / guardrail reject / decline → feedback ke LLM → regenerate
- Guardrails 2 lapis: engine read-only (SQLite `mode=ro`, PG `default_transaction_read_only`, MySQL session RO) + query-level check
- Insight bahasa natural (EN/ID) + auto-chart plotly
- PII masking (email, telepon, NIK, kartu) sebelum LLM & log

**Enterprise**
- Audit log append-only, RBAC 3 role (viewer/analyst/admin), API key (SHA-256) + JWT, rate limit
- Semantic layer YAML (metrik, glossary, alias)
- Few-shot store + retrieval keyword-overlap
- Model routing (fast model untuk query simpel)
- Golden set eval dengan result-set comparison (regression gate ≥ 90%)
- Cache hasil query (TTL, volatile-aware)

**Interfaces**
- CLI: `init`, `ask`, `serve`, `refresh`, `eval`, `golden`, `semantic`, `user`, `example-config`
- REST API (FastAPI + SSE streaming): `/auth/token`, `/ask`, `/schema`, `/schema/refresh`, `/health`, `/audit`, `/metrics`

**Ops**
- Docker image (slim, non-root, healthcheck), docs lengkap, CI (lint/mypy/test/build), benchmark gate
- Performa terverifikasi: pipeline 54ms, cache hit 59ms, introspection 100 tabel 397ms (semua < budget)
