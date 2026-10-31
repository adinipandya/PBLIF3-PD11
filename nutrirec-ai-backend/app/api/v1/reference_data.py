"""
app/api/v1/reference_data.py
Router endpoint data referensi.

GET /api/v1/reference-data  — pilihan kalori, prioritas, dan alergen
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.referensi_repo import (
    get_all_target_kalori,
    get_all_prioritas_nutrisi,
    get_all_alergen,
)
from app.schemas.referensi import ReferenceDataResponse

router = APIRouter(prefix="/reference-data", tags=["Referensi"])


@router.get(
    "",
    response_model=ReferenceDataResponse,
    summary="Data referensi kiosk",
    description=(
        "Mengembalikan semua pilihan yang tersedia untuk kiosk: "
        "target kalori, prioritas nutrisi, dan daftar alergen. "
        "Gunakan ID dari respons ini saat membuat permintaan personalisasi."
    ),
)
def get_reference_data(db: Session = Depends(get_db)) -> ReferenceDataResponse:
    return ReferenceDataResponse(
        target_kalori=get_all_target_kalori(db),
        prioritas_nutrisi=get_all_prioritas_nutrisi(db),
        alergen=get_all_alergen(db),
    )

