# Install & Deployment

## 1. pip (tim data engineer, quick start)

```bash
pip install insightkit
insightkit example-config -o insightkit.yml
insightkit init -c insightkit.yml
```

Requirement: Python 3.11+.

## 2. Docker (standar enterprise)

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

- Image non-root (user `insightkit`, uid 1001), healthcheck `/api/v1/health`.
- `/data` = meta store (audit log, cache, schema cache, users) — **wajib volume persistent**.
- Konfigurasi via env `INSIGHTKIT_<SECTION>__<KEY>` (mengalahkan YAML).

## 3. On-prem di server perusahaan (VM/K8s)

Kebutuhan dari sisi perusahaan:

| Item | Keterangan |
|------|-----------|
| Akses DB read-only | satu user khusus (bukan admin). PG: `GRANT CONNECT, SELECT ON ALL TABLES IN SCHEMA public TO insightkit_ro;` |
| LLM | API key sendiri, atau model self-host (Ollama/vLLM) di infra mereka |
| Admin pertama | `insightkit user create --username admin --role admin` |
| Opsional | SSO OIDC (fase lanjut), audit export, Prometheus scrape `/api/v1/metrics` |

## 4. Air-gapped (bank/pemerintah — tanpa internet)

Semua komponen berjalan offline:

- LLM self-host: Ollama atau vLLM di GPU internal (model `qwen2.5-coder` / `deepseek-coder` / model lain yang disetujui).
- Embedding: tidak dipakai untuk mode statis (schema ≤ 200 tabel).
- Install: transfer wheel + deps via registry PyPI internal (`uv pip install --find-links /opt/wheels ...`), atau image Docker di registry internal.

Tidak ada panggilan keluar yang wajib — library hanya memanggil `llm.base_url` yang kamu tentukan.

## 5. Upgrade & rollback

- Meta store SQLite backward-compatible (DDL idempotent `IF NOT EXISTS`).
- Image Docker di-tag semver; rollback = deploy image lama + restore `/data` dari backup.
- Evaluasi golden set wajib ≥ 90% sebelum upgrade (lihat [eval.md](eval.md)).
