"""Endpoint riwayat rekomendasi anonim per sesi kiosk."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.riwayat_rekomendasi import RiwayatRekomendasi

router = APIRouter(prefix="/recommendation-history", tags=["Riwayat Rekomendasi"])


@router.get("", summary="Riwayat rekomendasi sesi kiosk")
def get_recommendation_history(
    session_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(RiwayatRekomendasi)
        .where(RiwayatRekomendasi.session_id == str(session_id))
        .order_by(RiwayatRekomendasi.dibuat_pada.desc(), RiwayatRekomendasi.id_riwayat.desc())
        .limit(limit)
    ).all()
    return {
        "session_id": str(session_id),
        "total": len(rows),
        "items": [
            {
                "id_riwayat": row.id_riwayat,
                "permintaan": row.permintaan,
                "hasil": row.hasil,
                "dibuat_pada": row.dibuat_pada,
            }
            for row in rows
        ],
    }


@router.delete("", summary="Hapus seluruh riwayat sesi kiosk")
def delete_recommendation_history(session_id: UUID, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            delete(RiwayatRekomendasi).where(
                RiwayatRekomendasi.session_id == str(session_id)
            )
        )
        db.commit()
        return {"session_id": str(session_id), "deleted": result.rowcount or 0}
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Riwayat sementara tidak dapat dihapus.") from exc
