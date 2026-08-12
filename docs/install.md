# Install dan Deploy

## 1. pip

```bash
pip install insightkit
insightkit example-config -o insightkit.yml
insightkit init -c insightkit.yml
```

Butuh Python 3.11+.

## 2. Docker

```bash
docker build -t insightkit:0.1.0 .
# atau dari registry private:
# docker pull ghcr.io/<org>/insightkit:0.1.0

docker run -d \
  --name insightkit \
  -p 8000:8000 \
  -v /srv/insightkit-data:/data \
  -e INSIGHTKIT_DATABASE__URL='postgresql+psycopg://ro_user:***@db.internal:5432/prod' \
  -e INSIGHTKIT_LLM__BASE_URL='http://llm.internal:11434/v1' \
  -e INSIGHTKIT_LLM__API_KEY='ollama' \
  -e INSIGHTKIT_LLM__MODEL='qwen2.5-coder' \
  -e INSIGHTKIT_API__JWT_SECRET='$(openssl rand -hex 32)' \
  ghcr.io/<org>/insightkit:0.1.0
```

* Image jalan sebagai non-root (user `insightkit`), ada healthcheck di `/api/v1/health`.
* `/data` adalah meta store (audit log, cache, schema cache, users). Wajib dipasang sebagai volume persistent.
* Config via env `INSIGHTKIT_<SECTION>__<KEY>`. Nilai env mengalahkan YAML.

## 3. On-prem di server perusahaan

Yang perlu disiapkan perusahaan:

| Item | Keterangan |
|---|---|
| Akses database read-only | Satu user khusus, bukan admin. Contoh Postgres: `GRANT CONNECT, SELECT ON ALL TABLES IN SCHEMA public TO insightkit_ro;` |
| LLM | API key sendiri, atau model self-host (Ollama atau vLLM) di infra mereka |
| Admin pertama | `insightkit user create --username admin --role admin` |
| Opsional | SSO OIDC tahap lanjut, export audit, scrape Prometheus ke `/api/v1/metrics` |

## 4. Air-gapped

Semua komponen jalan offline:

* LLM self-host: Ollama atau vLLM di GPU internal.
* Tidak ada embedding untuk schema sampai 200 tabel.
* Install: transfer wheel plus deps via registry PyPI internal, atau image Docker di registry internal.

Tidak ada panggilan keluar yang wajib. Library hanya memanggil `llm.base_url` yang kamu tentukan.

## 5. Upgrade dan rollback

* Meta store SQLite backward-compatible (DDL idempotent).
* Image Docker di-tag semver. Rollback artinya deploy image lama plus restore `/data` dari backup.
* Golden set eval wajib minimal 90 persen sebelum upgrade (lihat [eval.md](eval.md)).
