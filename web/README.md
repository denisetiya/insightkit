# InsightKit Web UI (standalone)

Chat UI single-file untuk tanya-jawab data via InsightKit API. **Tanpa build, tanpa server** — buka langsung di browser.

## Cara pakai

1. Download `index.html` → buka di browser (double-click).
2. Klik **Pengaturan** → isi:
   - **API URL**: `https://insightkit.denisetiya.site` (atau `http://localhost:8002` kalau server lokal)
   - **API Key**: key dari `insightkit user create ...`
   - Klik **Tes Koneksi** → **Simpan**
3. Ketik pertanyaan (atau klik contoh di atas) → jawaban tampil: insight, tabel hasil query, chart (Plotly), dan SQL-nya (klik "Lihat SQL").

## Fitur

- Streaming SSE real-time (plan → sql → result → insight → chart → done)
- Tabel hasil query (raw data, max 50 baris)
- Chart otomatis (Plotly.js dari CDN)
- SQL bisa dilihat per pertanyaan
- Status per jawaban: latency, tokens, row count, cached
- URL + key tersimpan di localStorage (tidak dikirim ke mana pun)
- Light theme, palette blue→cyan

## Catatan

- Butuh koneksi internet untuk Plotly CDN (atau download plotly.min.js dan ganti `<script src>`-nya ke file lokal).
- API harus mengizinkan CORS (sudah default di InsightKit server).
