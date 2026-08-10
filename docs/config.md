# Konfigurasi

File default `insightkit.yml` (bisa dibuat dengan `insightkit example-config`). Setiap nilai bisa di-override env var `INSIGHTKIT_<SECTION>__<KEY>` — berguna untuk secret (jangan taruh API key di file).

```yaml
database:
  url: postgresql+psycopg://user:pass@host:5432/db   # WAJIB. Format SQLAlchemy async:
                                                     # postgresql+psycopg:// | mysql+asyncmy:// | sqlite+aiosqlite://

llm:
  base_url: http://localhost:11434/v1                # OpenAI-compatible endpoint (Ollama/vLLM/OpenAI/DeepSeek)
  api_key: ollama                                    # secret — pakai env INSIGHTKIT_LLM__API_KEY
  model: qwen2.5-coder                               # model default (kompleks)
  fast_model: null                                   # model murah untuk pertanyaan simpel (model routing)
  timeout_s: 60
  max_retries: 2

security:
  row_limit: 10000        # baris maks per query
  query_timeout_s: 30     # timeout eksekusi SQL
  pii_mask: true          # mask email/telepon/NIK/kartu sebelum ke LLM & log
  forbidden_tables: []    # tabel yang diblokir, mis. ["salaries", "raw_logs"]

prompt:
  max_tokens: 3000        # budget token prompt (schema di-ringkas bila lebih)
  max_few_shots: 3
  max_tables: 200         # >200 tabel → schema di-trim; RAG wajib di fase lanjut

cache:
  ttl_s: 300              # TTL cache hasil query (query volatile tidak di-cache)

insight:
  language: en            # en | id — bahasa output insight

api:
  jwt_secret: change-me   # WAJIB ganti di produksi (env INSIGHTKIT_API__JWT_SECRET)
  jwt_expire_min: 60
  rate_limit_per_min: 60
  host: 0.0.0.0
  port: 8000

storage:
  path: ~/.insightkit     # meta store: schema cache, audit, cache, users, few-shot
  meta_db: meta.db
```

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

Definisi metrik di-inject ke prompt → jawaban konsisten antar user. Aktifkan dengan `--semantic semantic.yml` di CLI, atau set di server.

## Validasi

- Salah format / nilai invalid → error jelas saat `init` (pydantic).
- `insightkit semantic semantic.yml` — validasi file semantic.
