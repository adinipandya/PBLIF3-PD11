import csv
import json
from pathlib import Path

import pytest

from scripts import demo_ml_exploratory as demo
from scripts import train_ml_exploratory as trainer
from app.services.makanan_service import filter_dan_rekomendasikan, urutkan_katalog_kandidat

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "data/experiments/survey-v001/ml-eval-exploratory-001"
SPLIT = ROOT / "data/experiments/survey-v001/features-exploratory-split-002"
FOODS = ROOT / "data/Dataset_makanan_revisi.xlsx"


def test_stored_predictions_and_read_only_demo(monkeypatch):
    _, _, _, test_rows, _ = trainer.validate_split(SPLIT)
    _, model_path = demo.validate_artifacts(EXPERIMENT, "Random Forest")
    model = demo.joblib.load(model_path)
    feature_vectors, _ = trainer.xy(test_rows)
    predictions = model.predict(feature_vectors)
    predicted_by_key = {(r["submission_uid"], int(r["no_makanan_excel"])): int(p) for r, p in zip(test_rows, predictions)}
    with (EXPERIMENT / "test_predictions.csv").open(encoding="utf-8-sig", newline="") as stream:
        stored = [row for row in csv.DictReader(stream) if row["model"] == "Random Forest"]
    assert { (row["submission_uid"], int(row["no_makanan_excel"])): int(row["y_pred"]) for row in stored } == predicted_by_key
    # Fail if inference attempts to fit any newly loaded pipeline.
    from sklearn.pipeline import Pipeline
    monkeypatch.setattr(Pipeline, "fit", lambda *a, **k: pytest.fail("inference must not fit"))
    result = demo.infer(EXPERIMENT, FOODS, "Random Forest", "Sedang", "Protein", "tidak", [])
    assert result["mode"] == "demo_model_eksploratif"
    assert result["status"] == "kosong"
    assert result["rekomendasi_demo_model"] == []


def test_cb_public_contract_remains_top3_and_all_candidate_helper_returns_full_ranking(db_session, seed_referensi):
    from tests.test_recommendations import _buat_menu
    for food_id in range(101, 106):
        _buat_menu(db_session, food_id, f"Menu {food_id}", 400, 20 + food_id % 3, 40, 10, "Sedang")
    request = type("Req", (), {"target_kalori_id": 2, "prioritas_id": 1, "status_alergi": False, "alergen_ids": []})()
    all_rows = urutkan_katalog_kandidat(db_session, request)
    top3 = filter_dan_rekomendasikan(db_session, request)
    assert len(all_rows) == 5
    assert len(top3) == 3
    assert all(set(row) == {"makanan", "proporsi_energi", "skor_kalori", "skor_prioritas", "skor_content_based"} for row in all_rows)
    assert [r["makanan"].id_makanan for r in top3] == [r["makanan"].id_makanan for r in all_rows[:3]]

def test_hybrid_alpha_extremes_filter_same_pool_and_seimbang_guard(monkeypatch):
    verified_records = [
        {
            "id": index,
            "name": f"Menu uji {index}",
            "calories": 350 + index * 10,
            "protein": 15 + index,
            "carbs": 45 - index,
            "fat": 10,
            "allergens": "telur",
            "allergen_status": "Terverifikasi",
            "portion": "1 porsi",
        }
        for index in range(1, 4)
    ]
    monkeypatch.setattr(
        demo,
        "load_catalog",
        lambda _dataset: (verified_records, "verified-test-catalog"),
    )
    base = (EXPERIMENT, FOODS, "Random Forest", "Sedang", "Protein", "tidak", [])
    ml_only = demo.infer_hybrid(*base, alpha=0.0)
    cb_only = demo.infer_hybrid(*base, alpha=1.0)
    mid = demo.infer_hybrid(*base, alpha=0.5)
    assert [x["id_makanan"] for x in ml_only["rekomendasi_demo"]] == [x["id_makanan"] for x in ml_only["top3_ml"]]
    assert [x["id_makanan"] for x in cb_only["rekomendasi_demo"]] == [x["id_makanan"] for x in cb_only["top3_cb"]]
    for result in (ml_only, cb_only, mid):
        assert result["jumlah_kandidat_setelah_filter_alergi"] == len(verified_records)
        assert {x["id_makanan"] for x in result["top3_cb"]} <= {x["id_makanan"] for x in result["rekomendasi_demo"]} | {x["id_makanan"] for x in result["top3_cb"]}
    for item in mid["rekomendasi_demo"]:
        assert item["S_hybrid"] == pytest.approx(0.5 * item["S_CB"] + 0.5 * item["S_ML"])
    for allergen_ids in ([1], [1, 2]):
        result = demo.infer_hybrid(EXPERIMENT, FOODS, "Random Forest", "Sedang", "Protein", "memiliki", list(allergen_ids), 0.0)
        assert result["status"] == "kosong"
        assert result["jumlah_kandidat_setelah_filter_alergi"] == 0
        assert result["rekomendasi_demo"] == []
    balanced = demo.infer_hybrid(EXPERIMENT, FOODS, "Random Forest", "Sedang", "Seimbang", "tidak", [], 0.5)
    assert balanced["dukungan_cb_seimbang"] is False
    assert balanced["top3_cb"] == []
    assert all(item["S_CB"] is None and item["S_hybrid"] is None for item in balanced["rekomendasi_demo"])
    unsupported_allergy = demo.infer_hybrid(EXPERIMENT, FOODS, "Random Forest", "Sedang", "Seimbang", "memiliki", [1], 0.5)
    assert unsupported_allergy["status"] == "kosong"
    assert unsupported_allergy["jumlah_kandidat_setelah_filter_alergi"] == 0
    assert unsupported_allergy["rekomendasi_demo"] == []

def test_input_and_schema_validation():
    with pytest.raises(ValueError, match="Pilih minimal"):
        demo.input_features("Rendah", "Protein", "memiliki", [], 300, 10, 20, 5)
    with pytest.raises(ValueError, match="harus kosong"):
        demo.input_features("Rendah", "Protein", "tidak", [1], 300, 10, 20, 5)
    with pytest.raises(ValueError, match="duplikat"):
        demo.input_features("Rendah", "Protein", "memiliki", [1, 1], 300, 10, 20, 5)
    with pytest.raises(ValueError, match="finite"):
        demo.parse_number(float("inf"), "Kalori")


def test_analysis_counts_and_rf_class_two_errors():
    _, report = __import__("scripts.analyze_ml_exploratory_errors", fromlist=["analyze"]).analyze(EXPERIMENT)
    assert report["random_forest_true_class_2"]["rows"] == 50
    assert report["random_forest_true_class_2"]["predicted_as"] == {"1": 0, "2": 0, "3": 48, "4": 2}
    assert report["model_summaries"]["Dummy"]["prediction_counts"] == {"1": 0, "2": 0, "3": 222, "4": 0}
