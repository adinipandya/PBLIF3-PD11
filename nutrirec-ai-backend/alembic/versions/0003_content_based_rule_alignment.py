"""Align reference rows with catalogue min-max content-based scoring.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
    """
    UPDATE prioritas_nutrisi
    SET min_persen_energi = NULL,
        keterangan = CASE nama_prioritas
            WHEN 'Protein' THEN 'Mendukung kebutuhan protein'
            WHEN 'Karbohidrat' THEN 'Sumber tenaga harian'
            WHEN 'Lemak' THEN 'Pilihan prioritas lemak'
        END
    WHERE nama_prioritas IN ('Protein', 'Karbohidrat', 'Lemak')
    """
))
    conn.execute(sa.text(
    """
    UPDATE prioritas_nutrisi
    SET keterangan = 'Keseimbangan zat gizi'
    WHERE nama_prioritas = 'Seimbang'
    """
))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE prioritas_nutrisi SET min_persen_energi = 0.25, "
        "keterangan = 'Prioritaskan makanan dengan proporsi energi dari protein tinggi' "
        "WHERE nama_prioritas = 'Protein'"
    ))
    conn.execute(sa.text(
        "UPDATE prioritas_nutrisi SET min_persen_energi = 0.50, "
        "keterangan = 'Prioritaskan makanan dengan proporsi energi dari karbohidrat tinggi' "
        "WHERE nama_prioritas = 'Karbohidrat'"
    ))
    conn.execute(sa.text(
        "UPDATE prioritas_nutrisi SET min_persen_energi = 0.35, "
        "keterangan = 'Prioritaskan makanan dengan proporsi energi dari lemak tinggi' "
        "WHERE nama_prioritas = 'Lemak'"
    ))
    conn.execute(sa.text(
        "UPDATE prioritas_nutrisi "
        "SET keterangan = 'Makanan dengan komposisi energi mendekati 15% protein, 55% karbo, 30% lemak' "
        "WHERE nama_prioritas = 'Seimbang'"
    ))
