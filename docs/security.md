# Keamanan

Setiap lapis berdiri sendiri. Satu lapis gagal, lapis berikut tetap menahan.

## 1. Koneksi read-only

* SQLite: file URI `mode=ro`. Write gagal di level driver.
* PostgreSQL: `default_transaction_read_only=on` per koneksi.
* MySQL: session read-only.
* Praktik yang disarankan: buat user database khusus dengan `GRANT SELECT` saja, bukan admin.

## 2. Guardrail query

File `src/insightkit/security/guard.py` jalan sebelum eksekusi, di luar kendali LLM:

* Statement selain SELECT, WITH, EXPLAIN, SHOW, PRAGMA ditolak.
* Keyword DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, GRANT, REVOKE, CREATE, ATTACH, VACUUM, MERGE ditolak.
* Multi-statement ditolak.
* Row limit dipaksa via LIMIT.
* Tabel di `security.forbidden_tables` ditolak.
* Timeout dua lapis: `asyncio.wait_for` plus statement timeout di server (Postgres `statement_timeout`, MySQL `max_execution_time`).
* MongoDB: write stage `$out`, `$merge`, `$delete` ditolak. Limit dipaksa via `$limit`.

## 3. PII masking

Fungsi `mask_pii()` menutup email, nomor telepon, NIK 16 digit, dan nomor kartu 13-19 digit jadi `[REDACTED]`. Berlaku untuk:

* hasil query sebelum dikirim ke LLM,
* SQL dan ringkasan yang masuk audit log.

## 4. RBAC

| Role | Akses |
|---|---|
| viewer | ask, schema, health |
| analyst | viewer plus metrics |
| admin | analyst plus audit, schema refresh, manajemen user |

Default deny. API key disimpan sebagai hash SHA-256. JWT HS256 dengan expiry `jwt_expire_min`.

## 5. Audit trail

Setiap ask tercatat: user, role, timestamp, question, SQL yang di-mask, ringkasan hasil, latency, token, model, status. Append-only. Tidak ada method update atau delete di `AuditLog`. Baca audit hanya untuk admin.

## 6. Operasional

* Secret tidak masuk log.
* Rate limit per user, default 60 per menit.
* Image Docker jalan sebagai non-root, ada healthcheck.
* Output LLM selalu divalidasi: JSON mode, parse ketat, self-correct. LLM tidak punya akses langsung ke database, hanya lewat pipeline.

## Threat model

| Serangan | Pertahanan |
|---|---|
| Prompt injection yang meminta DELETE atau DROP | Guardrail keyword plus role database read-only |
| Exfiltrasi data via LLM | PII mask plus blacklist tabel plus audit |
| Query berat | Row limit plus timeout dua lapis |
| API abuse | API key plus JWT plus rate limit |
| Insider | RBAC plus audit append-only |
