"""Local exploratory hybrid recommendation endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.hybrid import HasilHybridResponse
from app.schemas.personalisasi import PermintaanPersonalisasi
from app.services.hybrid_service import (
    EXPERIMENTAL_WARNING,
    HybridModelUnavailableError,
    rekomendasi_hybrid,
)

router = APIRouter(prefix="/recommendations", tags=["Rekomendasi Hybrid Eksploratif"])
logger = logging.getLogger(__name__)


@router.post(
    "/hybrid",
    response_model=HasilHybridResponse,
    summary="Rekomendasi hybrid lokal (eksploratif)",
    description="Menggabungkan skor content-based dan prediksi rating ML tersimpan. Bukan model produksi.",
)
def rekomendasi_hybrid_endpoint(
    permintaan: PermintaanPersonalisasi,
    db: Session = Depends(get_db),
) -> HasilHybridResponse:
    try:
        result = rekomendasi_hybrid(db, permintaan)
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Hybrid recommendation database operation failed.")
        raise HTTPException(status_code=503, detail="Layanan rekomendasi sementara tidak tersedia.") from exc
    except HybridModelUnavailableError as exc:
        logger.exception("Saved exploratory model could not be loaded or used.")
        raise HTTPException(status_code=503, detail="Artefak model hybrid lokal tidak siap digunakan.") from exc
    return HasilHybridResponse(**result, alpha=0.5, peringatan=EXPERIMENTAL_WARNING)
