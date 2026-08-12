# Referensi CLI

Semua perintah: `insightkit <command> [options]`. Opsi umum: `-c/--config` (default `insightkit.yml`), `--semantic <file>`.

## example-config

Menulis template config.

```bash
insightkit example-config -o insightkit.yml
```

## init

Konek ke database, baca schema otomatis, simpan cache schema, siapkan meta store. Bisa sekaligus buat admin.

```bash
insightkit init -c insightkit.yml --semantic semantic.yml --create-admin admin
```

Output sukses: `Connected OK` plus info schema cached dan `db_key`. API key admin tampil sekali, simpan segera.

## ask

Pertanyaan bahasa natural menjadi insight.

```bash
insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
insightkit ask "berapa total revenue bulan lalu?" --json -c insightkit.yml
```

Flag `--json` mengeluarkan output mesin: sql, insight, chart, latency, tokens, model.

## serve

Jalankan REST API dengan streaming SSE.

```bash
insightkit serve -c insightkit.yml --semantic semantic.yml --host 0.0.0.0 --port 8000
```

## refresh

Baca ulang schema database setelah migrasi tabel.

```bash
insightkit refresh -c insightkit.yml
```

## eval

Jalankan eval golden set. Exit code 1 bila skor di bawah threshold. Dipakai sebagai gate di CI.

```bash
insightkit eval -c insightkit.yml -g golden.yml --threshold 0.9
```

## golden

Validasi dan preview file golden set.

```bash
insightkit golden -g golden.yml
```

## semantic

Validasi dan preview file semantic layer.

```bash
insightkit semantic semantic.yml
```

## user

Kelola user API dengan role `admin`, `analyst`, atau `viewer`.

```bash
insightkit user create --username analis --role analyst -c insightkit.yml
insightkit user list -c insightkit.yml
insightkit user delete --username analis -c insightkit.yml
```

API key hanya tampil saat create. Di database yang tersimpan hanya hash SHA-256.
