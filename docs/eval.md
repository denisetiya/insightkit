# Evaluasi dan Golden Set

## Konsep

Golden set adalah kumpulan kasus pertanyaan ke SQL yang sudah diverifikasi manual. Dipakai sebagai regression gate. Skor akurasi wajib mencapai threshold sebelum rilis atau upgrade.

## Format golden.yml

```yaml
- question: "berapa total revenue?"
  sql_expected: "SELECT SUM(amount) FROM orders WHERE status = 'paid'"
- question: "berapa jumlah orders?"
  sql_expected: "SELECT COUNT(*) FROM orders"
- question: "berapa order yang pending?"
  result_keywords: ["2"]
```

Perbandingan berbasis hasil eksekusi, bukan teks SQL. Query hasil model dan SQL harapan dieksekusi, lalu result set dibandingkan. Urutan baris diabaikan, angka dinormalisasi. Cara ini tahan terhadap variasi alias dan format LLM. Bila SQL harapan tidak bisa dieksekusi, dipakai fallback perbandingan teks yang dinormalisasi.

## Menjalankan

```bash
insightkit eval -c insightkit.yml -g golden.yml --threshold 0.9
# Score: 100% (3/3), exit 0
# Score: 67% (2/3), exit 1, gate gagal
```

## Integrasi CI

```yaml
- name: Golden set
  run: |
    uv run insightkit eval -c insightkit.yml -g tests/golden/orders.yml || exit 1
```

CI tanpa LLM: pakai golden dengan `sql_expected` plus mock, atau pisahkan ke job dengan LLM key rahasia.

## Praktik yang disarankan

* 10 sampai 50 kasus per skema inti. Tambah kasus baru setiap kali menemukan bug SQL.
* Kasus gagal berarti perbaiki prompt atau semantic layer, lalu re-run. Jangan hapus kasus.
* Query yang berhasil dan disetujui masukkan ke few-shot store supaya dipakai sebagai contoh di prompt.
