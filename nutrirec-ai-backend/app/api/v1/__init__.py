"""Router utama API v1."""

from fastapi import APIRouter
from app.api.v1 import foods, reference_data, rekomendasi, history, food_statistics

router = APIRouter(prefix="/api/v1")

# Rute statis harus didaftarkan sebelum /foods/{id_makanan} agar
# kata "statistics" tidak dianggap sebagai parameter ID makanan.
router.include_router(food_statistics.router)
router.include_router(foods.router)
router.include_router(reference_data.router)
router.include_router(rekomendasi.router)
router.include_router(history.router)
