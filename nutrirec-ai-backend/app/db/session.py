"""
app/db/session.py
Manajemen sesi dan engine SQLAlchemy.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings

settings = get_settings()

# Buat engine; pool_pre_ping memeriksa koneksi sebelum dipakai kembali
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Session:
    """Dependency FastAPI — buka sesi, serahkan, tutup setelah selesai."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Periksa apakah koneksi ke database berhasil. Dipakai oleh /ready."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

