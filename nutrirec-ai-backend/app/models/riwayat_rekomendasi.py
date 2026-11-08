"""Riwayat rekomendasi anonim berdasarkan sesi kiosk, tanpa akun pengguna."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiwayatRekomendasi(Base):
    __tablename__ = "riwayat_rekomendasi"

    id_riwayat: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    permintaan: Mapped[dict] = mapped_column(JSON, nullable=False)
    hasil: Mapped[dict] = mapped_column(JSON, nullable=False)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_riwayat_session_dibuat", "session_id", "dibuat_pada"),
    )
