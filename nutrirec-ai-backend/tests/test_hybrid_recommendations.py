from types import SimpleNamespace

import numpy as np
import pytest

from app.models.alergen import KandunganAlergen
from app.services import hybrid_service
from tests.test_recommendations import _buat_menu


class StubPipeline:
    named_steps = {"model": SimpleNamespace(classes_=np.array([1, 2, 3, 4]))}

    def predict(self, matrix):
        self.last_matrix = matrix.copy()
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
    model = StubPipeline()
    monkeypatch.setattr(
        hybrid_service,
        "_load_saved_model",
        lambda: ({"source_run_id": "pd11-r2-cleanup-003"}, model),
    )
    return model


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


def test_hybrid_seimbang_uses_model_legacy_category_and_returns_scores_0_to_100(
    client, db_session, seed_referensi, monkeypatch
):
    _seed_hybrid_foods(db_session)
    model = _patch_model(monkeypatch)
    request = _payload()
    request["prioritas_id"] = 4

    response = client.post("/api/v1/recommendations/hybrid", json=request)

    assert response.status_code == 200
    assert model.last_matrix[0, 1] == "Seimbang (tidak ada prioritas khusus)"
    scores = [item["skor_hybrid"] for item in response.json()["kandidat"]]
    assert scores
    assert all(0 <= score <= 100 for score in scores)


def test_saved_random_forest_was_fitted_with_seimbang_and_predicts_it():
    from scripts.demo_ml_exploratory import input_features
    from scripts.prepare_ml_features import FEATURES

    _, model = hybrid_service._load_saved_model()
    legacy_category = "Seimbang (tidak ada prioritas khusus)"
    fitted_categories = model.named_steps["preprocess"].named_transformers_["categorical"].named_steps["encoder"].categories_[1]
    features = input_features("Sedang", "Seimbang", "tidak", [], 400, 20, 35, 10)
    matrix = np.asarray([[features[name] for name in FEATURES]], dtype=object)
    probabilities = hybrid_service.class_probabilities(model, matrix)

    assert legacy_category in fitted_categories
    assert model.predict(matrix)[0] in (1, 2, 3, 4)
    assert probabilities.shape == (1, 4)
    assert probabilities[0].sum() == pytest.approx(1.0)


def test_hybrid_seimbang_content_component_ignores_macro_composition(
    db_session, seed_referensi
):
    from app.services.makanan_service import _baca_nutrisi, get_makanan_detail, hitung_skor_katalog

    _buat_menu(db_session, 201, "Makro A", 400, 30, 20, 5, "Sedang")
    _buat_menu(db_session, 202, "Makro B", 400, 5, 60, 10, "Sedang")
    menu = [get_makanan_detail(db_session, food_id) for food_id in (201, 202)]
    valid = [(food, *_baca_nutrisi(food)) for food in menu]
    legacy_cb, _, _ = hitung_skor_katalog(valid, "Sedang", "Seimbang")

    # Macro composition changes the legacy CB value, but hybrid Seimbang ignores it.
    legacy_scores = [legacy_cb[food.id_makanan]["skor_content_based"] for food in menu]
    hybrid_scores = [
        hybrid_service._hybrid_content_score(legacy_cb[food.id_makanan], "Seimbang")
        for food in menu
    ]

    assert legacy_scores[0] != legacy_scores[1]
    assert hybrid_scores == [100.0, 100.0]
    assert hybrid_service._hybrid_content_score(legacy_cb[201], "Protein") == legacy_scores[0]


def test_hybrid_seimbang_kept_allergen_filter(client, db_session, seed_referensi, monkeypatch):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)
    request = _payload(status_alergi=True, alergen_ids=[1])
    request["prioritas_id"] = 4

    response = client.post("/api/v1/recommendations/hybrid", json=request)

    assert response.status_code == 200
    assert all(item["id_makanan"] != 101 for item in response.json()["kandidat"])


def test_hybrid_keeps_nutrient_priority_categories(client, db_session, seed_referensi, monkeypatch):
    _seed_hybrid_foods(db_session)
    _patch_model(monkeypatch)

    for priority_id in (1, 2, 3):
        request = _payload()
        request["prioritas_id"] = priority_id
        response = client.post("/api/v1/recommendations/hybrid", json=request)
        assert response.status_code == 200
        assert response.json()["jumlah_kandidat"] == 3
