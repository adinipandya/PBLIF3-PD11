"""
tests/test_prepare_survey.py
Uji skrip persiapan data survei NutriRec AI (scripts/prepare_survey.py).

Menggunakan data sintetis kecil; tidak memakai atau mengubah database aplikasi.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import prepare_survey as ps  # noqa: E402


# ─── Konstanta / helper sintetis ───────────────────────────────────────────────

KONFLIK_TANPA_ALLERGI = ps.PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN
KONFLIK_ALLERGI = ps.PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN
RATING_1_TANPA_ALLERGI = ps.PENANDA_RATING_1_TANPA_ALLERGI
KEMUNGKINAN_DUPLIKAT = ps.PENANDA_KEMUNGKINAN_DUPLIKAT
RATING_SERAGAM = ps.PENANDA_RATING_SERAGAM
PEMETAAN_BELUM = ps.PENANDA_PEMETAAN_MAKANAN_BELUM_KONFIRMASI


def _buat_row(
    source_row: int,
    target: str = "Rendah (< 300 kkal)",
    prioritas: str = "Protein tinggi",
    status_alergi: str = "Tidak ada alergi",
    alergen: str = "",
    ratings: dict | None = None,
) -> dict:
    row: dict = {
        "source_row": source_row,
        "Timestamp": None,
        "Berapa target kalori Anda untuk satu kali makan?": target,
        "Nutrisi apa yang paling Anda prioritaskan pada makanan?": prioritas,
        "Apakah Anda memiliki alergi terhadap makanan?": status_alergi,
        "Jika Anda memiliki alergi makanan, bahan makanan apa saja yang perlu dihindari?": alergen,
    }
    ratings = ratings or {}
    for key, value in ratings.items():
        row[key] = value
    return row


def _dataset_uji() -> dict:
    return {
        "Bihun Goreng Sayur": 1,
        "Capcay Goreng / Kuah (Ayam)": 20,
    }


# ─── Parsing rating ───────────────────────────────────────────────────────────

def test_parse_rating_valid():
    hasil = ps.parse_rating("3 = Sesuai (hampir sesuai target)")
    assert hasil["status"] == "valid"
    assert hasil["rating"] == 3
    assert hasil["label"] == "Sesuai (hampir sesuai target)"


def test_parse_rating_kosong():
    for nilai in (None, ""):
        hasil = ps.parse_rating(nilai)
        assert hasil["status"] == "kosong"
        assert hasil["rating"] is None


def test_parse_rating_tidak_valid():
    hasil = ps.parse_rating("5 = Tidak tahu")
    assert hasil["status"] == "tidak_valid"
    assert hasil["rating"] is None
    hasil = ps.parse_rating("bukan rating")
    assert hasil["status"] == "tidak_valid"


# ─── Parsing alergen ───────────────────────────────────────────────────────────

def test_parse_alergen_koma_dalam_tanda_kurung():
    ids, unknown = ps.parse_alergen("Kacang-kacangan (tauge, kacang tanah, buncis)")
    assert ids == [ps.ALLERGEN_KEYWORD_ID["kacang-kacangan"]]
    assert unknown == []


def test_parse_alergen_beberapa_dengan_koma():
    ids, unknown = ps.parse_alergen("Gandum, Udang/seafood")
    assert ids == [7, 9]
    assert unknown == []


# ─── Pemetaan profil & response_id ────────────────────────────────────────────

def test_response_id_format():
    assert ps.buat_response_id(2) == "R001"
    assert ps.buat_response_id(66) == "R065"


def test_pemetaan_profil_dalam_siapkan_data():
    rows = [_buat_row(2, target="Sedang (300-500 kkal)", prioritas="Karbohidrat tinggi")]
    responses, ratings, report = ps.siapkan_data(rows, _dataset_uji())
    assert responses[0]["target_kalori_id"] == 2
    assert responses[0]["prioritas_id"] == 2


# ─── Konflik status alergi ─────────────────────────────────────────────────────

def test_konflik_tanpa_alergi_dengan_pilihan():
    row = _buat_row(2, status_alergi="Tidak ada alergi", alergen="Ayam")
    responses, ratings, report = ps.siapkan_data([row], _dataset_uji())
    assert KONFLIK_TANPA_ALLERGI in (responses[0]["penanda"] or "").split(";")
    assert responses[0]["tahan_seluruh_kiriman"] is True


def test_konflik_alergi_dengan_pilihan():
    row = _buat_row(2, status_alergi="Ya, memiliki alergi")
    responses, ratings, report = ps.siapkan_data([row], _dataset_uji())
    assert KONFLIK_ALLERGI in (responses[0]["penanda"] or "").split(";")


# ─── Deteksi jawaban identik selain timestamp ──────────────────────────────────

def test_deteksi_jawaban_identik():
    baris1 = _buat_row(2, target="Sedang (300-500 kkal)", prioritas="Protein tinggi", status_alergi="Tidak ada alergi", alergen="", ratings={"1. Bihun Goreng Sayur": "3 = Sesuai (hampir sesuai target)"})
    baris1["source_row"] = 2
    baris2 = dict(baris1)
    baris2["source_row"] = 3
    kelompok = ps.deteksi_kelompok_jawaban_identik([baris1, baris2])
    assert kelompok == [["R001", "R002"]]


# ─── Transformasi ke format panjang ────────────────────────────────────────────

def test_transformasi_rating_long():
    rows = [_buat_row(2, target="Sedang (300-500 kkal)", prioritas="Protein tinggi", status_alergi="Tidak ada alergi", ratings={
        "1. Bihun Goreng Sayur": "3 = Sesuai (hampir sesuai target)",
        "2. Nasi Uduk": "2 = Tidak sesuai (agak jauh dari target)",
    })]
    responses, ratings, report = ps.siapkan_data(rows, _dataset_uji())
    assert len(ratings) == 2
    assert ratings[0]["response_id"] == "R001"
    assert ratings[0]["nama_makanan_survei"] == "1. Bihun Goreng Sayur"
    assert ratings[0]["rating"] == 3
    assert ratings[1]["rating"] == 2


# ─── Pemetaan makanan belum terkonfirmasi ───────────────────────────────────────

def test_pemetaan_makanan_belum_dikonfirmasi():
    row = _buat_row(2, ratings={"20. Capcay Kuah (Ayam)": "3 = Sesuai (hampir sesuai target)"})
    responses, ratings, report = ps.siapkan_data([row], _dataset_uji())
    assert "Capcay Kuah (Ayam)" in report["pemetaan_makanan_belum_dikonfirmasi"]
    assert ratings[0]["id_makanan"] == ""


# ─── Mode dry-run tidak menulis berkas ─────────────────────────────────────────

def test_mode_dry_run_tidak_menyimpan(tmp_path, monkeypatch):
    dataset_ids = {"Bihun Goreng Sayur": 1}
    monkeypatch.setattr(ps, "baca_survei", lambda p: ([], []))
    monkeypatch.setattr(ps, "baca_dataset", lambda p: (dataset_ids, []))

    keluaran = tmp_path / "dry_run"
    kode = ps.main(
        [
            "--file", "dummy.xlsx",
            "--foods", "dummy_dataset.xlsx",
            "--output-dir", str(keluaran),
            "--dry-run",
        ]
    )
    assert kode == 0
    assert not keluaran.exists()
