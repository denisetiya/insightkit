<div align="center">

# 📊 InsightKit

**Enterprise text-to-SQL analytics — natural language → SQL → insight**

Tanya datamu pakai bahasa natural, dapatkan insight + chart otomatis.
Dipakai **on-prem** di infrastruktur perusahaan, terhubung read-only ke database,
dengan audit, guardrails, dan RBAC bawaan.

[![Python](https://img.shields.io/badge/python-3.11+-2563eb?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-06b6d4)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/denisetiya/insightkit/ci.yml?label=CI&logo=github)](https://github.com/denisetiya/insightkit/actions)
[![GHCR](https://img.shields.io/github/actions/workflow/status/denisetiya/insightkit/publish.yml?label=GHCR&logo=docker)](https://github.com/denisetiya/insightkit/pkgs/container/insightkit)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-0b6e4f?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

</div>

---

## ✨ Fitur

| | |
|---|---|
| 🗣️ **Natural language → SQL** | Auto schema extraction, self-correcting (max 3x), JSON mode |
| 🛡️ **Keamanan berlapis** | DB read-only (2 lapis), guardrail query, PII masking, tabel blacklist |
| 📋 **Audit & compliance** | Append-only audit trail, RBAC (viewer/analyst/admin), JWT + API key |
| 📈 **Insight + chart** | Jawaban bahasa natural (EN/ID) + auto-chart Plotly + raw result JSON |
| 🗄️ **Multi-DB** | Postgres, MySQL, SQLite, MongoDB, OpenSearch, (Trino) |
| ⚡ **Cepat & hemat** | Streaming SSE, caching, model routing, prompt token-budget |
| 🎯 **Akurasi terukur** | Golden set evaluation + regression gate (≥ 90%) |
| 📦 **Deploy fleksibel** | pip, Docker (non-root), on-prem, air-gapped |

## 🚀 Quick start (2 menit)

```bash
# install
pip install insightkit

# config + init (auto schema extraction)
insightkit example-config -o insightkit.yml   # edit DSN + LLM
insightkit init -c insightkit.yml --create-admin admin

# tanya!
insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
```

**Atau langsung jalan sebagai API server + web UI:**

```bash
insightkit serve -c insightkit.yml        # API → http://localhost:8000
# buka web/chat.html di browser → isi URL + API key → tanya!
```

```bash
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "X-API-Key: ik_xxx" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue dari orders yang status paid?"}'
```

## 🖥️ Web UI (standalone)

`web/index.html` — chat UI single-file, tanpa build/server:

- Streaming SSE real-time
- Tabel hasil query + chart Plotly + SQL viewer
- API URL & key disimpan di localStorage

## 🏗️ Arsitektur

```
pertanyaan ─▶ cache ─▶ konteks (schema relevan + semantic + few-shot)
     ─▶ LLM (OpenAI-compatible) ─▶ SQL / aggregation
     ─▶ guardrail (read-only, row-limit, PII, blacklist)
     ─▶ execute (async, timeout) ─▶ self-correct (max 3x)
     ─▶ insight + chart + raw result ─▶ audit log + cache
```

## 📚 Dokumentasi

- [📦 Install & Deploy](docs/install.md) — pip / Docker / on-prem / air-gapped
- [🐳 Docker Guide](docs/docker-guide.md) — langkah-demi-langkah konek ke DB perusahaan (compose + LLM + security)
- [⚙️ Konfigurasi](docs/config.md) — YAML + env reference
- [💻 CLI](docs/cli.md) — semua perintah
- [🔌 API](docs/api.md) — per-endpoint (curl + TypeScript)
- [🔒 Keamanan](docs/security.md) — guardrails, RBAC, audit, PII
- [🧪 Evaluasi](docs/eval.md) — golden set & regression gate
- [📖 PRD](docs/PRD.md) — spesifikasi produk

## 🗄️ Database yang didukung

| DB | Status | Cara query |
|---|---|---|
| PostgreSQL | ✅ teruji live (10k rows) | SQL (SQLAlchemy async) |
| MySQL | ✅ teruji live | SQL (asyncmy) |
| SQLite | ✅ teruji live | SQL |
| MongoDB | ✅ teruji live | Aggregation pipeline (guard write-stage) |
| OpenSearch | ✅ teruji live | SQL plugin (REST) |
| Trino | 🔧 kode siap, belum teruji | REST statement API |

> LLM apa pun yang OpenAI-compatible bisa dipakai: Ollama, vLLM, OpenAI, DeepSeek, dll.

## 🛡️ Keamanan (intisari)

1. Koneksi **read-only** di level DB (`default_transaction_read_only`, `mode=ro`, session RO)
2. **Guardrail query**: tolak DROP/DELETE/UPDATE, multi-statement, blacklist tabel
3. **PII masking** sebelum LLM & log (email, telepon, NIK, kartu)
4. **RBAC** viewer/analyst/admin + rate limit
5. **Audit append-only** untuk setiap pertanyaan

## 🧪 Quality gates

```bash
uv run pytest                       # unit + integration
uv run pytest -m e2e                # live DB test (docker)
uv run insightkit eval -g golden.yml  # akurasi ≥ 90% (exit 1 jika gagal)
uv run mypy src/insightkit && uv run ruff check .   # type + lint
```

## 🗺️ Roadmap

- [ ] Dashboard admin web (setup wizard, audit viewer, few-shot curation)
- [ ] Conversation memory / follow-up ("kalau bulan ini?")
- [ ] Row-level security per role
- [ ] Slack/Teams bot & scheduled reports
- [ ] BigQuery / Snowflake connector
- [ ] OIDC SSO

## 📄 License

[Apache-2.0](LICENSE)
