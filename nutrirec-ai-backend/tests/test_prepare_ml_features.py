import csv
import json

import pytest
from openpyxl import Workbook, load_workbook

from scripts import prepare_ml_features as ml
from scripts import process_survey_version as pv
from test_process_survey_version import project


def foods(path, records):
    wb = Workbook(); ws = wb.active; ws.title = "Dataset"
    ws.append(["NO", "NAMA MAKANAN", "KALORI (kkal)", "PROTEIN (g)", "KARBO (g)", "LEMAK (g)", "PORSI"])
    for record in records: ws.append(record)
    wb.save(path)


@pytest.mark.parametrize("value", [None, -1, "NaN", float("inf"), float("nan")])
def test_nutrisi_tidak_valid_ditolak(tmp_path, value):
    path = tmp_path / "foods.xlsx"; foods(path, [[1, "A", value, 1, 1, 1, "1 porsi"]])
    with pytest.raises(ValueError, match="tidak valid"): ml.foods_data(path)


def test_nol_dan_nama_duplikat(tmp_path):
    path = tmp_path / "foods.xlsx"; foods(path, [[1, "A", 0, 0, 0, 0, "1 porsi"]])
    assert ml.foods_data(path)["a"]["nutrisi"] == [0, 0, 0, 0]
    foods(path, [[1, "A", 0, 0, 0, 0, "1 porsi"], [2, " a ", 1, 1, 1, 1, "1 porsi"]])
    with pytest.raises(ValueError, match="duplikat"): ml.foods_data(path)


def test_kelompok_transitif_deterministik():
    groups = [["a", "b"], ["b", "c"]]
    result = ml.groups_for(["a", "b", "c", "d"], groups)
    assert result["a"][0] == result["c"][0] != result["d"][0]
    assert result == ml.groups_for(["d", "c", "b", "a"], list(reversed(groups)))


def isi_nutrisi(food):
    wb = load_workbook(food); ws = wb["Dataset"]
    for col, label in enumerate(["KALORI (kkal)", "PROTEIN (g)", "KARBO (g)", "LEMAK (g)", "PORSI"], 3):
        ws.cell(1, col, label)
        for i in range(2, ws.max_row + 1): ws.cell(i, col, "1 porsi" if label == "PORSI" else 10)
    wb.save(food)


def test_run_sintetis_validasi_hash_dan_dry_run(project, tmp_path):
    folder, food, registry = project
    isi_nutrisi(food)
    assert pv.main(["--version-dir", str(folder), "--foods", str(food), "--run-id", "run1"]) == 0
    run = folder / "processing/run1"
    target = tmp_path / "feature-output"
    args = ["--run-dir", str(run), "--foods", str(food), "--output-dir", str(target)]
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert ml.main(args + ["--dry-run"]) == 0
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert ml.main(args) == 0
    with (target / "ml_feature_table.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    schema = json.loads((target / "feature_schema.json").read_text())
    assert len(rows) == 38
    assert set(schema["fitur_diizinkan"]).isdisjoint(set(schema["metadata_bukan_fitur"]) | {"y"})
    assert all(r["rating_asli"] == "3 = Sesuai (hampir sesuai target)" and r["y"] == "3" for r in rows)
    assert len({r["evaluation_group_id"] for r in rows}) == 1
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert ml.main(args) != 0
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with (run / "candidate/survey_candidate.csv").open("a") as f: f.write("rusak")
    assert ml.main(["--run-dir", str(run), "--foods", str(food), "--output-dir", str(tmp_path / "lain"), "--dry-run"]) != 0


@pytest.mark.parametrize("change", ["hilang", "bertentangan", "ganda"])
def test_pemetaan_kandidat_bermasalah_ditolak(project, tmp_path, change):
    folder, food, registry = project
    isi_nutrisi(food)
    assert pv.main(["--version-dir", str(folder), "--foods", str(food), "--run-id", "run1"]) == 0
    run = folder / "processing/run1"
    path = run / "candidate/survey_candidate.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
    if change == "hilang": rows[0]["nama_makanan_survei"] = "Tidak dikenal"
    if change == "bertentangan": rows[0]["id_makanan"] = "999"
    if change == "ganda": rows[1] = dict(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    manifest_path = run / "processing_manifest.json"; manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"]["candidate/survey_candidate.csv"] = ml.hash_file(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError): ml.build(run, food)
