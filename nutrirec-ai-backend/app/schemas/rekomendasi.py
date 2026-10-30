"""
app/schemas/rekomendasi.py
Schema respons rekomendasi konten (content-based) — mode prototipe.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SkorContentBasedResponse(BaseModel):
    """Komposisi skor content-based untuk satu makanan."""

    skor_kalori: float = Field(
        ...,
        description="Skor kedekatan kalori terhadap rentang target (0-1)",
    )
    skor_prioritas: float = Field(
        ...,
        description="Skor prioritas nutrisi hasil normalisasi min-max (0-1)",
    )
    bobot_kalori: float = Field(
        default=0.5,
        description="Bobot skor kalori (parameter simulasi; ditentukan lewat eksperimen)",
    )
    bobot_prioritas: float = Field(
        default=0.5,
        description="Bobot skor prioritas (parameter simulasi; ditentukan lewat eksperimen)",
    )
    skor_content_based: float = Field(
        ...,
        description="CB Score (%) = 100 * (w1 * skor_kalori + w2 * skor_prioritas)",
    )

    model_config = ConfigDict(from_attributes=True)


class KandidatRekomendasiResponse(BaseModel):
    """Respons satu kandidat rekomendasi (Top 3)."""

    id_makanan: int
    nama_makanan: str
    deskripsi_porsi: str
    berat_porsi_gram: Optional[Decimal] = Field(
        None,
        description="Berat porsi gram; null jika tidak tersedia",
    )
    kalori: Decimal
    protein: Decimal
    karbohidrat: Decimal
    lemak: Decimal
    skor_kalori: float
    skor_prioritas: float
    skor_content_based: float


class HasilRekomendasiResponse(BaseModel):
    """Respons akhir proses rekomendasi konten (mode prototipe)."""

    mode: str = Field(
        default="prototipe",
        description="Mode rekomendasi; 'prototipe' pada tahap ini",
    )
    versi_aturan: str = Field(
        default="PD11-R1",
        description="Versi aturan rekomendasi yang dipakai",
    )
    jumlah_kandidat: int = Field(
        default=0,
        description="Jumlah kandidat yang diberikan (maksimal 3)",
    )
    kandidat: list[KandidatRekomendasiResponse] = Field(
        default_factory=list,
        description="Daftar kandidat rekomendasi, diurutkan skor menurun",
    )
    pesan_kosong: Optional[str] = Field(
        default=None,
        description="Pesan ketika tidak ada kandidat yang lolos",
    )

    model_config = ConfigDict(from_attributes=True)
