# Dokumentasi InsightKit

InsightKit adalah library text-to-SQL yang dipasang on-prem. Input bahasa natural, output SQL plus insight. Koneksi database read-only, audit dan RBAC bawaan.

## Isi

| Dokumen | Isi |
|---|---|
| [install.md](install.md) | Install via pip, Docker, on-prem, air-gapped |
| [config.md](config.md) | Referensi config lengkap (YAML dan env var) |
| [cli.md](cli.md) | Semua perintah CLI |
| [api.md](api.md) | Referensi API per endpoint |
| [security.md](security.md) | Guardrail, RBAC, audit, PII |
| [eval.md](eval.md) | Golden set dan regression gate |
| [docker-guide.md](docker-guide.md) | Hubungkan ke database perusahaan |
| [PRD.md](PRD.md) | Spesifikasi produk |

## Mulai cepat

```bash
pip install insightkit

insightkit example-config -o insightkit.yml
# edit DSN dan LLM di file tersebut

insightkit init -c insightkit.yml --create-admin admin

insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
```

## Arsitektur

```
pertanyaan -> cek cache -> konteks (schema, semantic, few-shot)
 -> LLM (OpenAI-compatible) -> SQL
 -> guardrail (read-only, row limit, PII, blacklist)
 -> eksekusi (async, timeout) -> koreksi otomatis (maks 3x)
 -> insight + chart -> audit log + cache
```

## Stack inti

Python 3.11+, FastAPI, SQLAlchemy 2.0 async, SDK OpenAI-compatible, polars, plotly, SQLite untuk meta store, Typer, PyJWT. Tanpa LangChain dan LlamaIndex. Pipeline ditulis langsung supaya mudah diaudit.
