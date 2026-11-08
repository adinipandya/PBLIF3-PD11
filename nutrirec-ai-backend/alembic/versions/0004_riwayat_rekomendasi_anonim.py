"""Simpan riwayat rekomendasi anonim per sesi kiosk.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "riwayat_rekomendasi",
        sa.Column("id_riwayat", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("permintaan", sa.JSON(), nullable=False),
        sa.Column("hasil", sa.JSON(), nullable=False),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_riwayat_session_dibuat",
        "riwayat_rekomendasi",
        ["session_id", "dibuat_pada"],
    )


def downgrade() -> None:
    op.drop_index("ix_riwayat_session_dibuat", table_name="riwayat_rekomendasi")
    op.drop_table("riwayat_rekomendasi")
