# Rancangan eksperimen

Sasaran: prediksi kiriman baru untuk katalog makanan dikenal. Pembagian berdasarkan kiriman tidak menguji makanan baru.

Bandingkan Dummy baseline, Decision Tree, Random Forest dan KNN. Laporkan klasifikasi per kelas, macro-F1 dengan label tetap [1,2,3,4], confusion matrix, MAE dan support. Jelaskan kelas yang tidak muncul pada fold.

Gunakan grouped cross-validation dengan kelompok identik bersama; semua preprocessing yang belajar dari data di-fit hanya pada data latih setiap fold. Tuning memakai pembagian kelompok di dalam data latih, bukan evaluasi luar. Ranking Top 3 dan penggabungan content-based/ML adalah tahap terpisah. Tidak ada split atau pelatihan pada tahap ini.
