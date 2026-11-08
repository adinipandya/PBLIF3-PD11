"""
app/api/v1/rekomendasi.py
Router endpoint rekomendasi konten (content-based) — mode prototipe.

POST /api/v1/recommendations/content-based
"""

import logging
from uuid import UUID
from fastapi import Header

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.personalisasi import PermintaanPersonalisasi
from app.schemas.rekomendasi import HasilRekomendasiResponse, KandidatRekomendasiResponse
from app.models.riwayat_rekomendasi import RiwayatRekomendasi
from app.services.makanan_service import (
    KONDISI_TIDAK_KOSONG_MSG,
    VERSI_ATURAN,
    filter_dan_rekomendasikan,
)

router = APIRouter(prefix="/recommendations", tags=["Rekomendasi"])
logger = logging.getLogger(__name__)


@router.post(
    "/content-based",
    response_model=HasilRekomendasiResponse,
    summary="Rekomendasi konten (content-based) — mode prototipe",
    description=(
        "Filter alergi secara ketat, lalu urutkan maksimal 3 kandidat dengan skor "
        "kalori dan prioritas nutrisi. Skor CB adalah parameter awal prototipe, "
        "bukan probabilitas atau prediksi ML."
    ),
)
def rekomendasi_content_based(
    permintaan: PermintaanPersonalisasi,
    db: Session = Depends(get_db),
    x_session_id: UUID | None = Header(default=None, alias="X-Session-ID"),
) -> HasilRekomendasiResponse:
    try:
        kandidat = filter_dan_rekomendasikan(db, permintaan)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Recommendation database operation failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Layanan rekomendasi sementara tidak tersedia.",
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

    hasil = HasilRekomendasiResponse(
        mode="prototipe",
        versi_aturan=VERSI_ATURAN,
        jumlah_kandidat=len(items),
        kandidat=items,
        pesan_kosong=None if items else KONDISI_TIDAK_KOSONG_MSG,
    )

    # Riwayat bersifat anonim dan hanya dicatat jika kiosk mengirim ID sesi.
    if x_session_id is not None:
        try:
            db.add(
                RiwayatRekomendasi(
                    session_id=str(x_session_id),
                    permintaan=permintaan.model_dump(mode="json"),
                    hasil=hasil.model_dump(mode="json"),
                )
            )
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.exception("Failed to save anonymous recommendation history.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Riwayat rekomendasi sementara tidak dapat disimpan.",
            ) from e

    return hasil
