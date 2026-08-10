# InsightKit Documentation

InsightKit — library enterprise-grade **text-to-SQL analytics** (on-prem). Natural language → SQL → insight, dipasang di infrastruktur perusahaan, read-only, audit & RBAC bawaan.

## Isi

| Doc | Isi |
|-----|-----|
| [install.md](install.md) | Install: pip, Docker, on-prem, air-gapped |
| [config.md](config.md) | Referensi config lengkap (YAML + env var) |
| [cli.md](cli.md) | Semua perintah CLI |
| [api.md](api.md) | Referensi API per-endpoint (header, body, param, contoh curl + TypeScript) |
| [security.md](security.md) | Model keamanan: guardrail, RBAC, audit, PII |
| [eval.md](eval.md) | Golden set & regression gate |

## Quick start (5 menit)

```bash
# 1. install
pip install insightkit            # atau docker (lihat install.md)

# 2. tulis config
insightkit example-config -o insightkit.yml   # lalu edit DSN + LLM

# 3. init — connect + auto schema extraction
insightkit init -c insightkit.yml --create-admin admin

# 4. tanya!
insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
```

## Arsitektur

```
pertanyaan ─▶ cache check ─▶ RAG konteks (schema+semantic+few-shot)
      ─▶ LLM (OpenAI-compatible) ─▶ SQL (JSON mode)
      ─▶ guardrail (read-only, row-limit, PII, blacklist)
      ─▶ execute (async, timeout) ─▶ self-correct (max 3x)
      ─▶ insight + chart ─▶ audit log + cache
```

## Stack inti

Python 3.11+ · FastAPI · SQLAlchemy 2.0 async · openai SDK (OpenAI-compatible) · polars · plotly · SQLite (meta store) · Typer · PyJWT. **Tanpa LangChain/LlamaIndex** — hand-rolled, ringan, audit-able.

## Budget performa (PRD)

| Metrik | Budget |
|--------|--------|
| p95 end-to-end query simpel | < 5s |
| first token (SSE) | < 1.5s |
| Introspection 100 tabel | < 10s (paralel) |
| Cache hit | < 100ms |
| Prompt rata-rata | ≤ 3k token |
