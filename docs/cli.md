# CLI Reference

Semua perintah: `insightkit <command> [options]`. Umum: `-c/--config` (default `insightkit.yml`), `--semantic <file>`.

## `example-config`

Menulis template config.

```bash
insightkit example-config -o insightkit.yml
```

## `init`

Konek DB → auto schema extraction → cache schema → siapkan meta store. Opsional buat admin.

```bash
insightkit init -c insightkit.yml --semantic semantic.yml --create-admin admin
# → Admin user 'admin' created. API key (show once): ik_...
```

Verifikasi: `Connected OK — schema cached (db_key=...)`.

## `ask`

Pertanyaan bahasa natural → insight.

```bash
insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
insightkit ask "berapa total revenue bulan lalu?" --json   # output JSON (sql, insight, chart, latency, tokens, model)
```

## `serve`

Jalankan REST API (FastAPI + SSE streaming).

```bash
insightkit serve -c insightkit.yml --semantic semantic.yml --host 0.0.0.0 --port 8000
```

## `refresh`

Re-introspect schema (setelah migrasi tabel).

```bash
insightkit refresh -c insightkit.yml
```

## `eval`

Jalankan golden-set evaluation. **Exit code 1 jika skor < threshold** (CI gate).

```bash
insightkit eval -c insightkit.yml -g golden.yml --threshold 0.9
# → Score: 100% (3/3)
```

## `golden`

Validasi & preview file golden set.

```bash
insightkit golden -g golden.yml
```

## `semantic`

Validasi & preview file semantic layer.

```bash
insightkit semantic semantic.yml
```

## `user`

Manajemen user API (RBAC: `admin` / `analyst` / `viewer`).

```bash
insightkit user create --username analis --role analyst -c insightkit.yml   # API key ditampilkan SEKALI
insightkit user list -c insightkit.yml
insightkit user delete --username analis -c insightkit.yml
```

> API key hanya tampil saat create — simpan segera. Tersimpan sebagai hash SHA-256.
