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
    # Rendah < 300; Sedang 300–500 inklusif; Tinggi > 500 kkal per porsi.
    # Bounds are display/reference data; scoring uses category formulas.
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
    # Parameter awal prototipe; 15/55/30 bukan rekomendasi medis individual.
    # Historical survey meanings and ratings are not rewritten by this seed.
    conn.execute(
        sa.text(
            """
            INSERT INTO prioritas_nutrisi
              (nama_prioritas, jenis, zat_gizi, min_persen_energi,
               acuan_protein, acuan_karbo, acuan_lemak, keterangan)
            VALUES
              ('Protein', 'zat_gizi', 'Protein', NULL,
               NULL, NULL, NULL,
               'Skor proporsi energi protein dinormalisasi min-max pada katalog valid'),
              ('Karbohidrat', 'zat_gizi', 'Karbohidrat', NULL,
               NULL, NULL, NULL,
               'Skor proporsi energi karbohidrat dinormalisasi min-max pada katalog valid'),
              ('Lemak', 'zat_gizi', 'Lemak', NULL,
               NULL, NULL, NULL,
               'Skor proporsi energi lemak dinormalisasi min-max pada katalog valid'),
              ('Seimbang', 'seimbang', NULL, NULL,
               0.15, 0.55, 0.30,
               'Acuan prototipe 15/55/30; bukan rekomendasi medis individual; rating survei lama bermakna berbeda')
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

