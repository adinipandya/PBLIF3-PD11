"""
app/api/v1/__init__.py
Router utama API v1.
"""

from fastapi import APIRouter
from app.api.v1 import foods, reference_data

router = APIRouter(prefix="/api/v1")
router.include_router(foods.router)
router.include_router(reference_data.router)

