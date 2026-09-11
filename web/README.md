# InsightKit Web Workspace

Antarmuka web mandiri (single-file HTML) untuk eksplorasi dan tanya jawab analitik data via InsightKit API. Tanpa proses build, cukup buka langsung di peramban.

## Cara penggunaan

1. Buka file `index.html` langsung di peramban peramban Anda.
2. Klik tombol **Koneksi** di pojok kanan atas:
   - Pilih mode **Data Demo Interaktif** untuk mencoba seketika tanpa server lokal, atau
   - Pilih mode **Server InsightKit API**, lalu masukkan alamat API URL (default `http://localhost:8000`) dan API Key Anda.
   - Klik **Uji Koneksi**, lalu tekan **Simpan**.
3. Ketik pertanyaan analitik pada kolom input di bawah atau pilih dari tombol contoh yang tersedia.
4. Lembar inspektur di sebelah kanan akan menampilkan ringkasan fakta, grafik analitik Plotly, cuplikan tabel data, serta instruksi SQL read-only yang dieksekusi.

## Fitur utama

* Aliran respons real-time (SSE streaming) dengan pelacakan status bertahap.
* Mode demo interaktif bawaan untuk simulasi tanpa memerlukan server Python aktif.
* Penyesuaian tema warna Gelap dan Terang dengan rasio kontras tinggi (WCAG AA).
* Tampilan responsif untuk desktop dan perangkat seluler dengan tab navigasi adaptif.
* Tabel data tabular dilengkapi fitur unduh berkas CSV.
* Aksesibilitas keyboard penuh (navigasi Tab, Enter, dan tombol Escape untuk dialog).
