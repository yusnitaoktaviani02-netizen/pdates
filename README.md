# Chatbot RAG Publikasi Data Masjid Syuhada

Aplikasi Streamlit untuk publikasi dan penelusuran workbook metadata dokumentasi Masjid Syuhada. Mendukung pencarian semantik berbasis embeddings OpenAI, jawaban generatif dengan konteks hasil retrieval, dan tampilan sumber untuk keterlacakan. Tanpa API key, aplikasi tetap menyediakan pencarian kata kunci (retrieval-only).

## Isi folder

- `app.py` — aplikasi Streamlit.
- `Metadata_DCMA_RAG_Masjid_Syuhada_101.xlsx` — workbook sumber yang disediakan.
- `requirements.txt` — dependensi.
- `.streamlit/secrets.toml.example` — contoh konfigurasi API key.

## Deploy ke Streamlit Community Cloud

1. Buat repository GitHub baru dan unggah seluruh isi folder ini.
2. Buka https://share.streamlit.io/ dan masuk dengan akun GitHub.
3. Pilih **Create app**, pilih repository, branch, dan file utama `app.py`.
4. Pada **Advanced settings / Secrets**, tambahkan:

   ```toml
   OPENAI_API_KEY = "sk-..."
   ```

5. Deploy. Saat pertama kali digunakan, aplikasi membuat indeks embeddings dari rekod di workbook. Proses ini memakai OpenAI API dan dapat menimbulkan biaya API.
6. Jangan pernah menaruh API key langsung di `app.py`, GitHub, atau file yang dipublikasikan.

> “streamlit.ai” yang umum dimaksud untuk hosting aplikasi adalah Streamlit Community Cloud di `share.streamlit.io`.

## Menjalankan lokal

Disarankan Python 3.10–3.12.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Atur API key sebelum menjalankan agar jawaban generatif aktif:

**Windows PowerShell**
```powershell
$env:OPENAI_API_KEY="sk-..."
streamlit run app.py
```

**macOS/Linux**
```bash
export OPENAI_API_KEY="sk-..."
streamlit run app.py
```

## Cara kerja RAG

1. Aplikasi membaca sheet dokumen sumber, elemen arsitektur, inventarisasi kerusakan, panduan pelestarian, dan chunk RAG.
2. Isi setiap rekod diubah menjadi teks berlabel agar metadata dan informasi keterlacakan ikut terbawa.
3. OpenAI `text-embedding-3-small` mengubah rekod menjadi embedding dan menyimpannya sementara melalui cache Streamlit.
4. Pertanyaan pengguna di-embed; pencarian cosine similarity mengambil rekod relevan.
5. `gpt-4o-mini` menyusun jawaban dari konteks yang diambil, dengan instruksi agar tidak mengarang informasi dan menyebut keterbatasan data.
6. Aplikasi menampilkan judul, ID rekod, dokumen, halaman, cuplikan, dan tautan sumber bila tersedia.

## Sebelum dibuka untuk publik

- Pastikan pemilik/penerbit mengizinkan publikasi workbook dan dokumen yang ditautkan.
- Tinjau apakah ada data internal atau informasi yang tidak boleh dipublikasikan. Workbook memiliki nilai `access_level` pada chunk RAG; aplikasi ini saat ini memuat data dari workbook termasuk rekod berlabel internal. **Jangan deploy publik sebelum Anda memastikan semua rekod memang layak dibuka untuk umum.**
- Validasi URL sumber, nomor halaman, ejaan, kode elemen, dan status verifikasi. Data yang menyebut “sekitar” atau “perlu verifikasi” tetap akan ditampilkan sebagai demikian.
- Aplikasi tidak menafsirkan ulang dugaan penyebab kerusakan menjadi fakta, dan bukan rekomendasi teknis pengganti asesmen ahli.

## Catatan teknis

- Embedding dan jawaban generatif memerlukan API key OpenAI yang aktif serta akses jaringan dari aplikasi.
- Indeks dibangun dari data workbook dan disimpan dalam cache runtime, bukan database permanen. Cache dapat dibangun ulang setelah restart.
- Untuk volume besar, gunakan vector database persisten dan tambahkan autentikasi, rate limiting, monitoring, serta pipeline pembaruan data.
