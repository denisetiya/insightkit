# Panduan Docker

Panduan untuk tim IT menghubungkan InsightKit ke database perusahaan: buat user read-only, setup LLM, sampai produksi. File contoh ada di folder `deploy/`.

## 1. Prasyarat

* Docker dan Docker Compose di server perusahaan
* Akses jaringan dari server ke database (internal network atau VPC)
* Model LLM: self-host (Ollama atau vLLM) atau API key cloud (DeepSeek atau OpenAI)

Prinsip: data dan kredensial database tidak keluar dari infra perusahaan. Yang dikirim ke LLM hanya metadata schema dan hasil query agregat yang sudah PII-mask.

## 2. User database read-only

Buat user khusus dengan hak baca saja. Jangan pakai admin. InsightKit juga memaksa read-only di koneksinya sendiri, jadi ada dua lapis.

PostgreSQL:

```sql
CREATE ROLE insightkit_ro LOGIN PASSWORD 'RAHASIA';
GRANT CONNECT ON DATABASE nama_db TO insightkit_ro;
GRANT USAGE ON SCHEMA public TO insightkit_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO insightkit_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO insightkit_ro;
```

MySQL:

```sql
CREATE USER 'insightkit_ro'@'%' IDENTIFIED BY 'RAHASIA';
GRANT SELECT ON nama_db.* TO 'insightkit_ro'@'%';
FLUSH PRIVILEGES;
```

MongoDB (role read):

```
db.createUser({ user: "insightkit_ro", pwd: "RAHASIA", roles: [{ role: "read", db: "nama_db" }] })
```

OpenSearch: buat role dengan permission read pada index yang boleh diakses.

## 3. Struktur folder

```
company-server/
├── deploy/
│   ├── docker-compose.yml
│   ├── .env
│   └── semantic.yml
├── data/
└── ollama/
```

`deploy/` berisi compose dan contoh env. `data/` adalah volume meta store. `ollama/` adalah volume model bila self-host.

```bash
mkdir -p company-server && cd company-server
cp deploy/.env.example deploy/.env
```

Isi `.env` dari contoh. Jangan commit file `.env` yang sudah terisi secret.

## 4. Konfigurasi LLM

### A. Self-host Ollama

```bash
INSIGHTKIT_LLM__BASE_URL=http://ollama:11434/v1
INSIGHTKIT_LLM__API_KEY=ollama
INSIGHTKIT_LLM__MODEL=qwen2.5-coder
```

Download model sekali ke volume:

```bash
docker compose -f deploy/docker-compose.yml exec ollama ollama pull qwen2.5-coder
```

Tanpa GPU tetap jalan via CPU, tapi lebih lambat. Untuk GPU NVIDIA, aktifkan blok `deploy.resources` di docker-compose.yml.

### B. LLM cloud OpenAI-compatible

```bash
INSIGHTKIT_LLM__BASE_URL=https://api.deepseek.com/v1
INSIGHTKIT_LLM__API_KEY=sk-xxxxxxxx
INSIGHTKIT_LLM__MODEL=deepseek-chat
```

Hapus service `ollama` dari docker-compose.yml bila pakai cloud.

### C. vLLM internal

```bash
INSIGHTKIT_LLM__BASE_URL=http://vllm.internal:8000/v1
INSIGHTKIT_LLM__API_KEY=EMPTY
```

LLM apa pun yang OpenAI-compatible bisa dipakai. Cukup ganti tiga variabel di atas.

## 5. Jalankan dan verifikasi

```bash
# isi .env dulu (DB URL, JWT secret). Generate secret:
#   openssl rand -hex 32
vim deploy/.env

docker compose -f deploy/docker-compose.yml up -d

curl http://localhost:8000/api/v1/health

docker compose -f deploy/docker-compose.yml exec insightkit \
  insightkit user create --username admin --role admin

curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "X-API-Key: ik_xxx" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue bulan lalu?"}'
```

API key admin tampil sekali, simpan segera. InsightKit otomatis connect dan baca schema, tidak ada migrasi manual.

## 6. Semantic layer

Definisi metrik baku supaya jawaban konsisten antar user. Taruh `semantic.yml` di folder deploy:

```yaml
metrics:
  - name: revenue
    definition: "SUM(amount) FILTER (WHERE status = 'paid')"
    description: Total pendapatan dari order yang dibayar
glossary:
  churn: customer yang tidak order dalam 90 hari
```

Volume semantic sudah ada di compose dan terbaca via `INSIGHTKIT_SEMANTIC_PATH`. Setelah ubah file, restart: `docker compose restart insightkit`.

## 7. Manajemen user

```bash
docker compose -f deploy/docker-compose.yml exec insightkit insightkit user create --username analis --role analyst
docker compose -f deploy/docker-compose.yml exec insightkit insightkit user list
```

Role: viewer bisa ask, schema, health. Analyst tambah metrics. Admin tambah audit, refresh schema, dan manajemen user.

## 8. Update dan rollback

```bash
docker compose -f deploy/docker-compose.yml pull insightkit
docker compose -f deploy/docker-compose.yml up -d
```

Meta store SQLite backward-compatible, folder `data/` aman di-upgrade. Rollback artinya pakai tag image lama plus restore `data/` dari backup. Backup rutin `data/meta.db` karena berisi audit log dan users.

## 9. Checklist sebelum produksi

* User database read-only terpisah, bukan admin
* `INSIGHTKIT_API__JWT_SECRET` diganti random
* `INSIGHTKIT_SECURITY__FORBIDDEN_TABLES` diisi tabel sensitif
* Port 8000 hanya untuk jaringan internal atau VPN
* Bila expose publik, taruh di belakang reverse proxy plus VPN atau access policy
* Volume `data/` persistent dan masuk backup
* Pakai LLM self-host untuk data sensitif

## 10. Troubleshooting

| Gejala | Solusi |
|---|---|
| health `database: false` | Cek DSN, user read-only, dan firewall. Tes koneksi manual dari server |
| 401 Invalid credentials | API key salah. Buat ulang via `insightkit user create` |
| Jawaban lama atau error LLM | Cek `docker compose logs insightkit`. Pastikan `ollama pull` selesai dan nama model sesuai |
| connection refused ke ollama | Service ollama belum up |
| Query timeout | Naikkan `INSIGHTKIT_SECURITY__QUERY_TIMEOUT_S` atau periksa indeks database |
| GPU tidak dipakai | Install nvidia-container-toolkit dan aktifkan blok resources |

## 11. Setelah jalan

* Web UI: buka `web/index.html`, isi URL API dan API key
* Evaluasi: buat `golden.yml` dan jalankan `insightkit eval` untuk regression gate
* Monitor: `GET /api/v1/metrics` untuk latency, token, cache hit rate
* Audit: `GET /api/v1/audit` dengan user admin
