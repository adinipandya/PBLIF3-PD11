"""
app/schemas/makanan.py
Schema Pydantic untuk validasi dan serialisasi data makanan.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── InformasiGizi ────────────────────────────────────────────────────────────

class InformasiGiziResponse(BaseModel):
    """Respons data nutrisi per porsi."""

    kalori: Decimal = Field(..., description="Energi per porsi (kkal)")
    karbohidrat: Decimal = Field(..., description="Karbohidrat (g)")
    lemak: Decimal = Field(..., description="Lemak (g)")
    protein: Decimal = Field(..., description="Protein (g)")

    model_config = ConfigDict(from_attributes=True)


# ─── Alergen (ringkas untuk respons makanan) ──────────────────────────────────

class AlergenRingkas(BaseModel):
    """Informasi alergen ringkas yang disertakan pada respons makanan."""

    id_alergen: int
    nama_alergen: str
    status_verifikasi: str
    bahan_penyebab: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Makanan ──────────────────────────────────────────────────────────────────

class MakananResponse(BaseModel):
    """Respons lengkap satu item makanan."""

    id_makanan: int
    nama_makanan: str
    deskripsi_porsi: str
    berat_porsi_gram: Optional[Decimal] = Field(
        None,
        description="Berat porsi gram; null jika sumber tidak menyebutkan angka",
    )
    sumber_data: str
    kelompok_kalori: Optional[str] = Field(
        None, description="Rendah | Sedang | Tinggi"
    )
    label_prioritas: Optional[str] = Field(
        None, description="Label prioritas nutrisi deskriptif"
    )
    versi_dataset: str
    informasi_gizi: Optional[InformasiGiziResponse] = None
    alergen: list[AlergenRingkas] = Field(
        default_factory=list,
        description="Daftar alergen tercatat. Kosong bukan berarti bebas alergen.",
    )

    model_config = ConfigDict(from_attributes=True)


class MakananListResponse(BaseModel):
    """Respons daftar makanan dengan metadata paginasi sederhana."""

    total: int
    items: list[MakananResponse]

