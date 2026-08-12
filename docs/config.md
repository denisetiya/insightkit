# Konfigurasi

File default `insightkit.yml` (buat dengan `insightkit example-config`). Setiap nilai bisa di-override env var `INSIGHTKIT_<SECTION>__<KEY>`. Secret sebaiknya lewat env, jangan tulis API key di file.

```yaml
database:
  url: postgresql+psycopg://user:pass@host:5432/db
  # Format SQLAlchemy async:
  # postgresql+psycopg://, mysql+asyncmy://, sqlite+aiosqlite://

llm:
  base_url: http://localhost:11434/v1
  api_key: ollama
  model: qwen2.5-coder
  fast_model: null
  timeout_s: 60
  max_retries: 2

security:
  row_limit: 10000
  query_timeout_s: 30
  pii_mask: true
  forbidden_tables: []

prompt:
  max_tokens: 3000
  max_few_shots: 3
  max_tables: 200

cache:
  ttl_s: 300

insight:
  language: en

api:
  jwt_secret: change-me
  jwt_expire_min: 60
  rate_limit_per_min: 60
  host: 0.0.0.0
  port: 8000

storage:
  path: ~/.insightkit
  meta_db: meta.db
```

Keterangan:

* `database.url` wajib diisi.
* `llm` mendukung endpoint OpenAI-compatible: Ollama, vLLM, OpenAI, DeepSeek.
* `security.forbidden_tables` berisi tabel yang diblokir, contoh `["salaries", "raw_logs"]`.
* `prompt.max_tokens` adalah budget token prompt. Schema yang melebihi budget diringkas otomatis.
* `api.jwt_secret` wajib diganti di produksi via env `INSIGHTKIT_API__JWT_SECRET`.

## Contoh semantic layer (`semantic.yml`)

```yaml
metrics:
  - name: revenue
    definition: "SUM(amount) FILTER (WHERE status = 'paid')"
    description: Total pendapatan dari order yang dibayar
glossary:
  churn: customer yang tidak order dalam 90 hari
aliases:
  omset: revenue
```

Definisi metrik dimasukkan ke prompt supaya jawaban konsisten antar user. Aktifkan dengan `--semantic semantic.yml` di CLI.

## Validasi

* Format salah atau nilai invalid memicu error jelas saat `init`.
* `insightkit semantic semantic.yml` untuk validasi file semantic.
