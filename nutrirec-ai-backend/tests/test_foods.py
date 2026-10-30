"""
tests/test_foods.py
Uji endpoint GET /api/v1/foods dan GET /api/v1/foods/{id}.
"""

from fastapi.testclient import TestClient


def test_list_foods_empty(client: TestClient, seed_referensi):
    """Tanpa data makanan, endpoint mengembalikan daftar kosong."""
    resp = client.get("/api/v1/foods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_foods_returns_items(client: TestClient, seed_makanan):
    """Dengan data seed, endpoint mengembalikan makanan yang benar."""
    resp = client.get("/api/v1/foods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    ids = [item["id_makanan"] for item in data["items"]]
    assert 3 in ids
    assert 5 in ids


def test_food_detail_found(client: TestClient, seed_makanan):
    """Detail makanan ditemukan dengan struktur yang benar."""
    resp = client.get("/api/v1/foods/3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id_makanan"] == 3
    assert data["nama_makanan"] == "Sup Tahu Telur"
    assert data["kelompok_kalori"] == "Rendah"

    # Cek informasi gizi
    assert data["informasi_gizi"] is not None
    assert float(data["informasi_gizi"]["kalori"]) == 150.0
    assert float(data["informasi_gizi"]["protein"]) == 10.0

    # Cek alergen (daftar tidak kosong, bukan berarti bebas alergen)
    assert len(data["alergen"]) == 2
    nama_alergen = [a["nama_alergen"] for a in data["alergen"]]
    assert "Telur" in nama_alergen
    assert "Kedelai" in nama_alergen
    # Semua status belum diverifikasi
    for a in data["alergen"]:
        assert a["status_verifikasi"] == "Belum diverifikasi"


def test_food_detail_not_found(client: TestClient, seed_makanan):
    """ID makanan yang tidak ada mengembalikan 404."""
    resp = client.get("/api/v1/foods/9999")
    assert resp.status_code == 404
    assert "tidak ditemukan" in resp.json()["detail"].lower()


def test_food_berat_porsi_nullable(client: TestClient, seed_makanan):
    """Sup Tahu Telur tidak memiliki berat porsi; harus null."""
    resp = client.get("/api/v1/foods/3")
    assert resp.status_code == 200
    assert resp.json()["berat_porsi_gram"] is None


def test_food_berat_porsi_ada(client: TestClient, seed_makanan):
    """Soto Ayam Bening memiliki berat 400 g."""
    resp = client.get("/api/v1/foods/5")
    assert resp.status_code == 200
    assert float(resp.json()["berat_porsi_gram"]) == 400.0

