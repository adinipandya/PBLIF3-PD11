import csv
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import run_ml_experiment as exp


def synthetic(tmp_path):
    folder = tmp_path / "features"; folder.mkdir()
    schema = {"fitur_diizinkan": exp.FEATURES, "metadata_bukan_fitur": exp.METADATA, "target": {"y": "rating"}, "kategori": {"target_kalori": ["Rendah", "Sedang", "Tinggi"], "prioritas": ["Protein", "Lemak"]}}
    (folder / "feature_schema.json").write_text(json.dumps(schema))
    rows, groups = [], []
    labels = {"1": "Sangat tidak sesuai (karena mengandung bahan yang membuat saya alergi)", "2": "Tidak sesuai (agak jauh dari target)", "3": "Sesuai (hampir sesuai target)", "4": "Sangat sesuai (sesuai target)"}
    for i in range(10):
        uid, gid = f"u{i}", f"g{i // 2}"
        groups.append({"submission_uid": uid, "evaluation_group_id": gid, "alasan": "uji"})
        for food in (1, 2):
            y = str(i % 4 + 1)
            row = {k: "0" for k in exp.FEATURES}
            row.update(target_kalori="Rendah", prioritas="Protein", status_alergi="False", kalori_kkal="10", protein_g="1", karbohidrat_g="2", lemak_g="0")
            row.update({k: "x" for k in exp.METADATA})
            row.update(y=y, response_id=f"R{i}", submission_uid=uid, evaluation_group_id=gid, no_makanan_excel=str(food), dataset_version="d1", rating_asli=f"{y} = {labels[y]}")
            rows.append(row)
    def write(name, data):
        with (folder / name).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    write("ml_feature_table.csv", rows); write("evaluation_groups.csv", groups)
    (folder / "evaluation_feasibility_report.json").write_text("{}")
    (folder / "experiment_plan.md").write_text("plan")
    manifest = {"status": "fitur_eksperimen", "siap_training": False, "jumlah_baris": len(rows), "dataset_version": "d1", "run_id": "r1", "versi_aturan_fitur": "v1", "output_sha256": {name: exp.sha(folder / name) for name in exp.REQUIRED_OUTPUTS}}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def test_boolean_dan_kelompok_stabil(tmp_path):
    folder = synthetic(tmp_path)
    _, _, rows = exp.load_source(folder)
    assert exp.parse_bool("False") == 0 and exp.parse_bool("True") == 1
    with pytest.raises(ValueError): exp.parse_bool("false")
    a, diag = exp.folds_for(rows)
    b, _ = exp.folds_for(sorted(reversed(rows), key=lambda r: (r["evaluation_group_id"], r["submission_uid"], int(r["no_makanan_excel"]))))
    assert [list(t) for _, t in a] == [list(t) for _, t in b]
    assert all(d["train"]["kelompok"] == 4 and d["test"]["kelompok"] == 1 for d in diag)


def test_metrik_kelas_tetap_dan_probabilitas():
    y = np.array([2, 2, 3]); pred = np.array([2, 3, 3]); uids = np.array(["a", "a", "b"])
    result = exp.metrics(y, pred, uids)
    assert len(result["confusion_matrix"]) == 4
    assert result["per_kelas"]["1"]["dapat_dievaluasi"] is False
    assert result["macro_f1"] < 0.5
    class Estimator: classes_ = np.array([2, 4])
    class Model:
        named_steps = {"model": Estimator()}
        def predict_proba(self, X): return np.array([[0.25, 0.75]])
    assert exp.probabilities(Model(), [1]).tolist() == [[0, 0.25, 0, 0.75]]


def test_transformer_belajar_dari_train_saja():
    model = exp.pipeline("Decision Tree", 42)
    row = ["Rendah", "Protein"] + [0] * 12 + [10, 1, 2, 3]
    testrow = list(row); testrow[0] = "Kategori hanya test"
    model.fit(np.array([row, row], dtype=object), [2, 3])
    model.predict(np.array([testrow], dtype=object))
    categories = model.named_steps["preprocess"].named_transformers_["kategori"].categories_[0]
    assert "Kategori hanya test" not in categories


def test_dry_run_tidak_fit_dan_hash_ditolak(tmp_path, monkeypatch):
    folder = synthetic(tmp_path); out = tmp_path / "out"
    monkeypatch.setattr(exp, "pipeline", lambda *a: pytest.fail("dry-run tidak boleh fit"))
    args = ["--features-dir", str(folder), "--output-dir", str(out), "--dry-run"]
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert exp.main(args) == 0
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with (folder / "ml_feature_table.csv").open("a") as f: f.write("ubah")
    assert exp.main(args) != 0 and not out.exists()


def test_allowlist_menolak_target(tmp_path):
    folder = synthetic(tmp_path)
    path = folder / "feature_schema.json"; schema = json.loads(path.read_text()); schema["fitur_diizinkan"].append("y"); path.write_text(json.dumps(schema))
    path = folder / "manifest.json"; manifest = json.loads(path.read_text()); manifest["output_sha256"]["feature_schema.json"] = exp.sha(folder / "feature_schema.json"); path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Allowlist"): exp.load_source(folder)


def test_oof_semua_baris_dan_tidak_menimpa(tmp_path):
    folder = synthetic(tmp_path); out = tmp_path / "out"
    args = ["--features-dir", str(folder), "--output-dir", str(out)]
    assert exp.main(args) == 0
    with (out / "out_of_fold_predictions.csv").open(encoding="utf-8-sig") as f: rows = list(csv.DictReader(f))
    assert len(rows) == 20 * 4
    assert len({(r["model"], r["submission_uid"], r["no_makanan_excel"]) for r in rows}) == 80
    before = (out / "manifest.json").read_bytes()
    assert exp.main(args) != 0 and (out / "manifest.json").read_bytes() == before
