"""
app/schemas/personalisasi.py
Schema Pydantic untuk permintaan personalisasi kiosk (tahap berikutnya).

Divalidasi sekarang agar endpoint rekomendasi dapat dikembangkan tanpa
mengubah kontrak API. Endpoint rekomendasi BELUM diaktifkan pada tahap ini.

Aturan validasi (sesuai spesifikasi FR-02, FR-03, FR-04):
  - target_kalori_id : tepat satu nilai ID TargetKalori
  - prioritas_id     : tepat satu nilai ID PrioritasNutrisi
  - status_alergi    : boolean
  - alergen_ids      : daftar ID unik
    - Jika status_alergi=True  → minimal 1 alergen
    - Jika status_alergi=False → daftar harus kosong
"""

from pydantic import BaseModel, Field, model_validator
from typing import Annotated


class PermintaanPersonalisasi(BaseModel):
    """Body permintaan personalisasi dari kiosk."""

    target_kalori_id: int = Field(
        ...,
        description="ID TargetKalori yang dipilih (lihat GET /api/v1/reference-data)",
        gt=0,
    )
    prioritas_id: int = Field(
        ...,
        description="ID PrioritasNutrisi yang dipilih",
        gt=0,
    )
    status_alergi: bool = Field(
        ...,
        description="True = pengguna menyatakan memiliki alergi",
    )
    alergen_ids: list[Annotated[int, Field(gt=0)]] = Field(
        default_factory=list,
        description=(
            "Daftar ID alergen yang dihindari. "
            "Wajib tidak kosong jika status_alergi=True. "
            "Wajib kosong jika status_alergi=False."
        ),
    )

    @model_validator(mode="after")
    def validasi_aturan_alergi(self) -> "PermintaanPersonalisasi":
        """Pastikan konsistensi antara status_alergi dan alergen_ids."""
        # Hilangkan duplikasi ID
        unique_ids = list(dict.fromkeys(self.alergen_ids))
        if len(unique_ids) != len(self.alergen_ids):
            self.alergen_ids = unique_ids

        if self.status_alergi and len(self.alergen_ids) == 0:
            raise ValueError(
                "Jika status_alergi=True, minimal satu alergen harus dipilih."
            )
        if not self.status_alergi and len(self.alergen_ids) > 0:
            raise ValueError(
                "Jika status_alergi=False, daftar alergen harus kosong."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Contoh: Rendah kalori, prioritas Protein, alergi Telur",
                    "value": {
                        "target_kalori_id": 1,
                        "prioritas_id": 1,
                        "status_alergi": True,
                        "alergen_ids": [1],
                    },
                },
                {
                    "summary": "Contoh: Sedang kalori, prioritas Seimbang, tanpa alergi",
                    "value": {
                        "target_kalori_id": 2,
                        "prioritas_id": 4,
                        "status_alergi": False,
                        "alergen_ids": [],
                    },
                },
            ]
        }
    }

