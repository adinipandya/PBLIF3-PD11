"""Pengujian endpoint statistik kualitas katalog makanan."""


def test_statistik_katalog_kosong(client, seed_referensi):
    response = client.get("/api/v1/foods/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data["total_makanan"] == 0
    assert data["makanan_dengan_informasi_gizi"] == 0
    assert data["makanan_tanpa_informasi_gizi"] == 0
    assert data["kelompok_kalori"] == {}
    assert data["data_alergen"]["total_relasi"] == 0


def test_statistik_katalog_menghitung_kelengkapan_dan_verifikasi(
    client, seed_makanan
):
    response = client.get("/api/v1/foods/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data["total_makanan"] == 2
    assert data["makanan_dengan_informasi_gizi"] == 2
    assert data["makanan_tanpa_informasi_gizi"] == 0
    assert data["kelompok_kalori"] == {"Rendah": 2}
    assert data["data_alergen"]["total_relasi"] == 3
    assert data["data_alergen"]["status_verifikasi"] == {
        "Belum diverifikasi": 3
    }
    assert "tidak berarti" in data["data_alergen"]["catatan"]
