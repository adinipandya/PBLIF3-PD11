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
    from app.core.recommendation_rules import calorie_category

    db.add(
        Makanan(
            id_makanan=id_makanan,
            nama_makanan=nama,
            deskripsi_porsi=f"{kalori} kkal per porsi",
            berat_porsi_gram=None,
            sumber_data="https://nutrinusa.id/kalori/test",
            kelompok_kalori=calorie_category(kalori),
            label_prioritas=None,
            versi_dataset="fix-PD11-R1",
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
    # Default fixtures have known allergen data; pass [] to model missing relations.
    for id_alergen in [3] if allergen_ids is None else allergen_ids:
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
    assert data["versi_aturan"] == "PD11-R2"
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

def test_rekomendasi_skor_kalori_batasan_299_9_300_500_500_1(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Mie Ayam", 300, 30, 40, 10, "Sedang")   # tepat 300 → skor 1.0
    _buat_menu(db_session, 102, "Nasi Ayam", 500, 28, 40, 16, "Sedang") # tepat 500 → skor 1.0
    _buat_menu(db_session, 103, "Soto", 299, 30, 40, 10, "Rendah")
    _buat_menu(db_session, 104, "Batas Atas Tinggi", 500.1, 30, 40, 10, "Tinggi")
    _buat_menu(db_session, 105, "Batas Bawah Rendah", 299.9, 30, 40, 10, "Rendah")

    resp = _kirim_permintaan(client, target_kalori_id=2)  # Skor kategori Sedang: 300–500
    assert resp.status_code == 200
    data = resp.json()
    items = {i["id_makanan"]: i for i in data["kandidat"]}
    assert len(items) == 3
    assert float(items[101]["skor_kalori"]) == 1.0
    from app.core.recommendation_rules import calorie_score

    sed = [
        calorie_score(value, "Sedang")
        for value in (299, 299.9, 300, 500, 500.1)
    ]
    assert sed == pytest.approx([0.995, 0.9995, 1.0, 1.0, 0.9995])
    assert calorie_score(500, "Rendah") == pytest.approx(1 - 200 / 300)
    assert calorie_score(500, "Tinggi") == 1.0
    assert calorie_score(299, "Sedang") == pytest.approx(0.995)
    assert calorie_score(500.1, "Sedang") == pytest.approx(0.9995)
    assert calorie_score(299.9, "Sedang") == pytest.approx(0.9995)
    assert calorie_score(500, "Rendah") == pytest.approx(1 - 200 / 300)
    assert calorie_score(500, "Tinggi") == 1.0


def test_label_kategori_tunggal_di_titik_batas():
    from app.core.recommendation_rules import calorie_category

    assert calorie_category(299.9) == "Rendah"
    assert calorie_category(300) == "Sedang"
    assert calorie_category(500) == "Sedang"
    assert calorie_category(500.1) == "Tinggi"


def test_rekomendasi_skor_prioritas_seimbang(client: TestClient, db_session, seed_referensi):
    # Komposisi energi 15/55/30: acuan prototipe, bukan saran individual.
    _buat_menu(db_session, 105, "Makanan Seimbang", 400, 15, 55, 12, "Sedang")

    resp = _kirim_permintaan(client, prioritas_id=4)  # Seimbang
    assert resp.status_code == 200
    data = resp.json()
    items = {i["id_makanan"]: i for i in data["kandidat"]}
    assert 105 in items
    assert float(items[105]["skor_prioritas"]) == pytest.approx(0.9783505154639176)


# ─── Alergi ───────────────────────────────────────────────────────────────────

def test_rekomendasi_alergi_tunggal_menolak_data_tidak_aman(
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
        [],
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


def test_rekomendasi_tanpa_alergi_menolak_data_alergen_tidak_diketahui(
    client: TestClient, db_session, seed_referensi
):
    _buat_menu(
        db_session, 401, "Menu Terverifikasi",
        150, 10, 8, 8, "Rendah",
        [2], status="Terverifikasi",
    )
    _buat_menu(
        db_session, 402, "Menu Pending",
        150, 10, 8, 8, "Rendah",
        [2], status="Belum diverifikasi",
    )
    _buat_menu(
        db_session, 403, "Menu Tanpa Relasi",
        150, 10, 8, 8, "Rendah",
        [],
    )

    resp = _kirim_permintaan(client, status_alergi=False)

    assert resp.status_code == 200
    assert [item["id_makanan"] for item in resp.json()["kandidat"]] == [401]


def test_rekomendasi_alergi_multi_mengeluarkan_semua_id_pilihan(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 211, "Aman Bahan Lain", 350, 20, 40, 10, "Sedang", [3])
    _buat_menu(db_session, 212, "Mengandung Telur", 350, 20, 40, 10, "Sedang", [1])
    _buat_menu(db_session, 213, "Mengandung Kedelai", 350, 20, 40, 10, "Sedang", [2])

    resp = _kirim_permintaan(client, status_alergi=True, alergen_ids=[1, 2])

    assert resp.status_code == 200
    assert [item["id_makanan"] for item in resp.json()["kandidat"]] == [211]


def test_rekomendasi_alergi_invalid_status_dan_ids(client: TestClient, db_session, seed_referensi):
    assert _kirim_permintaan(client, status_alergi=True, alergen_ids=[]).status_code == 422
    assert _kirim_permintaan(client, status_alergi=False, alergen_ids=[1]).status_code == 422
    assert _kirim_permintaan(client, status_alergi=True, alergen_ids=[1, 1]).status_code == 422

# ─── Kandidat kosong vs kesalahan layanan ─────────────────────────────────────

def test_rekomendasi_kandidat_kosong(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 301, "Menu Tabrakan Seimbang", 150, 10, 8, 8, "Rendah", [1], status="Terverifikasi")

    resp = _kirim_permintaan(client, status_alergi=True, alergen_ids=[1])
    assert resp.status_code == 200
    data = resp.json()
    assert data["jumlah_kandidat"] == 0
    assert data["kandidat"] == []
    assert data["pesan_kosong"]


def test_db_failure_is_service_unavailable(client: TestClient, monkeypatch):
    from app.api.v1 import rekomendasi as recommendation_api
    from sqlalchemy.exc import OperationalError

    def fail_get(*args, **kwargs):
        raise OperationalError("SELECT", {}, RuntimeError("database down"))

    monkeypatch.setattr(recommendation_api, "filter_dan_rekomendasikan", fail_get)
    response = _kirim_permintaan(client)

    assert response.status_code == 503
    assert "sementara tidak tersedia" in response.json()["detail"]


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
    item = resp.json()["kandidat"][0]
    expected = 100.0 * (0.5 * float(item["skor_kalori"]) + 0.5 * float(item["skor_prioritas"]))
    assert float(item["skor_content_based"]) == pytest.approx(expected)
    assert 0 <= float(item["skor_content_based"]) <= 100

def test_rekomendasi_prioritas_normalisasi_min_max_katalog(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Rendah Protein", 400, 10, 80, 5, "Sedang")
    _buat_menu(db_session, 102, "Tinggi Protein", 400, 80, 10, 5, "Sedang")

    resp = _kirim_permintaan(client, prioritas_id=1)

    assert resp.status_code == 200
    items = {item["id_makanan"]: item for item in resp.json()["kandidat"]}
    assert float(items[101]["skor_prioritas"]) == 0.0
    assert float(items[102]["skor_prioritas"]) == 1.0


def test_rekomendasi_prioritas_normalisasi_memakai_katalog_sebelum_filter_alergi(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Aman Protein Rendah", 400, 10, 80, 5, "Sedang", [2])
    _buat_menu(db_session, 102, "Telur Protein Tinggi", 400, 80, 10, 5, "Sedang", [1])

    resp = _kirim_permintaan(client, prioritas_id=1, status_alergi=True, alergen_ids=[1])

    assert resp.status_code == 200
    items = resp.json()["kandidat"]
    assert [item["id_makanan"] for item in items] == [101]
    assert float(items[0]["skor_prioritas"]) == 0.0

def test_rekomendasi_menolak_nutrisi_tidak_valid(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Menu Energi Makro Nol", 400, 0, 0, 0, "Sedang")
    _buat_menu(db_session, 102, "Menu Satu-satunya Tanpa Data Gizi", 400, 10, 80, 5, "Sedang")
    db_session.delete(db_session.get(InformasiGizi, 102))
    db_session.flush()

    resp = _kirim_permintaan(client)

    assert resp.status_code == 200
    assert resp.json()["jumlah_kandidat"] == 0


def test_rekomendasi_katalog_satu_item_prioritas_netral(client: TestClient, db_session, seed_referensi):
    _buat_menu(db_session, 101, "Satu Menu", 400, 18, 50, 10, "Sedang")

    resp = _kirim_permintaan(client, prioritas_id=1)

    assert resp.status_code == 200
    item = resp.json()["kandidat"][0]
    assert float(item["skor_prioritas"]) == 0.5

def test_skor_prioritas_makanan_tunggal_tetap_netral_setelah_filter_alergi(
    client: TestClient, db_session, seed_referensi
):
    _buat_menu(db_session, 101, "Menu Telur", 400, 20, 40, 10, "Sedang", [1])
    _buat_menu(db_session, 102, "Menu Kedelai", 400, 10, 80, 5, "Sedang", [2])

    response = _kirim_permintaan(client, status_alergi=True, alergen_ids=[2])

    assert response.status_code == 200
    items = response.json()["kandidat"]
    assert [item["id_makanan"] for item in items] == [101]
    assert float(items[0]["skor_prioritas"]) == 1.0


def test_rekomendasi_prioritas_tie_break_id_naik(
    client: TestClient, db_session, seed_referensi
):
    for id_makanan in (102, 101, 103, 104):
        _buat_menu(db_session, id_makanan, f"Menu {id_makanan}", 400, 20, 40, 10, "Sedang")

    resp = _kirim_permintaan(client)

    assert resp.status_code == 200
    items = resp.json()["kandidat"]
    assert [item["id_makanan"] for item in items] == [101, 102, 103]
    assert len({item["skor_content_based"] for item in items}) == 1


def test_rekomendasi_satu_dua_dan_maksimal_tiga_kandidat(
    client: TestClient, db_session, seed_referensi
):
    expected_counts = (1, 2, 3)
    for index in range(4):
        _buat_menu(db_session, index + 1, f"Menu {index}", 400, 20, 40, 10, "Sedang")
        response = _kirim_permintaan(client)
        assert response.status_code == 200
        assert response.json()["jumlah_kandidat"] == expected_counts[min(index, 2)]


def test_rekomendasi_tidak_menampilkan_nasi_putih_dan_mengisi_top3_dari_kandidat_lain(
    client: TestClient, db_session, seed_referensi
):
    # ID 14 adalah Nasi Putih (Dijual Terpisah) pada Dataset Fix dan sengaja
    # diberi nilai protein tertinggi untuk memastikan pengecualian terjadi
    # sebelum pemeringkatan/Top 3.
    _buat_menu(db_session, 14, "Nasi Putih (Dijual Terpisah)", 400, 90, 10, 5, "Sedang")
    _buat_menu(db_session, 106, "Nasi Goreng", 400, 80, 10, 5, "Sedang")
    _buat_menu(db_session, 107, "Nasi Uduk", 400, 70, 10, 5, "Sedang")
    _buat_menu(db_session, 108, "Ayam Panggang", 400, 60, 10, 5, "Sedang")

    response = _kirim_permintaan(client)

    assert response.status_code == 200
    items = response.json()["kandidat"]
    assert [item["id_makanan"] for item in items] == [106, 107, 108]
    assert all(item["nama_makanan"] != "Nasi Putih (Dijual Terpisah)" for item in items)
    assert any(item["nama_makanan"] == "Nasi Goreng" for item in items)
    assert len(items) == 3


def test_rekomendasi_skor_sama_diurutkan_berdasarkan_id(
    client: TestClient, db_session, seed_referensi
):
    _buat_menu(db_session, 102, "Nasi Ayam", 400, 20, 50, 10, "Sedang")
    _buat_menu(db_session, 101, "Mie Ayam", 400, 20, 50, 10, "Sedang")

    resp = _kirim_permintaan(client)

    assert resp.status_code == 200
    kandidat = resp.json()["kandidat"]
    ids = [item["id_makanan"] for item in kandidat]

    assert ids == [101, 102]
