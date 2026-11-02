# NutriRec AI Backend

Backend API **Sistem Personalisasi Nutrisi Berbasis AI** untuk mesin penjual makanan panas
otomatis (kiosk vending machine).

Aplikasi ini dibangun dengan **FastAPI**, **SQLAlchemy 2.0**, **Alembic**, dan **MySQL**.

---

## 1. Deskripsi Singkat

NutriRec AI menerima kebutuhan nutrisi pengguna (target kalori, prioritas nutrisi, alergi)
melalui Kiosk/Web UI, lalu menghasilkan rekomendasi menu makanan beserta informasi nutrisi.

Alur aplikasi yang berjalan saat ini:

1. Pengguna menginput kebutuhan melalui Kiosk/Web UI.
2. Sistem menyaring makanan berdasarkan alergi (menu yang status datanya belum terverifikasi tidak diloloskan untuk pengguna dengan alergi).
3. Sistem menghitung skor kecocokan content-based dari target kalori dan prioritas komposisi energi.
4. Sistem menampilkan maksimal **Top 3** rekomendasi beserta informasi nutrisi dan skor.

Eksperimen model Machine Learning berjalan offline dan belum terintegrasi atau dinyatakan siap produksi. Skor aplikasi saat ini bukan gabungan skor content-based dan prediksi ML.

---

## Menjalankan seluruh aplikasi lokal

Gunakan dua terminal. Backend memerlukan database MySQL yang telah berisi tabel, data referensi, dan menu; lihat bagian **12.1. Menjalankan NutriRec secara lokal** untuk urutan setup yang aman. Setelah API hidup dan endpoint `/api/v1/reference-data` berhasil:

1. Di direktori `laravel`, jalankan `composer install` dan `npm ci`.
2. Salin `.env.example` menjadi `.env` hanya jika `.env` belum ada. Buat `APP_KEY` untuk instalasi baru dengan `php artisan key:generate`; atur `VITE_NUTRIREC_API_URL=http://127.0.0.1:8000`.
3. Jalankan `npm run build`, lalu `php artisan serve --host=127.0.0.1 --port=8001`.
4. Buka `http://127.0.0.1:8001/` dan jalankan alur pilih kalori, prioritas, alergi, lalu lihat hasil.

Nilai `.env.example` memakai session/cache file dan queue sync, sehingga tidak perlu tabel session/cache/queue Laravel untuk demo. Jika Anda sudah memiliki `.env`, periksa nilainya sendiri; file tersebut tidak ditimpa. API harus tetap berjalan di port 8000 dan mengizinkan origin web Laravel pada port 8001. Perubahan `VITE_NUTRIREC_API_URL` memerlukan rebuild aset. Uji frontend dengan `node --test tests/integration.test.js`; uji backend dengan `.venv/bin/python -m pytest -q` dari direktori backend.

## Skor rekomendasi prototipe

Skor akhir adalah rata-rata berbobot 50:50 antara kecocokan kalori dan kecocokan prioritas nutrisi. Protein, karbohidrat, atau lemak dibandingkan dengan `min_persen_energi` pada data referensi; karena itu skor konsisten dan tidak berubah hanya akibat menu lain ditambahkan ke katalog. Prioritas Seimbang memakai acuan protein/karbohidrat/lemak pada tabel referensi. Nilai bobot, ambang, dan acuan masih parameter prototipe yang perlu divalidasi dengan pengguna dan ahli gizi; skor bukan probabilitas, saran medis, ataupun jaminan keamanan alergi.

## 2. Prasyarat

- Python **3.10+** (disarankan 3.12)
- pip / virtual environment
- MySQL/MariaDB (untuk lingkungan utama) — atau SQLite untuk pengembangan/pengujian lokal

---

## 3. Instalasi

Buat virtual environment sebelum memasang dependensi. Salin `.env.example` ke `.env` hanya jika `.env` belum tersedia; isi `DATABASE_URL` dengan database pengembangan yang sudah disiapkan. Jangan menjalankan migrasi atau impor terhadap database yang belum diperiksa.

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
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:5500,http://127.0.0.1:8001,http://localhost:8001
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
- Prioritas: Protein, Karbohidrat, Lemak, Seimbang. Tiga prioritas zat gizi memakai
  `min_persen_energi` pada tabel referensi sebagai ambang; Seimbang memakai acuan energi
  yang tersimpan pada tabel prioritas.
- Energi makro = 4×protein + 4×karbohidrat + 9×lemak.
- **CB Score (%)** = 100 × (w1 × skor_kalori + w2 × skor_prioritas), dengan bobot
  prototipe w1 = 0.5 dan w2 = 0.5; bobot masih perlu divalidasi.
- Maksimal 3 kandidat, diurutkan skor menurun, lalu `id_makanan` naik jika seri.
- Jika tidak ada kandidat yang lolos, respons dikembalikan dengan
  `jumlah_kandidat: 0`, `kandidat: []`, dan `pesan_kosong` diisi (bukan error 500).
- Jika ID referensi tidak dikenal, endpoint mengembalikan **HTTP 400** dengan detail
  alasan.

Catatan: skor content-based saat ini **bukan** gabungan skor ML; eksperimen ML offline
belum terintegrasi atau dinyatakan siap produksi.

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

---

## 12. Persiapan Data Survei (Sebelum Pelatihan ML)

Skrip persiapan data survei berada di `scripts/prepare_survey.py`.

Header makanan boleh memakai nomor pertanyaan atau hanya nama; kapitalisasi
dan spasi dinormalisasi, sedangkan header asli dipertahankan untuk audit.
Nama harus ada dalam pemetaan eksplisit dan tidak boleh berulang. Nomor
pertanyaan bukan ID makanan. Rating kosong tetap dicatat.

`siap_ml` selalu `false` pada tahap persiapan: tidak adanya kesalahan bukan
persetujuan pelatihan. `alasan_belum_siap_ml` mencantumkan tahap persiapan dan
ID database yang belum diverifikasi, serta masalah kualitas yang ditemukan.

Jalankan dari direktori backend. Jika sumber berada di direktori induk seperti
pada proyek ini, gunakan `../data/` sebagai awalan seluruh path data. Contoh:

```bash
.venv/bin/python scripts/prepare_survey.py --file '../data/NutriRec-AI (Jawaban).xlsx' --foods '../data/Dataset_makanan_revisi.xlsx' --output-dir ../data/processed --dry-run
```

Hilangkan `--dry-run` untuk ekspor. `lolos_pemeriksaan_dasar` hanya menyatakan
pemeriksaan jawaban dasar, bukan kesiapan ML. `penanda_kiriman` dan
`penanda_penilaian` memisahkan informasi kualitas dari `alasan_tahan`.
Kolom `pemetaan_makanan_terkonfirmasi` menyatakan keputusan pemetaan nama,
bukan bukti kecocokan ID dengan database terpasang. NO Excel digunakan oleh
skrip impor sebagai ID makanan, tetapi isi database belum diverifikasi secara
offline. ID referensi migrasi memakai auto-increment dan juga perlu diperiksa.

### 12.1. File

- Sumber survei: `data/NutriRec-AI (Jawaban).xlsx`
- Sumber dataset: `data/Dataset_makanan_revisi.xlsx`
- Hasil pemeriksaan awal: `data/survey_review/`
- Output persiapan: `data/processed/`

### 12.2. Perintah

```bash
# Dry-run: baca, validasi, tampilkan ringkasan; tidak menulis file
python scripts/prepare_survey.py \
  --file "../data/NutriRec-AI (Jawaban).xlsx" \
  --foods "../data/Dataset_makanan_revisi.xlsx" \
  --output-dir ../data/processed \
  --dry-run

# Export: menulis survey_responses.csv, survey_ratings_long.csv, survey_validation_report.json
python scripts/prepare_survey.py \
  --file "../data/NutriRec-AI (Jawaban).xlsx" \
  --foods "../data/Dataset_makanan_revisi.xlsx" \
  --output-dir ../data/processed
```

### 12.3. Arti Setiap Output

- `survey_responses.csv`: satu baris per kiriman (profil asli + hasil pemetaan + source_row + penanda).
- `survey_ratings_long.csv`: satu baris per penilaian makanan (response_id, target/prioritas/alergen ter-mapping, nama_makanan_survei, id_makanan, rating_asli, rating, status, alasan_tahan/penanda).
- `survey_validation_report.json`: jumlah kiriman/penilaian, status penilaian, distribusi rating, penanda kualitas, grup duplikat, pemetaan belum konfirmasi.

### 12.4. Penanda Kualitas & Keputusan yang Perlu Ditinjau

- `konflik_tanpa_alergi_dengan_pilihan`: tanpa alergi namun mengisi pilihan alergen.
- `konflik_alergi_tanpa_pilihan`: alergi namun tidak ada pilihan alergen. Ini menggantikan nama lama `konflik_alergi_dengan_pilihan`.
- `rating_1_tanpa_alergi`: rating 1 diberikan pada responden tanpa alergi.
- `kemungkinan_duplikat`: jawaban identik selain timestamp.
- `rating_seragam`: seluruh rating seragam.
- `pemetaan_makanan_belum_dikonfirmasi`: pemetaan makanan survei -> dataset belum konfirmasi (saat ini: Capcay).

### 12.5. Perbedaan Makna "Seimbang"

- Pada survei: "Seimbang (tidak ada prioritas khusus)" — pengguna memilih tanpa prioritas khusus.
- Pada backend: prioritas "Seimbang" memakai acuan komposisi 15% protein / 55% karbohidrat / 30% lemak.
- Perbedaan ini sengaja tidak digabung; backend tidak memperlakukan pilihan survei sebagai acuan backend.

### 12.6. Pembagian Data ML

- Pembagian train/validation/test kelak harus memakai `response_id` (bukan timestamp/source_row) untuk mencegah satu kiriman muncul di beberapa kelompok.

## 13. Kandidat eksperimen survei

Jalankan dari direktori backend:

```bash
.venv/bin/python scripts/build_survey_candidate.py \
  --responses ../data/processed/survey_responses.csv \
  --ratings ../data/processed/survey_ratings_long.csv \
  --validation-report ../data/processed/survey_validation_report.json \
  --output-dir ../data/candidate --dry-run
```

Hilangkan `--dry-run` untuk ekspor. `survey_candidate.csv` berisi penilaian
terpilih; `survey_excluded.csv` menyimpan seluruh pengecualian beserta semua
alasan; `survey_candidate_report.json` berisi rekonsiliasi, distribusi, dan hash
ketiga masukan. Kiriman tertahan, penilaian tidak lolos dasar, atau pemetaan
makanan tanpa ID/belum terkonfirmasi dikecualikan. Duplikasi dan rating seragam
tetap dipertahankan sebagai penanda. Hasil adalah **kandidat eksperimen**, bukan
data siap training; ID backend dan makna Seimbang masih harus ditinjau.
Timestamp bukan fitur; `response_id` dan `source_row` hanya metadata audit.
Pembagian kelak harus berdasarkan `response_id`, dan kelompok jawaban identik
perlu dipertimbangkan bersama agar tidak bocor antarkelompok evaluasi.

## 14. Versi survei dan identitas kiriman

Letakkan ekspor baru di `../data/` tanpa menimpa sumber lama. Dari backend,
contoh pemeriksaan snapshot penuh (selalu pilih dataset version baru):

```bash
.venv/bin/python scripts/version_survey.py \
  --file '../data/NutriRec-AI (Jawaban).xlsx' \
  --dataset-version survey-v002 --form-version legacy-v1 \
  --source-namespace nutrirec-survey --mode snapshot \
  --versions-root ../data/survey_versions --registry ../data/survey_registry.json \
  --previous-version survey-v001 --dry-run
```

Hapus `--dry-run` untuk menerbitkan. `snapshot` adalah isi lengkap ekspor,
bukan tambahan ke versi sebelumnya; kiriman yang tidak muncul dilaporkan,
bukan dihapus. `incremental` hanya berisi tambahan dan membutuhkan versi
sebelumnya; registry versi mencatat gabungan UID dan sumber sebelumnya, sedangkan
`source.xlsx` dan sidecar menyimpan kiriman dari ekspor incremental saja.
Gunakan arsip versi sebelumnya untuk merekonstruksi data gabungan.

Sumber saat ini tidak mempunyai ID kiriman asli. Timestamp dan fingerprint
jawaban kanonis hanya bukti pencocokan satu-ke-satu, bukan identitas orang.
UID, response_id, source_row, dan timestamp bukan fitur ML. Timestamp sama
dengan jawaban berubah atau kecocokan jamak ditahan dan dicetak untuk review.
Keputusan JSON lewat `--decisions` berbentuk
`{"2": {"submission_uid": "UID-atau-baru", "alasan": "hasil review"}}`;
gunakan `baru` untuk kiriman baru. Keputusan dan hash-nya dicatat pada versi.
Perubahan form_version tidak digabung dengan versi sebelumnya secara otomatis.

Setiap versi disimpan di `../data/survey_versions/<dataset_version>/`; registry
lokal di `../data/survey_registry.json`. Ekspor processed/candidate lama tidak
diubah. Penerbitan membuat direktori lengkap dahulu, kemudian mengganti registry
secara atomik. Jika proses terputus di antaranya, direktori versi dapat tertinggal
tanpa entri registry; hentikan impor dan tinjau/rekonsiliasi secara manual,
jangan menghapus atau menimpa arsip secara otomatis.

## 15. Memproses snapshot yang sudah diterbitkan

Dari backend, periksa terlebih dahulu tanpa menulis berkas:

```bash
.venv/bin/python scripts/process_survey_version.py \
  --version-dir ../data/survey_versions/survey-v001 \
  --foods ../data/Dataset_makanan_revisi.xlsx --dry-run
```

Untuk ekspor, hilangkan `--dry-run` dan tambahkan `--run-id run-001`
(pilih ID baru untuk setiap run). Hasil tersimpan di
`survey-v001/processing/<run-id>/`, terpisah dari arsip dan hasil lama.
Hanya snapshot didukung; incremental ditolak sampai rekonstruksi lengkap
tersedia. Hasil tetap kandidat eksperimen, bukan data siap training.

`submission_uid` mengidentifikasi kiriman lintas versi, bukan orang. UID,
`dataset_version`, `form_version`, `source_namespace`, `response_id`,
`source_row`, dan timestamp adalah metadata audit, bukan fitur ML. Manifest
pemrosesan mencatat hash masukan, aturan dan keluaran agar hasil dapat diaudit.

## 16. Eksperimen ML awal offline

Instal dependensi `requirements.txt`, termasuk scikit-learn 1.5.2. Dari backend:

```bash
.venv/bin/python scripts/run_ml_experiment.py \
  --features-dir ../data/experiments/survey-v001/features-v001 \
  --output-dir ../data/experiments/survey-v001/experiment-001 \
  --seed 42 --dry-run
```

Hilangkan `--dry-run` untuk mengevaluasi; keluaran yang sudah ada tidak ditimpa.
Protokolnya GroupKFold lima fold tanpa tuning atau holdout final. Dummy, Decision
Tree, Random Forest, dan KNN menggunakan fold sama serta preprocessing yang
di-fit hanya pada train tiap fold. Metrik mencakup accuracy, macro-F1 empat kelas,
MAE, per kelas dan confusion matrix. Rata-rata/std fold bersifat deskriptif.
Kelas langka mungkin tidak tersedia di beberapa fold. Probabilitas belum
terkalibrasi; eksperimen ini bukan validasi produksi atau jaminan keamanan alergi.

### Analisis kesalahan OOF

```bash
.venv/bin/python scripts/analyze_ml_errors.py \
  --experiment-dir ../data/experiments/survey-v001/experiment-001 \
  --features-dir ../data/experiments/survey-v001/features-v001 \
  --output-dir ../data/experiments/survey-v001/error-analysis-002 --dry-run
```

Hilangkan `--dry-run` untuk menulis analisis ke direktori baru. Analisis tidak
melatih ulang model; kesalahan per kelas, profil, makanan, dan fold bersifat
deskriptif, khususnya untuk subkelompok kecil dan kelas langka.
