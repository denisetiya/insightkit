# Evaluasi & Golden Set

## Konsep

**Golden set** = kumpulan kasus (pertanyaan → SQL yang diharapkan / kata kunci hasil) yang diverifikasi manual. Dipakai sebagai **regression gate**: skor akurasi wajib ≥ threshold sebelum rilis/upgrade.

## Format (`golden.yml`)

```yaml
- question: "berapa total revenue?"
  sql_expected: "SELECT SUM(amount) FROM orders WHERE status = 'paid'"
- question: "berapa jumlah orders?"
  sql_expected: "SELECT COUNT(*) FROM orders"
- question: "berapa order yang pending?"
  result_keywords: ["2"]        # cek insight mengandung kata ini
```

Perbandingan **berbasis hasil eksekusi** (bukan teks SQL): query yang dihasilkan & SQL harapan dieksekusi, result set dibandingkan (urutan baris diabaikan, angka dinormalisasi). Robust terhadap variasi alias/format LLM. Jika SQL harapan tidak bisa dieksekusi → fallback perbandingan teks ternormalisasi.

## Menjalankan

```bash
insightkit eval -c insightkit.yml -g golden.yml --threshold 0.9
# Score: 100% (3/3)   → exit 0
# Score: 67% (2/3)    → exit 1 (gate gagal)
```

## CI integration

```yaml
- name: Golden set
  run: |
    uv run insightkit eval -c insightkit.yml -g tests/golden/orders.yml || exit 1
```

> CI tanpa LLM: gunakan golden dengan `sql_expected` + jalankan dengan mock, atau pisahkan ke job dengan LLM key rahasia.

## Praktik terbaik

- 10-50 kasus per skema inti; tambah tiap kali ketemu bug SQL.
- Kasus yang gagal → perbaiki prompt/semantic layer → re-run, bukan hapus kasus.
- Query yang berhasil & disetujui → tambahkan ke few-shot store (`insightkit user` → internal; otomatis dipakai sebagai contoh di prompt).
