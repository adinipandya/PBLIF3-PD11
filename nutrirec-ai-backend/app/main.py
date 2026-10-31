"""
app/main.py
Entry point aplikasi FastAPI NutriRec AI.

Endpoint sistem:
  GET /health  — status aplikasi
  GET /ready   — kesiapan koneksi database

Endpoint API:
  /api/v1/foods
  /api/v1/foods/{id}
  /api/v1/reference-data
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1 import router as api_v1_router
from app.db.session import check_db_connection

settings = get_settings()

app = FastAPI(
    title="NutriRec AI — Backend",
    description=(
        "Backend sistem rekomendasi nutrisi berbasis kiosk vending machine. "
        "PBL PD11 | Revisi PD11-R1."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Router API ────────────────────────────────────────────────────────────────
app.include_router(api_v1_router)


# ── Endpoint sistem ───────────────────────────────────────────────────────────

@app.get("/health", tags=["Sistem"], summary="Status aplikasi")
def health_check():
    """Mengembalikan status aplikasi. Tidak memeriksa database."""
    return {
        "status": "ok",
        "aplikasi": "NutriRec AI Backend",
        "versi": "0.1.0",
        "lingkungan": settings.APP_ENV,
    }


@app.get("/ready", tags=["Sistem"], summary="Kesiapan koneksi database")
def readiness_check():
    """
    Memeriksa apakah koneksi ke database MySQL berhasil.
    Mengembalikan 200 jika siap, 503 jika gagal.
    """
    db_ok = check_db_connection()
    if db_ok:
        return {"status": "ready", "database": "connected"}
    from fastapi import Response
    return Response(
        content='{"status":"not_ready","database":"disconnected"}',
        status_code=503,
        media_type="application/json",
    )

