"""
app/repositories/referensi_repo.py
Repository untuk tabel referensi (target_kalori, prioritas_nutrisi, alergen).
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.referensi import TargetKalori, PrioritasNutrisi
from app.models.alergen import Alergen


def get_all_target_kalori(db: Session) -> list[TargetKalori]:
    return list(
        db.scalars(select(TargetKalori).order_by(TargetKalori.id_target)).all()
    )


def get_all_prioritas_nutrisi(db: Session) -> list[PrioritasNutrisi]:
    return list(
        db.scalars(
            select(PrioritasNutrisi).order_by(PrioritasNutrisi.id_prioritas)
        ).all()
    )


def get_all_alergen(db: Session) -> list[Alergen]:
    return list(
        db.scalars(select(Alergen).order_by(Alergen.id_alergen)).all()
    )

