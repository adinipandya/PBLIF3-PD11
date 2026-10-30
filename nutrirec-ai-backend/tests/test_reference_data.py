"""
tests/test_reference_data.py
Uji endpoint GET /api/v1/reference-data.
"""

from fastapi.testclient import TestClient


def test_reference_data_struktur(client: TestClient, seed_referensi):
    """Endpoint mengembalikan tiga kunci utama."""
    resp = client.get("/api/v1/reference-data")
    assert resp.status_code == 200
    data = resp.json()
    assert "target_kalori" in data
    assert "prioritas_nutrisi" in data
    assert "alergen" in data


def test_reference_data_target_kalori(client: TestClient, seed_referensi):
    """Tiga pilihan target kalori tersedia."""
    resp = client.get("/api/v1/reference-data")
    assert resp.status_code == 200
    targets = resp.json()["target_kalori"]
    assert len(targets) == 3
    nama = [t["nama_kategori"] for t in targets]
    assert "Rendah" in nama
    assert "Sedang" in nama
    assert "Tinggi" in nama


def test_reference_data_prioritas_nutrisi(client: TestClient, seed_referensi):
    """Empat prioritas tersedia."""
    resp = client.get("/api/v1/reference-data")
    prioritas = resp.json()["prioritas_nutrisi"]
    assert len(prioritas) == 4
    nama = [p["nama_prioritas"] for p in prioritas]
    assert "Protein" in nama
    assert "Karbohidrat" in nama
    assert "Lemak" in nama
    assert "Seimbang" in nama


def test_reference_data_alergen(client: TestClient, seed_referensi):
    """Alergen tersedia sesuai yang di-seed."""
    resp = client.get("/api/v1/reference-data")
    alergen = resp.json()["alergen"]
    assert len(alergen) >= 1
    for a in alergen:
        assert "id_alergen" in a
        assert "nama_alergen" in a
        assert "kata_kunci" in a

