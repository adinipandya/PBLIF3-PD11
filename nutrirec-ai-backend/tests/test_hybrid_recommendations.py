from types import SimpleNamespace

import numpy as np

from app.models.alergen import KandunganAlergen
from app.services import hybrid_service
from tests.test_recommendations import _buat_menu


class StubPipeline:
    named_steps = {"model": SimpleNamespace(classes_=np.array([1, 2, 3, 4]))}

    def predict(self, matrix):
        return np.full(len(matrix), 3)

    def predict_proba(self, matrix):
        return np.tile([0.0, 0.0, 1.0, 0.0], (len(matrix), 1))


def _seed_hybrid_foods(db):
    for food_id, protein in zip(range(101, 106), (24, 22, 20, 18, 16)):
        _buat_menu(db, food_id, f"Menu {food_id}", 400, protein, 40, 10, "Sedang")
        db.add(KandunganAlergen(
            id_makanan=food_id,
            id_alergen=1 if food_id == 101 else 2,
            status_verifikasi="Terverifikasi",
            bahan_penyebab="bahan uji",
        ))
    db.flush()


def _patch_model(monkeypatch):
    monkeypatch.setattr(
        hybrid_service,
        "_load_saved_model",
        lambda: ({"source_run_id": "pd11-r2-cleanup-003"}, StubPipeline()),
    )


def _payload(status_alergi=False, alergen_ids=None):
    return {
        "target_kalori_id": 2,
        "prioritas_id": 1,
        "status_alergi": status_alergi,
        "alergen_ids": alergen_ids or [],
    }


def test_hybrid_endpoint_returns_hybrid_score_and_ranks_top_three(
    client, db_session, seed_referensi, monkeypatch
):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)

    response = client.post("/api/v1/recommendations/hybrid", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "hybrid_eksploratif"
    assert body["jumlah_kandidat"] == 3
    assert len(body["kandidat"]) == 3
    assert all("skor_hybrid" in item and "skor_content_based" not in item for item in body["kandidat"])
    scores = [item["skor_hybrid"] for item in body["kandidat"]]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_excludes_nasi_putih_but_keeps_other_rice_menus_and_top_three(
    client, db_session, seed_referensi, monkeypatch
):
    _patch_model(monkeypatch)
    _buat_menu(db_session, 14, "Nasi Putih (Dijual Terpisah)", 400, 90, 10, 5, "Sedang")
    _buat_menu(db_session, 106, "Nasi Goreng", 400, 80, 10, 5, "Sedang")
    _buat_menu(db_session, 107, "Nasi Uduk", 400, 70, 10, 5, "Sedang")
    _buat_menu(db_session, 108, "Ayam Panggang", 400, 60, 10, 5, "Sedang")

    response = client.post("/api/v1/recommendations/hybrid", json=_payload())

    assert response.status_code == 200
    items = response.json()["kandidat"]
    assert [item["id_makanan"] for item in items] == [106, 107, 108]
    assert all(item["nama_makanan"] != "Nasi Putih (Dijual Terpisah)" for item in items)
    assert any(item["nama_makanan"] == "Nasi Goreng" for item in items)
    assert len(items) == 3


def test_hybrid_allergy_filter_excludes_selected_food(client, db_session, seed_referensi, monkeypatch):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)

    response = client.post(
        "/api/v1/recommendations/hybrid",
        json=_payload(status_alergi=True, alergen_ids=[1]),
    )

    assert response.status_code == 200
    assert all(item["id_makanan"] != 101 for item in response.json()["kandidat"])


def test_hybrid_returns_successful_empty_result_after_allergen_filter(
    client, db_session, seed_referensi, monkeypatch
):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)

    response = client.post(
        "/api/v1/recommendations/hybrid",
        json=_payload(status_alergi=True, alergen_ids=[1, 2]),
    )

    assert response.status_code == 200
    assert response.json()["jumlah_kandidat"] == 0
    assert response.json()["kandidat"] == []
    assert response.json()["pesan_kosong"]


def test_hybrid_rejects_legacy_seimbang_blend(client, db_session, seed_referensi, monkeypatch):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)
    request = _payload()
    request["prioritas_id"] = 4

    response = client.post("/api/v1/recommendations/hybrid", json=request)

    assert response.status_code == 422
