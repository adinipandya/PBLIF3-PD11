"""
app/models/makanan.py
Model ORM untuk tabel makanan dan informasi_gizi.

Rancangan:
  - makanan           : data pokok item menu kiosk
  - informasi_gizi    : data nutrisi, relasi 1-ke-1 dengan makanan
    (PK = FK = id_makanan sesuai ERD diagram)

Keputusan pemetaan (lihat README § Keputusan Pemetaan):
  - berat_porsi_gram boleh NULL (spesifikasi, ERD, object diagram konsisten).
  - label_prioritas dan kelompok_kalori adalah atribut turunan;
    disimpan sebagai kolom agar query mudah, dihitung ulang saat impor.
  - versi_dataset dan sumber_data tersimpan agar data bisa dilacak.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Makanan(Base):
    """Tabel makanan — satu baris satu item menu vending machine."""

    __tablename__ = "makanan"

    # ── PK ────────────────────────────────────────────────────────────────
    id_makanan: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="ID stabil item menu"
    )

    # ── Kolom wajib ───────────────────────────────────────────────────────
    nama_makanan: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Nama lengkap item"
    )
    deskripsi_porsi: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="Deskripsi porsi dari sumber data"
    )
    sumber_data: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="URL atau nama sumber data nutrisi"
    )

    # ── Kolom opsional ────────────────────────────────────────────────────
    berat_porsi_gram: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2),
        nullable=True,
        comment="Berat porsi dalam gram; NULL jika sumber tidak menyebutkan angka",
    )

    # ── Atribut turunan (disimpan untuk kemudahan query) ─────────────────
    kelompok_kalori: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Rendah | Sedang | Tinggi — dihitung dari kalori saat impor",
    )
    label_prioritas: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Label prioritas nutrisi deskriptif; bukan syarat filter",
    )

    # ── Metadata impor ────────────────────────────────────────────────────
    versi_dataset: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="revisi-PD11-R1",
        comment="Versi dataset sumber (mis. revisi-PD11-R1)",
    )
    dibuat_pada: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    diperbarui_pada: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relasi ────────────────────────────────────────────────────────────
    informasi_gizi: Mapped["InformasiGizi"] = relationship(
        "InformasiGizi",
        back_populates="makanan",
        uselist=False,
        cascade="all, delete-orphan",
    )
    kandungan_alergen: Mapped[list["KandunganAlergen"]] = relationship(
        "KandunganAlergen",
        back_populates="makanan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_makanan_nama", "nama_makanan"),
        Index("ix_makanan_kelompok", "kelompok_kalori"),
    )

    def __repr__(self) -> str:
        return f"<Makanan id={self.id_makanan} nama='{self.nama_makanan}'>"


class InformasiGizi(Base):
    """Tabel informasi_gizi — relasi 1-ke-1 dengan makanan.

    PK sekaligus FK ke makanan.id_makanan sesuai ERD diagram.
    Nilai kalori dan gram nutrisi wajib >= 0.
    """

    __tablename__ = "informasi_gizi"

    # ── PK sekaligus FK ───────────────────────────────────────────────────
    id_makanan: Mapped[int] = mapped_column(
        ForeignKey("makanan.id_makanan", ondelete="CASCADE"),
        primary_key=True,
        comment="FK ke makanan; relasi 1-ke-1",
    )

    # ── Kolom nutrisi ─────────────────────────────────────────────────────
    kalori: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, comment="Energi per porsi dalam kkal"
    )
    karbohidrat: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, comment="Karbohidrat dalam gram"
    )
    lemak: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, comment="Lemak dalam gram"
    )
    protein: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, comment="Protein dalam gram"
    )

    # ── Relasi balik ──────────────────────────────────────────────────────
    makanan: Mapped["Makanan"] = relationship(
        "Makanan", back_populates="informasi_gizi"
    )

    __table_args__ = (
        CheckConstraint("kalori >= 0", name="ck_gizi_kalori_nonneg"),
        CheckConstraint("karbohidrat >= 0", name="ck_gizi_karbo_nonneg"),
        CheckConstraint("lemak >= 0", name="ck_gizi_lemak_nonneg"),
        CheckConstraint("protein >= 0", name="ck_gizi_protein_nonneg"),
    )

    def __repr__(self) -> str:
        return (
            f"<InformasiGizi makanan_id={self.id_makanan}"
            f" kalori={self.kalori}>"
        )

