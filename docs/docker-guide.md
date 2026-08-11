# 🐳 Panduan Docker — Hubungkan InsightKit ke Database Perusahaan

Panduan langkah-demi-langkah untuk tim IT/DevOps perusahaan: dari membuat user DB read-only, setup LLM, sampai produksi. Semua file contoh ada di folder `deploy/`.

---

## 1. Prasyarat

- Docker + Docker Compose di server perusahaan (VM atau K8s node)
- Akses jaringan dari server ke database (biasanya internal network / VPC)
- Model LLM: self-host (Ollama/vLLM) **atau** API key cloud (DeepSeek/OpenAI)

> **Prinsip:** data & kredensial DB **tidak pernah keluar** infrastruktur perusahaan.
> Yang keluar ke LLM hanya: metadata schema + hasil query agregat (sudah PII-masked).

---

## 2. Siapkan user database READ-ONLY (wajib — jangan pakai admin!)

Buat user khusus dengan hak baca saja. InsightKit juga memaksa read-only di koneksinya sendiri — ini lapisan ganda.

**PostgreSQL:**
```sql
CREATE ROLE insightkit_ro LOGIN PASSWORD 'RAHASIA';
GRANT CONNECT ON DATABASE nama_db TO insightkit_ro;
GRANT USAGE ON SCHEMA public TO insightkit_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO insightkit_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO insightkit_ro;  -- tabel baru otomatis
```

**MySQL:**
```sql
CREATE USER 'insightkit_ro'@'%' IDENTIFIED BY 'RAHASIA';
GRANT SELECT ON nama_db.* TO 'insightkit_ro'@'%';
FLUSH PRIVILEGES;
```

**MongoDB** (baca semua collection):
```
db.createUser({ user: "insightkit_ro", pwd: "RAHASIA", roles: [{ role: "read", db: "nama_db" }] })
```

**OpenSearch** — buat user/role dengan permission `read` pada index yang boleh diakses (Security → Roles → `search` + `indices:data/read/*`).

---

## 3. Struktur folder

```
company-server/
├── deploy/
│   ├── docker-compose.yml   # sudah disediakan
│   ├── .env                 # isi dari .env.example (JANGAN commit)
│   └── semantic.yml         # opsional — definisi metrik bisnis
├── data/                    # volume: audit, cache, users, schema (dibuat otomatis)
└── ollama/                  # volume model LLM (kalau self-host)
```

```bash
mkdir -p company-server && cd company-server
# ambil file dari repo:
#   deploy/docker-compose.yml, deploy/.env.example
cp deploy/.env.example deploy/.env
```

---

## 4. Konfigurasi LLM — 3 pilihan

### A. Self-host dengan Ollama (paling privat — sudah ada di docker-compose)
```bash
# .env:
INSIGHTKIT_LLM__BASE_URL=http://ollama:11434/v1
INSIGHTKIT_LLM__API_KEY=ollama
INSIGHTKIT_LLM__MODEL=qwen2.5-coder

# jalankan sekali untuk download model ke volume (sekitar 4-6 GB):
docker compose -f deploy/docker-compose.yml exec ollama ollama pull qwen2.5-coder
```
Tanpa GPU tetap jalan (CPU), tapi lebih lambat. Untuk GPU NVIDIA: buka komentar blok `deploy.resources` di docker-compose.yml.

### B. LLM cloud OpenAI-compatible (DeepSeek/OpenAI/Gemini)
```bash
# .env:
INSIGHTKIT_LLM__BASE_URL=https://api.deepseek.com/v1
INSIGHTKIT_LLM__API_KEY=sk-xxxxxxxx
INSIGHTKIT_LLM__MODEL=deepseek-chat
```
Hapus service `ollama` dari docker-compose.yml (dan `depends_on`).

### C. vLLM internal perusahaan (GPU sendiri, skala besar)
```bash
INSIGHTKIT_LLM__BASE_URL=http://vllm.internal:8000/v1
INSIGHTKIT_LLM__API_KEY=EMPTY
```

> LLM apa pun yang OpenAI-compatible bisa dipakai — cukup ganti 3 variabel.

---

## 5. Jalankan & verifikasi

```bash
# isi .env dulu (DB URL, JWT secret) — generate secret:
#   openssl rand -hex 32
vim deploy/.env

# start
docker compose -f deploy/docker-compose.yml up -d

# cek health
curl http://localhost:8000/api/v1/health
# → {"status":"ok","database":true,"model":"qwen2.5-coder",...}

# buat admin pertama (API key tampil SEKALI — simpan!)
docker compose -f deploy/docker-compose.yml exec insightkit \
  insightkit user create --username admin --role admin

# tes tanya-jawab
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H "X-API-Key: ik_xxx" -H "Content-Type: application/json" \
  -d '{"question":"berapa total revenue bulan lalu?"}'
```

InsightKit otomatis: connect → **auto schema extraction** → siap dipakai. Tidak ada langkah migrasi manual.

---

## 6. Semantic layer (opsional tapi sangat disarankan)

Definisi metrik baku supaya jawaban konsisten antar user. Taruh `semantic.yml` di folder deploy:

```yaml
metrics:
  - name: revenue
    definition: "SUM(amount) FILTER (WHERE status = 'paid')"
    description: Total pendapatan dari order yang dibayar
glossary:
  churn: customer yang tidak order dalam 90 hari
```

Volume `./semantic.yml:/config/semantic.yml:ro` sudah ada di compose — file ini langsung terbaca (via `INSIGHTKIT_SEMANTIC_PATH`). Ubah → `docker compose restart insightkit`.

---

## 7. Manajemen user & RBAC

```bash
docker compose -f deploy/docker-compose.yml exec insightkit insightkit user create --username analis --role analyst
docker compose -f deploy/docker-compose.yml exec insightkit insightkit user list
```

| Role | Akses |
|------|-------|
| `viewer` | ask, schema, health |
| `analyst` | + metrics |
| `admin` | + audit, refresh schema, manage user |

---

## 8. Update & rollback

```bash
docker compose -f deploy/docker-compose.yml pull insightkit
docker compose -f deploy/docker-compose.yml up -d
```
- Meta store SQLite backward-compatible (DDL idempotent) — `data/` aman di-upgrade.
- Rollback: tag image lama (`ghcr.io/denisetiya/insightkit:0.1.0`) + restore `data/` dari backup.
- **Backup rutin:** `data/meta.db` berisi audit log + users — taruh di backup policy perusahaan.

---

## 9. Security checklist sebelum produksi

- [ ] User DB **read-only** terpisah (bukan admin)
- [ ] `INSIGHTKIT_API__JWT_SECRET` diganti (random 64 hex)
- [ ] `INSIGHTKIT_SECURITY__FORBIDDEN_TABLES` diisi tabel sensitif (salaries, dll)
- [ ] Firewall: port 8000 hanya untuk jaringan internal / VPN (bukan publik)
- [ ] Kalau expose publik: wajib di belakang reverse proxy + mTLS/VPN, atau Cloudflare Tunnel + Access policy
- [ ] Volume `data/` di-mount persistent + masuk backup
- [ ] LLM self-host kalau data sangat sensitif (bank/pemerintah) — mode air-gapped

---

## 10. Troubleshooting

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `/api/v1/health` → `"database": false` | DSN salah / user RO belum dibuat / firewall blok. Tes koneksi manual dari server |
| `401 Invalid credentials` | API key salah — bikin ulang: `insightkit user create` |
| Jawaban lama / error LLM | Cek `docker compose logs insightkit`; pastikan `ollama pull` selesai & model name sesuai |
| `connection refused` ke `http://ollama:11434` | Service ollama belum up / `depends_on` terhapus |
| Kueri timeout | Naikkan `INSIGHTKIT_SECURITY__QUERY_TIMEOUT_S`, atau periksa indeks DB |
| GPU tidak dipakai | Install nvidia-container-toolkit + buka blok `deploy.resources` |

---

## 11. Setelah jalan

- **Web UI**: buka `http://<server>:8000` (atau gunakan `web/chat.html` lokal)
- **Evaluasi**: buat `golden.yml` + jalankan `insightkit eval` di container untuk regression gate
- **Monitor**: `GET /api/v1/metrics` (latency p50/p95, token, cache hit rate)
- **Audit**: `GET /api/v1/audit` (admin) — semua pertanyaan tercatat
