"""
app/schemas/referensi.py
Schema Pydantic untuk data referensi: target kalori, prioritas nutrisi, alergen.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TargetKaloriResponse(BaseModel):
    id_target: int
    nama_kategori: str
    kalori_min: Optional[int] = None
    kalori_max: Optional[int] = None
    keterangan: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PrioritasNutrisiResponse(BaseModel):
    id_prioritas: int
    nama_prioritas: str
    jenis: str
    keterangan: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AlergenResponse(BaseModel):
    id_alergen: int
    nama_alergen: str
    kata_kunci: str

    model_config = ConfigDict(from_attributes=True)


class ReferenceDataResponse(BaseModel):
    """Gabungan semua data referensi yang dibutuhkan kiosk."""

    target_kalori: list[TargetKaloriResponse]
    prioritas_nutrisi: list[PrioritasNutrisiResponse]
    alergen: list[AlergenResponse]

