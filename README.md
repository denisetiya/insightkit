# InsightKit

Tanya database pakai bahasa Indonesia atau Inggris, dapat SQL, insight, dan chart.

InsightKit jalan on-prem di server sendiri. Koneksi database read-only. Setiap pertanyaan tercatat di audit log. Akses diatur per role.

[![Python](https://img.shields.io/badge/python-3.11+-2563eb?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-06b6d4)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/denisetiya/insightkit/ci.yml?label=CI&logo=github)](https://github.com/denisetiya/insightkit/actions)
[![GHCR](https://img.shields.io/github/actions/workflow/status/denisetiya/insightkit/publish.yml?label=GHCR&logo=docker)](https://github.com/denisetiya/insightkit/pkgs/container/insightkit)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-0b6e4f?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

## Fitur

* Natural language ke SQL. Schema dibaca otomatis dari database. Gagal eksekusi dicoba ulang maksimal 3 kali.
* Keamanan dua lapis. User database read-only ditambah validasi query sebelum eksekusi. PII di-mask sebelum dikirim ke LLM dan sebelum masuk log. Tabel sensitif bisa diblokir.
* Audit dan akses. Audit log append-only. Tiga role: viewer, analyst, admin. Auth pakai API key dan JWT.
* Hasil lengkap. Insight dalam bahasa Inggris atau Indonesia, chart Plotly otomatis, dan raw rows dalam JSON.
* Banyak database. PostgreSQL, MySQL, SQLite, MongoDB, OpenSearch, Trino.
* Hemat token dan cepat. Streaming SSE, cache hasil query, model routing untuk pertanyaan simpel, budget token untuk prompt.
* Eval terukur. Golden set dengan regression gate di CI.

## Mulai cepat

```bash
pip install insightkit

insightkit example-config -o insightkit.yml
# edit insightkit.yml: isi database.url dan llm.base_url

insightkit init -c insightkit.yml --create-admin admin

insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
```

Jalan sebagai API server:

```bash
insightkit serve -c insightkit.yml
# API di http://localhost:8000
# buka web/index.html di browser, isi URL dan API key, lalu tanya
```

```bash
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "X-API-Key: ik_xxx" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue dari orders yang status paid?"}'
```

## Web UI

`web/index.html` adalah chat UI satu file. Tidak perlu build.

* Streaming SSE
* Tabel hasil, chart Plotly, viewer SQL
* URL API dan key disimpan di localStorage browser

## Arsitektur

```
pertanyaan -> cek cache -> susun konteks (schema, semantic, few-shot)
  -> LLM (OpenAI-compatible) -> SQL
  -> validasi (read-only, row limit, PII, blacklist)
  -> eksekusi (async, timeout) -> koreksi otomatis bila gagal (maks 3x)
  -> insight + chart + raw rows -> audit log + cache
```

## Dokumentasi

* [Install dan Deploy](docs/install.md)
* [Panduan Docker](docs/docker-guide.md)
* [Konfigurasi](docs/config.md)
* [CLI](docs/cli.md)
* [API](docs/api.md)
* [Keamanan](docs/security.md)
* [Evaluasi](docs/eval.md)
* [PRD](docs/PRD.md)

## Database

| DB | Cara query |
|---|---|
| PostgreSQL | SQL via SQLAlchemy async |
| MySQL | SQL via asyncmy |
| SQLite | SQL |
| MongoDB | Aggregation pipeline, write stage diblokir |
| OpenSearch | SQL plugin via REST |
| Trino | REST statement API |

LLM apa pun yang OpenAI-compatible bisa dipakai: Ollama, vLLM, OpenAI, DeepSeek.

## Keamanan

1. Koneksi read-only di level database. PostgreSQL pakai `default_transaction_read_only`, SQLite pakai `mode=ro`, MySQL pakai session read-only.
2. Validasi query sebelum eksekusi. Tolak DROP, DELETE, UPDATE, multi-statement, dan tabel yang diblokir.
3. PII di-mask sebelum ke LLM dan log (email, telepon, NIK, kartu).
4. RBAC viewer, analyst, admin, plus rate limit per user.
5. Audit append-only untuk setiap pertanyaan.

## Quality gates

```bash
uv run pytest
uv run pytest -m e2e
uv run insightkit eval -g golden.yml
uv run mypy src/insightkit && uv run ruff check .
```

## Rencana lanjut

* Dashboard admin web (setup wizard, audit viewer, kurasi few-shot)
* Memory percakapan untuk follow-up
* Row-level security per role
* Bot Slack/Teams dan scheduled report
* Konektor BigQuery dan Snowflake
* OIDC SSO

## Lisensi

[Apache-2.0](LICENSE)
