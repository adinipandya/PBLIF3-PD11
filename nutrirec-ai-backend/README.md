# NutriRec AI Backend

Backend API **Sistem Personalisasi Nutrisi Berbasis AI** untuk mesin penjual makanan panas
otomatis (kiosk vending machine).

Aplikasi ini dibangun dengan **FastAPI**, **SQLAlchemy 2.0**, **Alembic**, dan **MySQL**.

---

## 1. Deskripsi Singkat

NutriRec AI menerima kebutuhan nutrisi pengguna (target kalori, prioritas nutrisi, alergi)
melalui Kiosk/Web UI, lalu menghasilkan rekomendasi menu makanan beserta informasi nutrisi.

Alur inti:

1. Pengguna menginput kebutuhan melalui Kiosk/Web UI.
2. Sistem menyaring makanan berdasarkan alergi.
3. Sistem menjalankan content-based recommendation pada makanan yang lolos penyaringan.
4. Sistem memprediksi tingkat kesesuaian via model Machine Learning (proses final).
5. Sistem menggabungkan Content-Based Score dan prediksi ML menjadi **Suitability Score**.
6. Sistem menampilkan maksimal **Top 3** rekomendasi beserta informasi nutrisi dan skor.

---

## 2. Prasyarat

- Python **3.10+** (disarankan 3.12)
- pip / virtual environment
- MySQL/MariaDB (untuk lingkungan utama) — atau SQLite untuk pengembangan/pengujian lokal

---

## 3. Instalasi

```bash
# 1. Clone / masuk ke folder proyek
cd nutrirec-ai-backend

# 2. Buat virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependensi
pip install -r requirements.txt

# 4. Salin file environment contoh
cp .env.example .env

# 5. (Opsional) Generate aplikasi key tidak diperlukan untuk FastAPI,
#    namun pastikan variabel DATABASE_URL sudah diisi.
```

---

## 4. Konfigurasi

File `.env` diperlukan. Contoh konfigurasi (jangan di-commit; jangan tampilkan kredensial):

```env
DATABASE_URL=mysql+pymysql://nutrirec_user:<password>@<host>:3306/nutrirec_db
APP_ENV=development
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:5500
DATASET_VERSION=revisi-PD11-R1
```

Aturan pemetaan:

| Variabel        | Keterangan                                        |
|----------------|---------------------------------------------------|
| `DATABASE_URL` | SQLAlchemy URL (MySQL default; bisa SQLite)       |
| `APP_ENV`      | development / production                         |
| `DEBUG`        | mode debug                                       |
| `ALLOWED_ORIGINS` | CORS allowed origins (dipisah koma)         |
| `DATASET_VERSION` | versi dataset aktif                           |

---

## 5. Migrasi Database (Alembic)

```bash
alembic upgrade head
```

Migrasi yang tersedia:

1. `0001` — Migrasi awal: membuat tabel `target_kalori`, `prioritas_nutrisi`, `alergen`,
   `makanan`, `informasi_gizi`, `kandungan_alergen`.
2. `0002` — Migrasi data referensi: mengisi tabel `target_kalori`, `prioritas_nutrisi`, dan `alergen`.

---

## 6. Impor Dataset

```bash
python scripts/import_dataset.py --file Dataset_makanan_revisi.xlsx
python scripts/import_dataset.py --file Dataset_makanan_revisi.xlsx --dry-run
```

Aturan impor:

- Membaca sheet `Dataset` dari file Excel (openpyxl, `data_only=True`).
- Mempertahankan ID makanan (kolom A) dan angka sumber dari dataset.
- Menggunakan transaksi; error pada salah satu baris menolak seluruh impor (rollback).
- Idempotent: aman dijalankan ulang tanpa duplikasi (update path).
- Menolak data tidak valid (kolom wajib kosong, nilai nutrisi tidak valid, token alergen tidak dikenal).
- Menyimpan status verifikasi alergen dari dataset (default `Belum diverifikasi`).

---

## 7. Menjalankan Aplikasi

```bash
uvicorn app.main:app --reload
```

Atau dengan `python -m uvicorn app.main:app --reload`.

---

## 8. Pengujian

```bash
pytest
```

Test saat ini mencakup: health check, foods API, reference data, validasi schema
personalisasi, dan rekomendasi content-based prototipe (memakai SQLite in-memory).

---

## 9. Endpoint API Saat Ini

### `GET /health`

Status aplikasi.

### `GET /ready`

Kesiapan koneksi database.

### `GET /api/v1/foods`

Daftar seluruh makanan beserta informasi gizi dan alergen.

### `GET /api/v1/foods/{id_makanan}`

Detail satu makanan.

### `GET /api/v1/reference-data`

Data referensi kiosk: target kalori, prioritas nutrisi, dan alergen.

### `POST /api/v1/recommendations/content-based`

Rekomendasi konten (content-based) — **mode prototipe** pada tahap ini.

Request body (menggunakan schema `PermintaanPersonalisasi` yang sudah ada):

```json
{
  "target_kalori_id": 2,
  "prioritas_id": 1,
  "status_alergi": false,
  "alergen_ids": []
}
```

Response:

```json
{
  "mode": "prototipe",
  "versi_aturan": "PD11-R1",
  "jumlah_kandidat": 1,
  "kandidat": [
    {
      "id_makanan": 1,
      "nama_makanan": "Bihun Goreng Sayur",
      "deskripsi_porsi": "1 porsi (200 g)",
      "berat_porsi_gram": null,
      "kalori": "310.00",
      "protein": "8.00",
      "karbohidrat": "55.00",
      "lemak": "7.00",
      "skor_kalori": 0.75,
      "skor_prioritas": 0.5,
      "skor_content_based": 62.5
    }
  ],
  "pesan_kosong": null
}
```

Aturan layanan pada mode prototipe:

- Alergi adalah **filter wajib** (`status_alergi: true` → makanan berpotensi alergi
  diproses).
- Makanan dengan informasi alergen **belum terverifikasi** dikeluarkan apabila
  pengguna memiliki alergi. Daftar relasi alergen **kosong tidak** berarti bebas alergen.
- Kalori dan prioritas nutrisi digunakan sebagai **skor**, bukan filter wajib.
- Rentang kalori: Rendah < 300; Sedang 300–500 (inklusif); Tinggi > 500 kkal per porsi.
- Priority: Protein, Karbohidrat, Lemak, Seimbang (normalisasi min-max proporsi energi;
  Seimbang memakai acuan 0.15 / 0.55 / 0.30).
- Energi makro = 4×protein + 4×karbohidrat + 9×lemak.
- **CB Score (%)** = 100 × (w1 × skor_kalori + w2 × skor_prioritas), dengan bobot
  w1 = 0.5 dan w2 = 0.5 pada mode prototipe (bobot akhir ditentukan lewat eksperimen
  pada tahap pelatihan ML).
- Maksimal 3 kandidat, diurutkan skor menurun, lalu `id_makanan` naik jika seri.
- Jika tidak ada kandidat yang lolos, respons dikembalikan dengan
  `jumlah_kandidat: 0`, `kandidat: []`, dan `pesan_kosong` diisi (bukan error 500).
- Jika ID referensi tidak dikenal, endpoint mengembalikan **HTTP 400** dengan detail
  alasan.

Catatan: pada tahap ini skor content-based **bukan** gabungan skor ML; prediksi ML
masih akan ditambahkan pada tahap berikutnya.

---

## 10. Contoh Request dan Response

### `GET /api/v1/foods`

Request:

```http
GET /api/v1/foods
```

Response:

```json
{
  "total": 0,
  "items": []
}
```

### `GET /api/v1/reference-data`

Request:

```http
GET /api/v1/reference-data
```

Response (struktural):

```json
{
  "target_kalori": [...],
  "prioritas_nutrisi": [...],
  "alergen": [...]
}
```

---

## 11. Catatan Penting

- Daftar alergen kosong **tidak** berarti makanan bebas alergen.
- Alergi adalah filter wajib pada proses rekomendasi.
- Makanan dengan informasi alergen belum terverifikasi wajib dikeluarkan apabila pengguna
  memiliki alergi.
