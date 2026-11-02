# Analisis kesalahan OOF

## A. Teramati

Sumber experiment-001; 4200 prediksi pada 1050 penilaian per model. Aucun training ulang.

| Model | N | UID | Kelompok | Accuracy | Macro-F1 | MAE | Benar | Salah 1 | Salah ≥2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Decision Tree | 1050 | 56 | 54 | 0.4457 | 0.1978 | 0.6257 | 468 | 510 | 72 |
| Dummy | 1050 | 56 | 54 | 0.4933 | 0.1652 | 0.5133 | 518 | 525 | 7 |
| KNN | 1050 | 56 | 54 | 0.3943 | 0.2452 | 0.7200 | 414 | 519 | 117 |
| Random Forest | 1050 | 56 | 54 | 0.4010 | 0.1682 | 0.6581 | 421 | 570 | 59 |

### F1 dan support per kelas

| Model | Kelas | F1 | Support |
|---|---:|---:|---:|
| Decision Tree | 1 | 0.0000 | 7 |
| Decision Tree | 2 | 0.0183 | 181 |
| Decision Tree | 3 | 0.6254 | 518 |
| Decision Tree | 4 | 0.1474 | 344 |
| Dummy | 1 | 0.0000 | 7 |
| Dummy | 2 | 0.0000 | 181 |
| Dummy | 3 | 0.6607 | 518 |
| Dummy | 4 | 0.0000 | 344 |
| KNN | 1 | 0.0000 | 7 |
| KNN | 2 | 0.1596 | 181 |
| KNN | 3 | 0.5345 | 518 |
| KNN | 4 | 0.2867 | 344 |
| Random Forest | 1 | 0.0000 | 7 |
| Random Forest | 2 | 0.0000 | 181 |
| Random Forest | 3 | 0.5798 | 518 |
| Random Forest | 4 | 0.0931 | 344 |

Macro-F1 memakai empat label dan zero_division=0; kelas dengan support nol tidak dapat dievaluasi. Normalisasi baris dengan support nol adalah null.

### Confusion matrix: baris aktual, kolom prediksi (1–4)

**Decision Tree**

| Aktual | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 4 | 3 |
| 2 | 0 | 2 | 139 | 40 |
| 3 | 0 | 11 | 429 | 78 |
| 4 | 0 | 25 | 282 | 37 |

**Dummy**

| Aktual | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 7 | 0 |
| 2 | 0 | 0 | 181 | 0 |
| 3 | 0 | 0 | 518 | 0 |
| 4 | 0 | 0 | 344 | 0 |

**KNN**

| Aktual | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|
| 1 | 0 | 2 | 3 | 2 |
| 2 | 1 | 30 | 110 | 40 |
| 3 | 0 | 92 | 298 | 128 |
| 4 | 1 | 71 | 186 | 86 |

**Random Forest**

| Aktual | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 4 | 3 |
| 2 | 0 | 0 | 135 | 46 |
| 3 | 0 | 3 | 396 | 119 |
| 4 | 0 | 6 | 313 | 25 |

### Perbandingan berpasangan terhadap Dummy

| Model | Keduanya benar | Hanya model | Hanya Dummy | Keduanya salah | Δ accuracy | Δ MAE |
|---|---:|---:|---:|---:|---:|---:|
| Decision Tree | 429 | 39 | 89 | 493 | -0.0476 | 0.1124 |
| KNN | 298 | 116 | 220 | 416 | -0.0990 | 0.2067 |
| Random Forest | 396 | 25 | 122 | 507 | -0.0924 | 0.1448 |

### Subkelompok: selisih accuracy terbesar terhadap Dummy

| Model | Variabel | Nilai | Penilaian | UID | Kelompok | Δ accuracy | Dukungan terbatas |
|---|---|---|---:|---:|---:|---:|---|
| Random Forest | target_kalori | Rendah | 94 | 5 | 5 | -0.2979 | False |
| Decision Tree | prioritas | Lemak | 19 | 1 | 1 | 0.2632 | True |
| KNN | prioritas | Lemak | 19 | 1 | 1 | 0.2632 | True |
| Decision Tree | target_kalori | Rendah | 94 | 5 | 5 | -0.2234 | False |
| KNN | nama_makanan_dataset | Bakso Sapi Kuah (Tanpa Mie) | 55 | 55 | 53 | -0.2000 | False |
| Random Forest | prioritas | Karbohidrat | 76 | 4 | 4 | -0.1842 | True |
| Random Forest | nama_makanan_dataset | Rawon Daging Sapi | 56 | 56 | 54 | -0.1786 | False |
| KNN | target_kalori | Rendah | 94 | 5 | 5 | -0.1702 | False |
| KNN | nama_makanan_dataset | Nasi Putih (Dijual Terpisah) | 54 | 54 | 52 | -0.1667 | False |
| KNN | nama_makanan_dataset | Dendeng Balado Basah | 55 | 55 | 53 | -0.1636 | False |

Kurang dari 5 kelompok ditandai dukungan sangat terbatas; ambang ini deskriptif, bukan jaminan kecukupan statistik.

### Rating 1 dan contoh kesalahan besar

Contoh maksimal 10 per model, diurutkan error absolut menurun, UID lalu NO makanan numerik.

**Decision Tree:** 7 penilaian, 2 UID, 2 kelompok, fold ['5']; train tidak memiliki kelas 1: 7, benar 0.
- R062 / NO 5: aktual 1, prediksi 4, error 3.
- R062 / NO 7: aktual 1, prediksi 4, error 3.
- R062 / NO 12: aktual 1, prediksi 4, error 3.
- R019 / NO 7: aktual 2, prediksi 4, error 2.
- R055 / NO 7: aktual 2, prediksi 4, error 2.
- R055 / NO 13: aktual 2, prediksi 4, error 2.
- R018 / NO 5: aktual 2, prediksi 4, error 2.
- R018 / NO 7: aktual 2, prediksi 4, error 2.
- R018 / NO 15: aktual 2, prediksi 4, error 2.
- R020 / NO 1: aktual 4, prediksi 2, error 2.

**Dummy:** 7 penilaian, 2 UID, 2 kelompok, fold ['5']; train tidak memiliki kelas 1: 7, benar 0.
- R062 / NO 1: aktual 1, prediksi 3, error 2.
- R062 / NO 2: aktual 1, prediksi 3, error 2.
- R062 / NO 5: aktual 1, prediksi 3, error 2.
- R062 / NO 7: aktual 1, prediksi 3, error 2.
- R062 / NO 8: aktual 1, prediksi 3, error 2.
- R062 / NO 12: aktual 1, prediksi 3, error 2.
- R056 / NO 1: aktual 1, prediksi 3, error 2.
- R003 / NO 3: aktual 4, prediksi 3, error 1.
- R003 / NO 4: aktual 4, prediksi 3, error 1.
- R003 / NO 5: aktual 4, prediksi 3, error 1.

**KNN:** 7 penilaian, 2 UID, 2 kelompok, fold ['5']; train tidak memiliki kelas 1: 7, benar 0.
- R032 / NO 12: aktual 4, prediksi 1, error 3.
- R062 / NO 5: aktual 1, prediksi 4, error 3.
- R062 / NO 7: aktual 1, prediksi 4, error 3.
- R003 / NO 4: aktual 4, prediksi 2, error 2.
- R003 / NO 14: aktual 4, prediksi 2, error 2.
- R003 / NO 16: aktual 4, prediksi 2, error 2.
- R050 / NO 5: aktual 4, prediksi 2, error 2.
- R050 / NO 9: aktual 4, prediksi 2, error 2.
- R050 / NO 11: aktual 4, prediksi 2, error 2.
- R019 / NO 4: aktual 4, prediksi 2, error 2.

**Random Forest:** 7 penilaian, 2 UID, 2 kelompok, fold ['5']; train tidak memiliki kelas 1: 7, benar 0.
- R062 / NO 5: aktual 1, prediksi 4, error 3.
- R062 / NO 7: aktual 1, prediksi 4, error 3.
- R062 / NO 12: aktual 1, prediksi 4, error 3.
- R019 / NO 7: aktual 2, prediksi 4, error 2.
- R055 / NO 7: aktual 2, prediksi 4, error 2.
- R018 / NO 3: aktual 2, prediksi 4, error 2.
- R018 / NO 5: aktual 2, prediksi 4, error 2.
- R018 / NO 6: aktual 2, prediksi 4, error 2.
- R018 / NO 7: aktual 2, prediksi 4, error 2.
- R018 / NO 15: aktual 2, prediksi 4, error 2.

## B. Perlu diuji

Perbedaan subkelompok adalah hipotesis, bukan bukti penyebab atau kesalahan responden. Rating 1 yang hanya diuji ketika train tidak memiliki kelas itu tidak membuktikan kemampuan umum model.

## C. Saran berikutnya

1. Kumpulkan lebih banyak kiriman independen untuk kelas langka dan prioritas Lemak.
2. Tinjau definisi target dan kualitas jawaban tanpa mengganti rating.
3. Rancang evaluasi kelompok independen sebelum eksperimen konfirmasi.

Hasil berlaku untuk kiriman baru pada katalog makanan dikenal; bukan keamanan alergi. Prioritas Lemak memiliki 1 kiriman dan 1 kelompok. Perubahan berdasarkan OOF menjadikan eksperimen berikutnya adaptif/eksploratif, bukan konfirmasi independen. Tidak ada pemilihan model produksi atau uji signifikansi. Probabilitas belum terkalibrasi.
