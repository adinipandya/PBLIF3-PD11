"""
app/api/v1/foods.py
Router endpoint makanan.

GET /api/v1/foods          — daftar semua makanan
GET /api/v1/foods/{id}     — detail satu makanan
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.makanan import MakananResponse, MakananListResponse, AlergenRingkas
from app.services.makanan_service import get_semua_makanan, get_makanan_detail
from app.models.makanan import Makanan
from app.models.alergen import KandunganAlergen

router = APIRouter(prefix="/foods", tags=["Makanan"])


def _to_response(makanan: Makanan) -> MakananResponse:
    """Konversi ORM Makanan ke schema respons."""
    alergen_list = []
    for ka in (makanan.kandungan_alergen or []):
        alergen_list.append(
            AlergenRingkas(
                id_alergen=ka.alergen.id_alergen,
                nama_alergen=ka.alergen.nama_alergen,
                status_verifikasi=ka.status_verifikasi,
                bahan_penyebab=ka.bahan_penyebab,
            )
        )
    return MakananResponse(
        id_makanan=makanan.id_makanan,
        nama_makanan=makanan.nama_makanan,
        deskripsi_porsi=makanan.deskripsi_porsi,
        berat_porsi_gram=makanan.berat_porsi_gram,
        sumber_data=makanan.sumber_data,
        kelompok_kalori=makanan.kelompok_kalori,
        label_prioritas=makanan.label_prioritas,
        versi_dataset=makanan.versi_dataset,
        informasi_gizi=makanan.informasi_gizi,
        alergen=alergen_list,
    )


@router.get(
    "",
    response_model=MakananListResponse,
    summary="Daftar semua makanan",
    description=(
        "Mengembalikan seluruh item makanan beserta informasi gizi dan "
        "daftar alergen tercatat. Daftar alergen kosong bukan berarti bebas alergen."
    ),
)
def list_makanan(db: Session = Depends(get_db)) -> MakananListResponse:
    makanan_list = get_semua_makanan(db)
    items = [_to_response(m) for m in makanan_list]
    return MakananListResponse(total=len(items), items=items)


@router.get(
    "/{id_makanan}",
    response_model=MakananResponse,
    summary="Detail satu makanan",
    responses={
        404: {"description": "Makanan tidak ditemukan"},
    },
)
def detail_makanan(
    id_makanan: int, db: Session = Depends(get_db)
) -> MakananResponse:
    makanan = get_makanan_detail(db, id_makanan)
    if makanan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Makanan dengan id={id_makanan} tidak ditemukan.",
        )
    return _to_response(makanan)

