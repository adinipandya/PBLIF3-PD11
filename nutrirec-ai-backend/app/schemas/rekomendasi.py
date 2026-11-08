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
        ge=0,
        le=1,
        description="Skor kesesuaian kalori kategori terpilih (0-1)",
    )
    skor_prioritas: float = Field(
        ...,
        ge=0,
        le=1,
        description="Skor prioritas min-max katalog atau acuan Seimbang (0-1)",
    )
    bobot_kalori: float = Field(
        default=0.5,
        description="Bobot awal prototipe untuk skor kalori",
    )
    bobot_prioritas: float = Field(
        default=0.5,
        description="Bobot awal prototipe untuk skor prioritas nutrisi",
    )
    skor_content_based: float = Field(
        ...,
        ge=0,
        le=100,
        description="Skor CB 0-100; parameter awal prototipe, bukan prediksi ML atau keamanan alergi.",
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
    skor_kalori: float = Field(..., ge=0, le=1)
    skor_prioritas: float = Field(..., ge=0, le=1)
    skor_content_based: float = Field(
        ...,
        ge=0,
        le=100,
        description="Skor CB 0–100; prototipe, bukan prediksi ML atau keamanan alergi.",
    )

class HasilRekomendasiResponse(BaseModel):
    """Respons akhir proses rekomendasi konten (mode prototipe)."""

    mode: str = Field(
        default="prototipe",
        description="Mode rekomendasi; 'prototipe' pada tahap ini",
    )
    versi_aturan: str = Field(
        default="PD11-R2",
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
