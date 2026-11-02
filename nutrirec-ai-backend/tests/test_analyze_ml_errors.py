import csv
import json

import pytest
import numpy as np

from scripts import analyze_ml_errors as analysis
from scripts import run_ml_experiment as exp
from test_run_ml_experiment import synthetic


def fixture_files(tmp_path):
    features = synthetic(tmp_path)
    fm, _, rows = exp.load_source(features)
    splits, diagnostics = exp.folds_for(rows)
    experiment = tmp_path / "experiment"; experiment.mkdir()
    assignments, predictions = [], []
    for fold, (_, test) in enumerate(splits, 1):
        for i in test:
            row = rows[i]
            meta = {key: row[key] for key in ("submission_uid", "response_id", "evaluation_group_id", "no_makanan_excel")}
            assignments.append({"fold": fold, **meta})
            predictions.append({"model": "Dummy", "fold": fold, **meta, "y_true": row["y"], "y_pred": "3", "prob_1": "0", "prob_2": "0", "prob_3": "1", "prob_4": "0", "kelas_tidak_ada_train": ";".join(map(str, diagnostics[fold-1]["train"]["kelas_tidak_tersedia"]))})
    exp.write_csv(experiment / "fold_assignments.csv", assignments, list(assignments[0]))
    exp.write_csv(experiment / "out_of_fold_predictions.csv", predictions, list(predictions[0]))
    (experiment / "fold_diagnostics.json").write_text(json.dumps(diagnostics))
    scores = exp.metrics(np.array([int(p["y_true"]) for p in predictions]), np.array([3] * len(predictions)), np.array([p["submission_uid"] for p in predictions]))
    (experiment / "metrics_summary.json").write_text(json.dumps({"Dummy": {"oof": scores}}))
    manifest = {"eksperimen_awal": True, "siap_produksi": False, "dataset_version": fm["dataset_version"], "run_id": fm["run_id"], "feature_version": fm["versi_aturan_fitur"], "config": {"model": {"Dummy": "most_frequent"}}, "masukan_sha256": {name: exp.sha(features / name) for name in ("manifest.json", "ml_feature_table.csv", "feature_schema.json", "evaluation_groups.csv")}, "output_sha256": {p.name: exp.sha(p) for p in experiment.iterdir()}}
    (experiment / "manifest.json").write_text(json.dumps(manifest))
    return experiment, features


def test_analisis_dan_dry_run(tmp_path):
    experiment, features = fixture_files(tmp_path); output = tmp_path / "analysis"
    args = ["--experiment-dir", str(experiment), "--features-dir", str(features), "--output-dir", str(output)]
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert analysis.main(args + ["--dry-run"]) == 0
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert analysis.main(args) == 0
    report = json.loads((output / "error_analysis_report.json").read_text())
    assert report["model"]["Dummy"]["penilaian"] == 20
    assert report["model"]["Dummy"]["kesalahan"] == 16
    assert sum(sum(x.values()) for x in report["model"]["Dummy"]["confusion_matrix"].values()) == 20
    old = (output / "manifest.json").read_bytes()
    assert analysis.main(args) != 0
    assert (output / "manifest.json").read_bytes() == old


def test_hash_dan_prediksi_duplikat_ditolak(tmp_path):
    experiment, features = fixture_files(tmp_path)
    path = experiment / "out_of_fold_predictions.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
    rows[1] = dict(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match="Hash"): analysis.load(experiment, features)
    manifest_path = experiment / "manifest.json"; m = json.loads(manifest_path.read_text()); m["output_sha256"][path.name] = analysis.digest(path); manifest_path.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="duplikat"): analysis.load(experiment, features)


def item(uid, true, pred, group="g1", fold="1", food="1"):
    return {"submission_uid": uid, "evaluation_group_id": group, "fold": fold,
            "no_makanan_excel": food, "response_id": uid, "y_true": str(true), "y_pred": str(pred),
            "selisih": pred - true, "error_absolut": abs(pred - true)}


def test_metrik_asimetris_nol_dan_uid():
    rows = [item("a", 1, 2, food="1"), item("a", 1, 1, food="2"), item("b", 2, 2, group="g2", fold="2")]
    score = analysis.metrik(rows)
    assert score["matrix"][0][1] == 1 and score["matrix"][1][0] == 0
    assert score["normalisasi"][0] == [0.5, 0.5, 0, 0]
    assert score["normalisasi"][2] == [None] * 4
    assert score["kelas"]["3"]["dapat_dievaluasi"] is False
    assert score["macro_f1"] == pytest.approx((2 / 3 + 2 / 3) / 4)
    assert score["accuracy"] == pytest.approx(2 / 3) and score["uid_accuracy"] == pytest.approx(0.75)
    assert score["uid"] == 2 and score["kelompok"] == 2 and score["fold"] == 2 and score["dukungan_sangat_terbatas"]
    assert score["salah_satu"] == 1 and score["terlalu_tinggi"] == 1


def test_paired_rekonsiliasi_dan_arah():
    rows = [item("a", 1, 1), item("b", 1, 2), item("c", 1, 1), item("d", 1, 4)]
    dummy_rows = [item("a", 1, 1), item("b", 1, 1), item("c", 1, 4), item("d", 1, 3)]
    dummy = {(r["submission_uid"], r["no_makanan_excel"]): r for r in dummy_rows}
    result = analysis.paired(rows, dummy)
    assert [result[k] for k in ("keduanya_benar", "hanya_model_benar", "hanya_dummy_benar", "keduanya_salah")] == [1, 1, 1, 1]
    assert result["accuracy_delta"] == 0 and result["mae_delta"] == pytest.approx(-0.25)
    score = analysis.metrik(rows)
    assert score["salah_satu"] == 1 and score["salah_dua_atau_lebih"] == 1 and score["terlalu_tinggi"] == 2


def test_delta_per_uid_tidak_sama_delta_per_baris():
    rows = [item("a", 1, 1, food="1"), item("a", 1, 1, food="2"), item("b", 1, 2)]
    dummy_rows = [item("a", 1, 2, food="1"), item("a", 1, 2, food="2"), item("b", 1, 1)]
    result = analysis.paired(rows, {(r["submission_uid"], r["no_makanan_excel"]): r for r in dummy_rows})
    assert result["accuracy_delta"] == pytest.approx(1 / 3)
    assert result["uid_accuracy_delta"] == 0


def test_metrik_sumber_tidak_cocok_ditolak(tmp_path):
    experiment, features = fixture_files(tmp_path)
    path = experiment / "metrics_summary.json"; value = json.loads(path.read_text()); value["Dummy"]["oof"]["accuracy"] = 0.99; path.write_text(json.dumps(value))
    manifest = experiment / "manifest.json"; data = json.loads(manifest.read_text()); data["output_sha256"][path.name] = analysis.digest(path); manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Metrik sumber"): analysis.load(experiment, features)


def test_keluaran_wajib_dan_markdown_aktual(tmp_path):
    experiment, features = fixture_files(tmp_path); output = tmp_path / "output"
    assert analysis.main(["--experiment-dir", str(experiment), "--features-dir", str(features), "--output-dir", str(output)]) == 0
    assert {"overall_metrics.json", "confusion_matrices.json", "subgroup_metrics.csv", "paired_vs_dummy.csv", "prediction_errors.csv", "error_analysis_report.md", "manifest.json"} <= {p.name for p in output.iterdir()}
    text = (output / "error_analysis_report.md").read_text()
    assert "| Dummy | 20 |" in text and "Confusion matrix" in text


@pytest.mark.parametrize("kind", ["hilang", "target", "fold", "metadata", "train_class"])
def test_prediksi_tidak_konsisten_ditolak(tmp_path, kind):
    experiment, features = fixture_files(tmp_path)
    path = experiment / "out_of_fold_predictions.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
    if kind == "hilang": rows.pop()
    if kind == "target": rows[0]["y_true"] = "4" if rows[0]["y_true"] != "4" else "1"
    if kind == "fold": rows[0]["fold"] = "99"
    if kind == "metadata": rows[0]["response_id"] = "salah"
    if kind == "train_class": rows[0]["kelas_tidak_ada_train"] = "1;2;3;4"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    mpath = experiment / "manifest.json"; m = json.loads(mpath.read_text()); m["output_sha256"][path.name] = analysis.digest(path); mpath.write_text(json.dumps(m))
    with pytest.raises(ValueError): analysis.load(experiment, features)


def test_contoh_deterministik_dan_rating_satu():
    common = {"model": "Dummy", "target_kalori": "Rendah", "prioritas": "Protein", "status_alergi": "False", "nama_makanan_dataset": "A", "kelas_tidak_ada_train": "1"}
    rows = [{**common, **item("b", 1, 4, food="2")}, {**common, **item("a", 1, 4, food="10")}, {**common, **item("a", 1, 4, food="1")}]
    first = analysis.detail(rows)
    second = analysis.detail(list(reversed(rows)))
    assert [(r["submission_uid"], r["no_makanan_excel"]) for r in first[4]["Dummy"]] == [(r["submission_uid"], r["no_makanan_excel"]) for r in second[4]["Dummy"]] == [("a", "1"), ("a", "10"), ("b", "2")]
    assert first[0]["Dummy"]["rating_1"]["train_tidak_tersedia"]["penilaian"] == 3
