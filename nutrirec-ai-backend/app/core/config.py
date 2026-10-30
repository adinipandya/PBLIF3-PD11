"""
app/core/config.py
Konfigurasi aplikasi dibaca dari variabel lingkungan (.env).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Seluruh konfigurasi aplikasi NutriRec AI.

    Nilai default hanya untuk pengembangan lokal; selalu timpa lewat .env
    pada lingkungan produksi.
    """

    # ── Koneksi database ──────────────────────────────────────────────────
    DATABASE_URL: str = (
        "mysql+pymysql://nutrirec_user:password@localhost:3306/nutrirec_db"
    )

    # ── Metadata aplikasi ─────────────────────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = True

    # ── CORS ──────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:5500"

    # ── Versi dataset yang aktif ──────────────────────────────────────────
    DATASET_VERSION: str = "revisi-PD11-R1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """Konversi string ALLOWED_ORIGINS menjadi list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Kembalikan instance Settings yang di-cache (singleton)."""
    return Settings()

