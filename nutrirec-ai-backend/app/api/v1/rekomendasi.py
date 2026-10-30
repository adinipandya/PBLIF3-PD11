"""
app/api/v1/rekomendasi.py
Router endpoint rekomendasi konten (content-based) — mode prototipe.

POST /api/v1/recommendations/content-based
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.personalisasi import PermintaanPersonalisasi
from app.schemas.rekomendasi import HasilRekomendasiResponse, KandidatRekomendasiResponse
from app.services.makanan_service import (
    KONDISI_TIDAK_KOSONG_MSG,
    VERSI_ATURAN,
    filter_dan_rekomendasikan,
)

router = APIRouter(prefix="/recommendations", tags=["Rekomendasi"])


@router.post(
    "/content-based",
    response_model=HasilRekomendasiResponse,
    summary="Rekomendasi konten (content-based) — mode prototipe",
    description=(
        "Mengembalikan maksimal 3 kandidat rekomendasi berdasarkan content-based "
        "scoring (skor kalori + skor prioritas). Mode ini adalah prototipe; skor "
        "content-based bukan skor gabungan ML."
    ),
)
def rekomendasi_content_based(
    permintaan: PermintaanPersonalisasi,
    db: Session = Depends(get_db),
) -> HasilRekomendasiResponse:
    try:
        kandidat = filter_dan_rekomendasikan(db, permintaan)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    items = [
        KandidatRekomendasiResponse(
            id_makanan=item["makanan"].id_makanan,
            nama_makanan=item["makanan"].nama_makanan,
            deskripsi_porsi=item["makanan"].deskripsi_porsi,
            berat_porsi_gram=item["makanan"].berat_porsi_gram,
            kalori=item["makanan"].informasi_gizi.kalori,
            protein=item["makanan"].informasi_gizi.protein,
            karbohidrat=item["makanan"].informasi_gizi.karbohidrat,
            lemak=item["makanan"].informasi_gizi.lemak,
            skor_kalori=item["skor_kalori"],
            skor_prioritas=item["skor_prioritas"],
            skor_content_based=item["skor_content_based"],
        )
        for item in kandidat
    ]

    return HasilRekomendasiResponse(
        mode="prototipe",
        versi_aturan=VERSI_ATURAN,
        jumlah_kandidat=len(items),
        kandidat=items,
        pesan_kosong=None if items else KONDISI_TIDAK_KOSONG_MSG,
    )
