"""
app/models/referensi.py
Model ORM untuk tabel referensi: target_kalori dan prioritas_nutrisi.

Tabel ini memuat data statis yang dimasukkan lewat migrasi data referensi,
bukan dari Excel. Mereka menjadi sumber acuan pilihan kiosk.

target_kalori
  Rendah  : kalori_min=NULL, kalori_max=300  (eksklusif, < 300 kkal)
  Sedang  : kalori_min=300,  kalori_max=500  (inklusif, 300–500 kkal)
  Tinggi  : kalori_min=500,  kalori_max=NULL (eksklusif, > 500 kkal)

prioritas_nutrisi
  jenis = 'zat_gizi'  → Protein, Karbohidrat, Lemak
  jenis = 'seimbang'  → Seimbang
  Kolom acuan_protein/karbo/lemak diisi hanya untuk jenis='seimbang'.
"""

from sqlalchemy import (
    CheckConstraint,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TargetKalori(Base):
    """Tabel target_kalori — tiga pilihan rentang kalori kiosk."""

    __tablename__ = "target_kalori"

    id_target: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    nama_kategori: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        comment="'Rendah' | 'Sedang' | 'Tinggi'",
    )
    # NULL berarti batas terbuka (tidak ada batas bawah/atas)
    kalori_min: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Batas bawah inklusif (kkal); NULL jika terbuka",
    )
    kalori_max: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Batas atas eksklusif (kkal); NULL jika terbuka",
    )
    keterangan: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Penjelasan rentang untuk tampilan kiosk",
    )

    __table_args__ = (
        CheckConstraint(
            "nama_kategori IN ('Rendah', 'Sedang', 'Tinggi')",
            name="ck_target_nama_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TargetKalori id={self.id_target} nama='{self.nama_kategori}'>"
        )


class PrioritasNutrisi(Base):
    """Tabel prioritas_nutrisi — empat pilihan prioritas kiosk.

    Kolom acuan_* hanya relevan untuk baris jenis='seimbang';
    baris lainnya dapat dibiarkan NULL.
    """

    __tablename__ = "prioritas_nutrisi"

    id_prioritas: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    nama_prioritas: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
        comment="'Protein' | 'Karbohidrat' | 'Lemak' | 'Seimbang'",
    )
    jenis: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'zat_gizi' atau 'seimbang'",
    )
    zat_gizi: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Nama zat gizi untuk jenis='zat_gizi'",
    )
    min_persen_energi: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Ambang batas proporsi energi (0–1) untuk skor prioritas",
    )
    # Kolom acuan untuk 'Seimbang'
    acuan_protein: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Acuan proporsi protein untuk prioritas Seimbang (mis. 0.15)",
    )
    acuan_karbo: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Acuan proporsi karbo untuk prioritas Seimbang (mis. 0.55)",
    )
    acuan_lemak: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Acuan proporsi lemak untuk prioritas Seimbang (mis. 0.30)",
    )
    keterangan: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Penjelasan prioritas untuk tampilan kiosk",
    )

    __table_args__ = (
        CheckConstraint(
            "nama_prioritas IN ('Protein', 'Karbohidrat', 'Lemak', 'Seimbang')",
            name="ck_prioritas_nama_valid",
        ),
        CheckConstraint(
            "jenis IN ('zat_gizi', 'seimbang')",
            name="ck_prioritas_jenis_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PrioritasNutrisi id={self.id_prioritas}"
            f" nama='{self.nama_prioritas}'>"
        )

