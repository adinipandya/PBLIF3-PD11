"""Statistik katalog makanan untuk dashboard pengelola."""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alergen import KandunganAlergen
from app.models.makanan import InformasiGizi, Makanan

router = APIRouter(prefix="/foods", tags=["Statistik Katalog"])


@router.get(
    "/statistics",
    summary="Statistik kualitas katalog makanan",
    description=(
        "Menyediakan ringkasan jumlah makanan, kelengkapan informasi gizi, "
        "kelompok kalori, dan status verifikasi data alergen untuk dashboard pengelola."
    ),
)
def statistik_katalog_makanan(db: Session = Depends(get_db)) -> dict:
    total_makanan = db.scalar(select(func.count()).select_from(Makanan)) or 0
    makanan_dengan_gizi = (
        db.scalar(
            select(func.count()).select_from(
                select(InformasiGizi.id_makanan)
                .join(Makanan, Makanan.id_makanan == InformasiGizi.id_makanan)
                .subquery()
            )
        )
        or 0
    )

    kelompok_rows = db.execute(
        select(Makanan.kelompok_kalori, func.count())
        .group_by(Makanan.kelompok_kalori)
    ).all()
    kelompok_kalori = {
        (kelompok or "Belum dikategorikan"): jumlah
        for kelompok, jumlah in kelompok_rows
    }

    status_rows = db.execute(
        select(KandunganAlergen.status_verifikasi, func.count())
        .group_by(KandunganAlergen.status_verifikasi)
    ).all()
    status_verifikasi_alergen = {
        status: jumlah for status, jumlah in status_rows
    }

    return {
        "total_makanan": total_makanan,
        "makanan_dengan_informasi_gizi": makanan_dengan_gizi,
        "makanan_tanpa_informasi_gizi": total_makanan - makanan_dengan_gizi,
        "kelompok_kalori": kelompok_kalori,
        "data_alergen": {
            "total_relasi": sum(status_verifikasi_alergen.values()),
            "status_verifikasi": status_verifikasi_alergen,
            "catatan": "Data alergen kosong tidak berarti makanan bebas alergen.",
        },
    }
