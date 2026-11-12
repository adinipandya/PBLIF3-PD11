"""Add nullable audit fields to allergen relations.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kandungan_alergen",
        sa.Column("sumber_bukti", sa.Text(), nullable=True),
    )
    op.add_column(
        "kandungan_alergen",
        sa.Column("waktu_verifikasi", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "kandungan_alergen",
        sa.Column("id_pengelola", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    conn = op.get_bind()
    populated = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM kandungan_alergen "
            "WHERE sumber_bukti IS NOT NULL "
            "OR waktu_verifikasi IS NOT NULL "
            "OR id_pengelola IS NOT NULL"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "Downgrade dibatalkan agar metadata bukti verifikasi tidak terhapus."
        )
    op.drop_column("kandungan_alergen", "id_pengelola")
    op.drop_column("kandungan_alergen", "waktu_verifikasi")
    op.drop_column("kandungan_alergen", "sumber_bukti")
