# Keamanan

Model pertahanan berlapis — setiap lapis independen, satu gagal lapis berikutnya tetap menahan.

## 1. Koneksi read-only (lapis DB)

- **SQLite**: file URI `mode=ro` — menulis gagal di level driver.
- **PostgreSQL**: `SET LOCAL default_transaction_read_only=on` per koneksi.
- **MySQL**: `SET SESSION TRANSACTION READ ONLY`.
- Praktik: perusahaan menyediakan user DB terpisah dengan `GRANT SELECT` saja.

## 2. Guardrail query (lapis aplikasi)

`security/guard.py` — dijalankan **sebelum eksekusi**, di luar kendali LLM:

- Statement selain `SELECT/WITH/EXPLAIN/SHOW/PRAGMA` → tolak (`GuardError`).
- Keyword berbahaya (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `CREATE`, `ATTACH`, `VACUUM`, `MERGE`) → tolak.
- Multi-statement (`;`) → tolak.
- `row_limit` dipaksa (`LIMIT` di-clamp / ditambahkan).
- Tabel blacklist (`security.forbidden_tables`) → tolak.
- Query timeout: `asyncio.wait_for` + statement timeout server-side (PG `statement_timeout`, MySQL `max_execution_time`).

## 3. PII masking

`mask_pii()` — regex untuk email, nomor telepon (ID/international), NIK 16 digit, nomor kartu 13-19 digit → `[REDACTED]`. Diterapkan pada:

- hasil query **sebelum** dikirim ke LLM untuk interpretasi,
- SQL & ringkasan yang masuk audit log.

## 4. RBAC

| Role | Akses |
|------|-------|
| `viewer` | ask, schema, health |
| `analyst` | + metrics |
| `admin` | + audit, schema refresh, manajemen user |

Default deny. API key disimpan sebagai SHA-256 hash; JWT HS256 expiry `jwt_expire_min`.

## 5. Audit trail (compliance)

- Setiap `ask` tercatat: user, role, ts, question, SQL (masked), ringkasan hasil, latency, token, model, status.
- **Append-only** — tidak ada method update/delete pada `AuditLog`; akses baca hanya via `admin`.

## 6. Operasional

- Secret tidak pernah masuk log (config tidak di-log).
- Rate limit per-user.
- Image Docker non-root + healthcheck.
- LLM output selalu divalidasi (JSON mode + parse ketat + self-correct) — LLM tidak punya akses langsung ke DB, hanya lewat pipeline yang dijaga.

## Threat model ringkas

| Serangan | Pertahanan |
|----------|-----------|
| Prompt injection ("lupakan instruksi, DELETE...") | Guardrail keyword + read-only DB role |
| Exfiltrasi data via LLM | PII mask + blacklist tabel + audit |
| Query berat (bomb) | row-limit + timeout 2 lapis |
| API abuse | API key + JWT + rate limit |
| Insider jahat | RBAC + audit append-only |
