"""
tests/test_personalisasi_schema.py
Uji validasi schema PermintaanPersonalisasi.

Test ini memvalidasi logika validasi Pydantic tanpa memerlukan database.
"""

import pytest
from pydantic import ValidationError

from app.schemas.personalisasi import PermintaanPersonalisasi


# ─── Kasus valid ──────────────────────────────────────────────────────────────

def test_valid_dengan_alergi():
    """Status alergi True dengan satu alergen valid."""
    p = PermintaanPersonalisasi(
        target_kalori_id=1,
        prioritas_id=1,
        status_alergi=True,
        alergen_ids=[1],
    )
    assert p.status_alergi is True
    assert p.alergen_ids == [1]


def test_valid_tanpa_alergi():
    """Status alergi False dengan daftar kosong valid."""
    p = PermintaanPersonalisasi(
        target_kalori_id=2,
        prioritas_id=4,
        status_alergi=False,
        alergen_ids=[],
    )
    assert p.status_alergi is False
    assert p.alergen_ids == []


def test_valid_deduplication_alergen():
    """ID alergen duplikat dihapus secara otomatis."""
    p = PermintaanPersonalisasi(
        target_kalori_id=1,
        prioritas_id=2,
        status_alergi=True,
        alergen_ids=[1, 2, 1, 3, 2],
    )
    assert p.alergen_ids == [1, 2, 3]


# ─── Kasus tidak valid ────────────────────────────────────────────────────────

def test_invalid_alergi_true_tanpa_alergen():
    """Status alergi True tapi daftar kosong harus ditolak (FR-04)."""
    with pytest.raises(ValidationError) as exc_info:
        PermintaanPersonalisasi(
            target_kalori_id=1,
            prioritas_id=1,
            status_alergi=True,
            alergen_ids=[],
        )
    errors = exc_info.value.errors()
    assert any("minimal satu alergen" in str(e) for e in errors)


def test_invalid_alergi_false_dengan_alergen():
    """Status alergi False tapi ada alergen harus ditolak (FR-04)."""
    with pytest.raises(ValidationError) as exc_info:
        PermintaanPersonalisasi(
            target_kalori_id=1,
            prioritas_id=1,
            status_alergi=False,
            alergen_ids=[1, 2],
        )
    errors = exc_info.value.errors()
    assert any("harus kosong" in str(e) for e in errors)


def test_invalid_target_kalori_id_nol():
    """ID target kalori harus > 0."""
    with pytest.raises(ValidationError):
        PermintaanPersonalisasi(
            target_kalori_id=0,
            prioritas_id=1,
            status_alergi=False,
            alergen_ids=[],
        )


def test_invalid_prioritas_id_negatif():
    """ID prioritas harus > 0."""
    with pytest.raises(ValidationError):
        PermintaanPersonalisasi(
            target_kalori_id=1,
            prioritas_id=-1,
            status_alergi=False,
            alergen_ids=[],
        )


def test_invalid_alergen_id_nol():
    """Setiap ID alergen harus > 0."""
    with pytest.raises(ValidationError):
        PermintaanPersonalisasi(
            target_kalori_id=1,
            prioritas_id=1,
            status_alergi=True,
            alergen_ids=[0],
        )

