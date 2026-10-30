"""
app/repositories/makanan_repo.py
Repository untuk operasi database pada tabel makanan dan informasi_gizi.

Semua query database dikumpulkan di sini; router dan service tidak
memanggil SQLAlchemy secara langsung.
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.models.makanan import Makanan, InformasiGizi
from app.models.alergen import KandunganAlergen, Alergen


def get_all_makanan(db: Session) -> list[Makanan]:
    """Kembalikan semua makanan beserta gizi dan alergen."""
    stmt = (
        select(Makanan)
        .options(
            joinedload(Makanan.informasi_gizi),
            joinedload(Makanan.kandungan_alergen).joinedload(
                KandunganAlergen.alergen
            ),
        )
        .order_by(Makanan.id_makanan)
    )
    return list(db.scalars(stmt).unique().all())


def get_makanan_by_id(db: Session, id_makanan: int) -> Makanan | None:
    """Kembalikan satu makanan berdasarkan ID; None jika tidak ditemukan."""
    stmt = (
        select(Makanan)
        .where(Makanan.id_makanan == id_makanan)
        .options(
            joinedload(Makanan.informasi_gizi),
            joinedload(Makanan.kandungan_alergen).joinedload(
                KandunganAlergen.alergen
            ),
        )
    )
    return db.scalars(stmt).first()

