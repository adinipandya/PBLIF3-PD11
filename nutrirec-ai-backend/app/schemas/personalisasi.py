"""
app/schemas/personalisasi.py
Schema Pydantic untuk permintaan personalisasi rekomendasi.

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
        description="True = pengguna menyatakan memiliki alergi; pilih satu atau lebih alergen.",
    )
    alergen_ids: list[Annotated[int, Field(gt=0)]] = Field(
        default_factory=list,
        description=(
            "Daftar ID unik alergen yang dihindari. "
            "Wajib tidak kosong jika status_alergi=True. "
            "Wajib kosong jika status_alergi=False. ID duplikat dihapus."
        ),
    )

    @model_validator(mode="after")
    def validasi_aturan_alergi(self) -> "PermintaanPersonalisasi":
        """Pastikan konsistensi antara status_alergi dan alergen_ids."""
        if self.status_alergi and not self.alergen_ids:
            raise ValueError(
                "Pilih minimal satu alergen jika Anda memiliki alergi."
            )
        if not self.status_alergi and self.alergen_ids:
            raise ValueError(
                "Daftar alergen harus kosong jika Anda tidak memiliki alergi."
            )
        if len(set(self.alergen_ids)) != len(self.alergen_ids):
            raise ValueError("Setiap alergen hanya boleh dipilih satu kali.")
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

