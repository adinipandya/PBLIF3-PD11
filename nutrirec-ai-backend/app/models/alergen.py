"""
app/models/alergen.py
Model ORM untuk tabel alergen dan kandungan_alergen (tabel penghubung).

Sebelas pilihan bahan sesuai spesifikasi:
  Telur, Kedelai, Jagung, Kelapa, Ayam, Daging sapi,
  Gandum, Kacang-kacangan, Udang/seafood, Ikan, Beras.

kandungan_alergen menyimpan hubungan M:N makanan ↔ alergen beserta
  - status_verifikasi : "Belum diverifikasi" | "Terverifikasi"
  - bahan_penyebab    : nama bahan konkret yang memicu alergen

CATATAN: Daftar alergen kosong TIDAK berarti bebas alergen.
Status "Belum diverifikasi" berarti item HARUS DIKELUARKAN dari hasil
pada mode operasional jika pengguna menyatakan memiliki alergi.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Alergen(Base):
    """Tabel alergen — daftar referensi 11 bahan pilihan kiosk."""

    __tablename__ = "alergen"

    id_alergen: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    nama_alergen: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Nama tampilan: Telur, Kedelai, dst.",
    )
    kata_kunci: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment=(
            "Kata kunci pencocokan dari dataset (misal: 'telur', 'kedelai')."
            " Bukan untuk pencarian kata bebas di runtime."
        ),
    )

    # ── Relasi ────────────────────────────────────────────────────────────
    kandungan_makanan: Mapped[list["KandunganAlergen"]] = relationship(
        "KandunganAlergen",
        back_populates="alergen",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Alergen id={self.id_alergen} nama='{self.nama_alergen}'>"


class KandunganAlergen(Base):
    """Tabel penghubung kandungan_alergen (M:N makanan ↔ alergen).

    Setiap baris menyatakan satu alergen yang terkandung dalam satu makanan,
    beserta status verifikasi dan nama bahan penyebab.

    PK gabungan: (id_makanan, id_alergen).
    """

    __tablename__ = "kandungan_alergen"

    # ── PK gabungan ───────────────────────────────────────────────────────
    id_makanan: Mapped[int] = mapped_column(
        ForeignKey("makanan.id_makanan", ondelete="CASCADE"),
        primary_key=True,
        comment="FK ke makanan",
    )
    id_alergen: Mapped[int] = mapped_column(
        ForeignKey("alergen.id_alergen", ondelete="CASCADE"),
        primary_key=True,
        comment="FK ke alergen",
    )

    # ── Atribut verifikasi ────────────────────────────────────────────────
    status_verifikasi: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Belum diverifikasi",
        comment="'Belum diverifikasi' | 'Terverifikasi'",
    )
    bahan_penyebab: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="Nama bahan konkret yang memicu alergen ini pada item ini",
    )
    catatan_verifikasi: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Catatan tambahan tentang verifikasi dari dataset",
    )
    dibuat_pada: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # ── Relasi ────────────────────────────────────────────────────────────
    makanan: Mapped["app.models.makanan.Makanan"] = relationship(
        "Makanan", back_populates="kandungan_alergen"
    )
    alergen: Mapped["Alergen"] = relationship(
        "Alergen", back_populates="kandungan_makanan"
    )

    __table_args__ = (
        CheckConstraint(
            "status_verifikasi IN ('Belum diverifikasi', 'Terverifikasi')",
            name="ck_kandungan_status_valid",
        ),
        Index("ix_kandungan_makanan", "id_makanan"),
        Index("ix_kandungan_alergen", "id_alergen"),
    )

    def __repr__(self) -> str:
        return (
            f"<KandunganAlergen makanan={self.id_makanan}"
            f" alergen={self.id_alergen}"
            f" status='{self.status_verifikasi}'>"
        )

