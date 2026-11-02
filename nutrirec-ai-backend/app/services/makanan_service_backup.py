"""
app/services/makanan_service.py
Logika bisnis untuk data makanan.

Saat ini berupa lapisan tipis yang memanggil repository.
Pada tahap rekomendasi, logika penyaringan alergi dan penilaian skor
akan ditambahkan di sini (bukan di router).
"""

from sqlalchemy.orm import Session

from app.repositories import makanan_repo
from app.models.makanan import Makanan


def get_semua_makanan(db: Session) -> list[Makanan]:
    """Ambil semua item makanan dari database."""
    return makanan_repo.get_all_makanan(db)


def get_makanan_detail(db: Session, id_makanan: int) -> Makanan | None:
    """Ambil detail satu makanan; None jika tidak ditemukan."""
    return makanan_repo.get_makanan_by_id(db, id_makanan)


# ─── Titik pengembangan tahap berikutnya ──────────────────────────────────────
# def filter_dan_rekomendasikan(db, permintaan) -> list:
#     """
#     1. Ambil semua makanan dengan gizi valid.
#     2. Jika ada alergi: filter kandungan_alergen + status_verifikasi.
#     3. Hitung Content-Based Score (skor kalori + skor prioritas).
#     4. Prediksi rating dengan model ML yang dimuat dari file.
#     5. Hitung Suitability Score dan urutkan.
#     6. Kembalikan maks. 3 kandidat.
#     """
#     raise NotImplementedError("Modul rekomendasi belum diimplementasikan.")

