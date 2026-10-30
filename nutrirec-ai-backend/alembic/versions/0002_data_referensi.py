"""Migrasi data referensi: isi tabel target_kalori, prioritas_nutrisi, dan alergen.

Data ini bersifat statis dan sesuai spesifikasi sistem (tidak dari Excel).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── target_kalori ─────────────────────────────────────────────────────
    # Rendah  : < 300 kkal  (kalori_min=NULL, kalori_max=300 eksklusif)
    # Sedang  : 300–500 kkal inklusif (kalori_min=300, kalori_max=500)
    # Tinggi  : > 500 kkal  (kalori_min=500 eksklusif, kalori_max=NULL)
    conn.execute(
        sa.text(
            """
            INSERT INTO target_kalori (nama_kategori, kalori_min, kalori_max, keterangan)
            VALUES
              ('Rendah', NULL, 300,
               'Kalori per porsi kurang dari 300 kkal'),
              ('Sedang', 300, 500,
               'Kalori per porsi 300 hingga 500 kkal (inklusif)'),
              ('Tinggi', 500, NULL,
               'Kalori per porsi lebih dari 500 kkal')
            """
        )
    )

    # ── prioritas_nutrisi ─────────────────────────────────────────────────
    # Parameter acuan Seimbang (15/55/30) adalah nilai awal eksperimen tim;
    # dapat diperbarui setelah evaluasi tanpa mengubah skema database.
    conn.execute(
        sa.text(
            """
            INSERT INTO prioritas_nutrisi
              (nama_prioritas, jenis, zat_gizi, min_persen_energi,
               acuan_protein, acuan_karbo, acuan_lemak, keterangan)
            VALUES
              ('Protein', 'zat_gizi', 'Protein', 0.25,
               NULL, NULL, NULL,
               'Prioritaskan makanan dengan proporsi energi dari protein tinggi'),
              ('Karbohidrat', 'zat_gizi', 'Karbohidrat', 0.50,
               NULL, NULL, NULL,
               'Prioritaskan makanan dengan proporsi energi dari karbohidrat tinggi'),
              ('Lemak', 'zat_gizi', 'Lemak', 0.35,
               NULL, NULL, NULL,
               'Prioritaskan makanan dengan proporsi energi dari lemak tinggi'),
              ('Seimbang', 'seimbang', NULL, NULL,
               0.15, 0.55, 0.30,
               'Makanan dengan komposisi energi mendekati 15% protein, 55% karbo, 30% lemak')
            """
        )
    )

    # ── alergen ───────────────────────────────────────────────────────────
    # 11 pilihan bahan sesuai spesifikasi FR-04 dan instrumen survei.
    # kata_kunci: kata yang dicari di kolom alergen_tercatat dataset.
    conn.execute(
        sa.text(
            """
            INSERT INTO alergen (nama_alergen, kata_kunci) VALUES
              ('Telur',          'telur'),
              ('Kedelai',        'kedelai'),
              ('Jagung',         'jagung'),
              ('Kelapa',         'kelapa'),
              ('Ayam',           'ayam'),
              ('Daging sapi',    'daging sapi'),
              ('Gandum',         'gandum'),
              ('Kacang-kacangan','kacang-kacangan'),
              ('Udang/seafood',  'udang/seafood'),
              ('Ikan',           'ikan'),
              ('Beras',          'beras')
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM alergen"))
    conn.execute(sa.text("DELETE FROM prioritas_nutrisi"))
    conn.execute(sa.text("DELETE FROM target_kalori"))

