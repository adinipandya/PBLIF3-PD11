# app/models/__init__.py
# Ekspor semua model agar Alembic dapat menemukan metadata.

from app.models.base import Base
from app.models.makanan import Makanan, InformasiGizi
from app.models.alergen import Alergen, KandunganAlergen
from app.models.referensi import TargetKalori, PrioritasNutrisi
from app.models.riwayat_rekomendasi import RiwayatRekomendasi

__all__ = [
    "Base",
    "Makanan",
    "InformasiGizi",
    "Alergen",
    "KandunganAlergen",
    "TargetKalori",
    "PrioritasNutrisi",
    "RiwayatRekomendasi",
]

