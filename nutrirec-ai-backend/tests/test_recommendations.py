"""
tests/test_recommendations.py
Uji endpoint prototipe rekomendasi content-based
(POST /api/v1/recommendations/content-based).
"""

from decimal import Decimal

import pytest

from fastapi.testclient import TestClient
from fastapi import Response

from app.models.makanan import InformasiGizi
from app.models.referensi import PrioritasNutrisi

# ─── Helper seeder ────────────────────────────────────────────────────────────

def _buat_menu(
    db,
    id_makanan: int,
    nama: str,
    kalori: float,
    protein: float,
    karbohidrat: float,
    lemak: float,
    kelompok_kalori: str,
    allergen_ids: list[int] | None = None,
    status: str = "Terverifikasi",
) -> None:
    """Seeder menu makanan + informasi gizi + kandungan alergen."""
    from app.models.makanan import Makanan, InformasiGizi
    from app.models.alergen import KandunganAlergen

    db.add(
        Makanan(
            id_makanan=id_makanan,
            nama_makanan=nama,
            deskripsi_porsi=f"{kalori} kkal per porsi",
            berat_porsi_gram=None,
            sumber_data="https://nutrinusa.id/kalori/test",
            kelompok_kalori=kelompok_kalori,
            label_prioritas=None,
            versi_dataset="revisi-PD11-R1",
        )
    )
    db.add(
        InformasiGizi(
            id_makanan=id_makanan,
            kalori=Decimal(str(kalori)),
            karbohidrat=Decimal(str(karbohidrat)),
            lemak=Decimal(str(lemak)),
            protein=Decimal(str(protein)),
        )
    )
    for id_alergen in allergen_ids or []:
        db.add(
            KandunganAlergen(
                id_makanan=id_makanan,
                id_alergen=id_alergen,
                status_verifikasi=status,
                bahan_penyebab="bahan pengujian",
            )
        )
    db.flush()


def _kirim_permintaan(
    client: TestClient,
    target_kalori_id: int = 2,
    prioritas_id: int = 1,
    status_alergi: bool = False,
    alergen_ids: list[int] | None = None,
) -> Response:
    return client.post(
        "/api/v1/recommendations/content-based",
        json={
            "target_kalori_id": target_kalori_id,
            "prioritas_id": prioritas_id,
            "status_alergi": status_alergi,
            "alergen_ids": alergen_ids or [],
        },
    )


# ─── Struktur respons ──────────────────────────────────────────────────────────

def test_rekomendasi_content_based_struktur(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 450, 18.5, 62.4, 14.8, "Sedang")

    resp = _kirim_permintaan(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "prototipe"
    assert data["versi_aturan"] == "PD11-R1"
    assert data["jumlah_kandidat"] == len(data["kandidat"])
    assert len(data["kandidat"]) <= 3
    for item in data["kandidat"]:
        assert "id_makanan" in item
        assert "nama_makanan" in item
        assert "deskripsi_porsi" in item
        assert "kalori" in item
        assert "protein" in item
        assert "karbohidrat" in item
        assert "lemak" in item
        assert "skor_kalori" in item
        assert "skor_prioritas" in item
        assert "skor_content_based" in item


def test_rekomendasi_content_based_urut_skor_menurun(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 450, 30, 40, 10, "Sedang")
    _buat_menu(db_session, 102, "Nasi Ayam", 480, 28, 40, 16, "Sedang")

    resp = _kirim_permintaan(client)
    assert resp.status_code == 200
    data = resp.json()
    skor_list = [float(i["skor_content_based"]) for i in data["kandidat"]]
    assert skor_list == sorted(skor_list, reverse=True)


# ─── Skor kalori dan batas ─────────────────────────────────────────────────────

def test_rekomendasi_skor_kalori_batasan_300_dan_500(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 300, 30, 40, 10, "Sedang")   # tepat 300 → skor 1.0
    _buat_menu(db_session, 102, "Nasi Ayam", 500, 28, 40, 16, "Sedang") # tepat 500 → skor 1.0
    _buat_menu(db_session, 103, "Soto", 299, 30, 40, 10, "Sedang")     # Di luar rentang: skor menurun.

    resp = _kirim_permintaan(client, target_kalori_id=2)  # Sedang: 300–500
    assert resp.status_code == 200
    data = resp.json()
    items = {i["id_makanan"]: i for i in data["kandidat"]}
    assert 101 in items
    assert 102 in items
    assert 103 in items
    assert float(items[101]["skor_kalori"]) == 1.0
    assert float(items[102]["skor_kalori"]) == 1.0
    assert float(items[103]["skor_kalori"]) == pytest.approx(0.995)


def test_rekomendasi_skor_prioritas_seimbang(client: TestClient, db_session, seed_referensi):
    # Komposisi % energi: protein 0.15, karbohidrat 0.55, lemak 0.30 → skor 1.0
    _buat_menu(db_session, 105, "Makanan Seimbang", 400, 15, 55, 13.33, "Sedang")

    resp = _kirim_permintaan(client, prioritas_id=4)  # Seimbang
    assert resp.status_code == 200
    data = resp.json()
    items = {i["id_makanan"]: i for i in data["kandidat"]}
    assert 105 in items
    assert round(float(items[105]["skor_prioritas"]), 2) == 1.0


# ─── Alergi ───────────────────────────────────────────────────────────────────

def test_rekomendasi_alergi_menolak_data(
    client: TestClient, db_session, seed_referensi
):
    # Pengguna memilih alergi Telur (id=1).

    # 201: mengandung Telur dan belum diverifikasi → ditolak.
    _buat_menu(
        db_session, 201, "Menu Belum Terverifikasi",
        150, 10, 8, 8, "Rendah",
        [1], status="Belum diverifikasi",
    )

    # 202: tidak memiliki relasi alergen → ditolak.
    _buat_menu(
        db_session, 202, "Menu Tanpa Relasi",
        150, 10, 8, 8, "Rendah",
    )

    # 203: mengandung Kedelai terverifikasi, bukan Telur → lolos.
    _buat_menu(
        db_session, 203, "Menu Kedelai Terverifikasi",
        150, 10, 8, 8, "Rendah",
        [2], status="Terverifikasi",
    )

    # 204: mengandung Telur terverifikasi → ditolak.
    _buat_menu(
        db_session, 204, "Menu Tabrakan",
        150, 10, 8, 8, "Rendah",
        [1], status="Terverifikasi",
    )

    # 205: mengandung Kedelai, tetapi belum diverifikasi → ditolak.
    _buat_menu(
        db_session, 205, "Menu Kedelai Belum Diverifikasi",
        150, 10, 8, 8, "Rendah",
        [2], status="Belum diverifikasi",
    )

    resp = _kirim_permintaan(
        client,
        status_alergi=True,
        alergen_ids=[1],
    )

    assert resp.status_code == 200

    data = resp.json()
    ids = {item["id_makanan"] for item in data["kandidat"]}

    assert 203 in ids
    assert 201 not in ids
    assert 202 not in ids
    assert 204 not in ids
    assert 205 not in ids


# ─── Kandidat kosong vs kesalahan layanan ─────────────────────────────────────

def test_rekomendasi_kandidat_kosong(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 301, "Menu Tabrakan Seimbang", 150, 10, 8, 8, "Rendah", [1], status="Terverifikasi")

    resp = _kirim_permintaan(client, status_alergi=True, alergen_ids=[1])
    assert resp.status_code == 200
    data = resp.json()
    assert data["jumlah_kandidat"] == 0
    assert data["kandidat"] == []
    assert data["pesan_kosong"]


def test_rekomendasi_referensi_tidak_valid(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 450, 18.5, 62.4, 14.8, "Sedang")

    # ID target kalori tidak dikenal
    resp = _kirim_permintaan(client, target_kalori_id=9999)
    assert resp.status_code == 400

    # ID prioritas tidak dikenal
    resp = _kirim_permintaan(client, prioritas_id=9999)
    assert resp.status_code == 400

    # ID alergen tidak dikenal
    resp = _kirim_permintaan(client, status_alergi=True, alergen_ids=[9999])
    assert resp.status_code == 400


# ─── Konsistensi skor ──────────────────────────────────────────────────────────

def test_rekomendasi_cb_score_konsistensi(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 450, 30, 40, 10, "Sedang")

    resp = _kirim_permintaan(client)
    assert resp.status_code == 200
    data = resp.json()
    item = data["kandidat"][0]
    expected = 100.0 * (0.5 * float(item["skor_kalori"]) + 0.5 * float(item["skor_prioritas"]))
    assert float(item["skor_content_based"]) == pytest.approx(expected)

def test_rekomendasi_prioritas_menggunakan_ambang_gizi_tetap(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Menu Rendah Protein", 400, 10, 80, 5, "Sedang")

    resp = _kirim_permintaan(client, prioritas_id=1)
    assert resp.status_code == 200
    item = resp.json()["kandidat"][0]
    energi = 4 * 10 + 4 * 80 + 9 * 5
    proporsi_protein = 4 * 10 / energi
    expected_priority = proporsi_protein / 0.25

    assert float(item["skor_prioritas"]) == pytest.approx(expected_priority)
    assert float(item["skor_content_based"]) == pytest.approx(
        100 * (0.5 * item["skor_kalori"] + 0.5 * expected_priority)
    )

def test_rekomendasi_prioritas_tidak_berubah_saat_katalog_bertambah(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Menu Target", 400, 10, 80, 5, "Sedang")
    awal = _kirim_permintaan(client, prioritas_id=1).json()["kandidat"][0]

    _buat_menu(db_session, 102, "Menu Sangat Tinggi Protein", 400, 80, 10, 5, "Sedang")
    sesudah = _kirim_permintaan(client, prioritas_id=1).json()["kandidat"]
    target = next(item for item in sesudah if item["id_makanan"] == 101)

    assert float(target["skor_prioritas"]) == pytest.approx(awal["skor_prioritas"])
    assert float(target["skor_content_based"]) == pytest.approx(awal["skor_content_based"])

def test_rekomendasi_menolak_nutrisi_tidak_valid(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Menu Kalori Nol", 400, 0, 0, 0, "Sedang")
    _buat_menu(db_session, 102, "Menu Tanpa Data Gizi", 400, 10, 80, 5, "Sedang")
    db_session.delete(db_session.get(InformasiGizi, 102))
    db_session.flush()

    resp = _kirim_permintaan(client)

    assert resp.status_code == 200
    assert resp.json()["jumlah_kandidat"] == 0

def test_rekomendasi_prioritas_tanpa_ambang_referensi_ditolak(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 450, 18.5, 62.4, 14.8, "Sedang")
    prioritas = db_session.get(PrioritasNutrisi, 1)
    prioritas.min_persen_energi = None
    db_session.flush()

    resp = _kirim_permintaan(client, prioritas_id=1)

    assert resp.status_code == 400
    assert "Ambang prioritas" in resp.json()["detail"]

def test_rekomendasi_skor_sama_diurutkan_berdasarkan_id(
    client: TestClient, db_session, seed_referensi
):
    # Data gizi dibuat sama agar skor rekomendasinya sama.
    _buat_menu(db_session, 102, "Nasi Ayam", 400, 20, 50, 10, "Sedang")
    _buat_menu(db_session, 101, "Mie Ayam", 400, 20, 50, 10, "Sedang")

    resp = _kirim_permintaan(client)

    assert resp.status_code == 200

    kandidat = resp.json()["kandidat"]
    ids = [item["id_makanan"] for item in kandidat]

    assert ids == [101, 102]