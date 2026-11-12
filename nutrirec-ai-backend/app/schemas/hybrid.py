"""Response contract for the local exploratory hybrid recommendation endpoint."""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class KandidatHybridResponse(BaseModel):
    id_makanan: int
    nama_makanan: str
    deskripsi_porsi: str
    berat_porsi_gram: Optional[Decimal] = None
    kalori: Decimal
    protein: Decimal
    karbohidrat: Decimal
    lemak: Decimal
    skor_hybrid: float = Field(..., ge=0, le=100)


class HasilHybridResponse(BaseModel):
    mode: str = "hybrid_eksploratif"
    versi_model: str
    alpha: float
    jumlah_kandidat: int
    kandidat: list[KandidatHybridResponse] = Field(default_factory=list)
    pesan_kosong: Optional[str] = None
    peringatan: str
