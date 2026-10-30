"""Migrasi awal: buat semua tabel NutriRec AI.

Tabel yang dibuat:
  - target_kalori
  - prioritas_nutrisi
  - alergen
  - makanan
  - informasi_gizi
  - kandungan_alergen

Revision ID: 0001
Revises: —
Create Date: 2026-10-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── target_kalori ─────────────────────────────────────────────────────
    op.create_table(
        "target_kalori",
        sa.Column("id_target", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_kategori", sa.String(20), nullable=False, unique=True,
                  comment="'Rendah' | 'Sedang' | 'Tinggi'"),
        sa.Column("kalori_min", sa.Integer(), nullable=True,
                  comment="Batas bawah inklusif (kkal); NULL jika terbuka"),
        sa.Column("kalori_max", sa.Integer(), nullable=True,
                  comment="Batas atas eksklusif (kkal); NULL jika terbuka"),
        sa.Column("keterangan", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "nama_kategori IN ('Rendah', 'Sedang', 'Tinggi')",
            name="ck_target_nama_valid",
        ),
    )

    # ── prioritas_nutrisi ─────────────────────────────────────────────────
    op.create_table(
        "prioritas_nutrisi",
        sa.Column("id_prioritas", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_prioritas", sa.String(30), nullable=False, unique=True),
        sa.Column("jenis", sa.String(20), nullable=False),
        sa.Column("zat_gizi", sa.String(30), nullable=True),
        sa.Column("min_persen_energi", sa.Numeric(5, 4), nullable=True),
        sa.Column("acuan_protein", sa.Numeric(5, 4), nullable=True),
        sa.Column("acuan_karbo", sa.Numeric(5, 4), nullable=True),
        sa.Column("acuan_lemak", sa.Numeric(5, 4), nullable=True),
        sa.Column("keterangan", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "nama_prioritas IN ('Protein', 'Karbohidrat', 'Lemak', 'Seimbang')",
            name="ck_prioritas_nama_valid",
        ),
        sa.CheckConstraint(
            "jenis IN ('zat_gizi', 'seimbang')",
            name="ck_prioritas_jenis_valid",
        ),
    )

    # ── alergen ───────────────────────────────────────────────────────────
    op.create_table(
        "alergen",
        sa.Column("id_alergen", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_alergen", sa.String(100), nullable=False, unique=True),
        sa.Column("kata_kunci", sa.String(200), nullable=False),
    )

    # ── makanan ───────────────────────────────────────────────────────────
    op.create_table(
        "makanan",
        sa.Column("id_makanan", sa.Integer(), primary_key=True, autoincrement=True,
                  comment="ID stabil item menu"),
        sa.Column("nama_makanan", sa.String(200), nullable=False),
        sa.Column("deskripsi_porsi", sa.String(300), nullable=False),
        sa.Column("berat_porsi_gram", sa.Numeric(7, 2), nullable=True,
                  comment="Berat porsi gram; NULL jika tidak tersedia"),
        sa.Column("sumber_data", sa.String(500), nullable=False),
        sa.Column("kelompok_kalori", sa.String(10), nullable=True,
                  comment="Rendah | Sedang | Tinggi"),
        sa.Column("label_prioritas", sa.String(100), nullable=True),
        sa.Column("versi_dataset", sa.String(50), nullable=False,
                  server_default="revisi-PD11-R1"),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("diperbarui_pada", sa.DateTime(), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_makanan_nama", "makanan", ["nama_makanan"])
    op.create_index("ix_makanan_kelompok", "makanan", ["kelompok_kalori"])

    # ── informasi_gizi ────────────────────────────────────────────────────
    op.create_table(
        "informasi_gizi",
        sa.Column(
            "id_makanan",
            sa.Integer(),
            sa.ForeignKey("makanan.id_makanan", ondelete="CASCADE"),
            primary_key=True,
            comment="FK ke makanan; relasi 1-ke-1",
        ),
        sa.Column("kalori", sa.Numeric(8, 2), nullable=False,
                  comment="Energi per porsi (kkal)"),
        sa.Column("karbohidrat", sa.Numeric(8, 2), nullable=False,
                  comment="Karbohidrat (g)"),
        sa.Column("lemak", sa.Numeric(8, 2), nullable=False,
                  comment="Lemak (g)"),
        sa.Column("protein", sa.Numeric(8, 2), nullable=False,
                  comment="Protein (g)"),
        sa.CheckConstraint("kalori >= 0", name="ck_gizi_kalori_nonneg"),
        sa.CheckConstraint("karbohidrat >= 0", name="ck_gizi_karbo_nonneg"),
        sa.CheckConstraint("lemak >= 0", name="ck_gizi_lemak_nonneg"),
        sa.CheckConstraint("protein >= 0", name="ck_gizi_protein_nonneg"),
    )

    # ── kandungan_alergen ─────────────────────────────────────────────────
    op.create_table(
        "kandungan_alergen",
        sa.Column(
            "id_makanan",
            sa.Integer(),
            sa.ForeignKey("makanan.id_makanan", ondelete="CASCADE"),
            primary_key=True,
            comment="FK ke makanan",
        ),
        sa.Column(
            "id_alergen",
            sa.Integer(),
            sa.ForeignKey("alergen.id_alergen", ondelete="CASCADE"),
            primary_key=True,
            comment="FK ke alergen",
        ),
        sa.Column("status_verifikasi", sa.String(30), nullable=False,
                  server_default="Belum diverifikasi"),
        sa.Column("bahan_penyebab", sa.String(300), nullable=True),
        sa.Column("catatan_verifikasi", sa.Text(), nullable=True),
        sa.Column("dibuat_pada", sa.DateTime(), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint(
            "status_verifikasi IN ('Belum diverifikasi', 'Terverifikasi')",
            name="ck_kandungan_status_valid",
        ),
    )
    op.create_index("ix_kandungan_makanan", "kandungan_alergen", ["id_makanan"])
    op.create_index("ix_kandungan_alergen", "kandungan_alergen", ["id_alergen"])


def downgrade() -> None:
    op.drop_table("kandungan_alergen")
    op.drop_table("informasi_gizi")
    op.drop_index("ix_makanan_kelompok", table_name="makanan")
    op.drop_index("ix_makanan_nama", table_name="makanan")
    op.drop_table("makanan")
    op.drop_table("alergen")
    op.drop_table("prioritas_nutrisi")
    op.drop_table("target_kalori")

