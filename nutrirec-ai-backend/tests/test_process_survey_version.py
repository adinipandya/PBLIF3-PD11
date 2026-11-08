import csv
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from scripts import version_survey as vs
from scripts import process_survey_version as pv
from scripts import prepare_survey as ps
from scripts import build_survey_candidate as bc


@pytest.fixture
def project(tmp_path):
    survey = tmp_path / "survey.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Form Responses 1"
    ws.append(ps.REQUIRED_COLUMNS + [f"{i}. {n}" for i, n in enumerate(ps.MAPELANGGAN_MAKANAN, 1)])
    for timestamp in ("satu", "dua"):
        ws.append([timestamp, "Rendah (< 300 kkal)", "Protein tinggi", "Tidak ada alergi", ""] + ["3 = Sesuai (hampir sesuai target)"] * 19 + ["2 = Tidak sesuai (agak jauh dari target)"])
    wb.save(survey)
    foods = tmp_path / "foods.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Dataset"
    headers = ["NO", "NAMA MAKANAN", "KALORI (kkal)", "KARBO (g)", "LEMAK (g)", "PROTEIN (g)", "PORSI", "KELOMPOK KALORI", "% ENERGI PROTEIN", "% ENERGI KARBO", "% ENERGI LEMAK", "PRIORITAS NUTRISI", "ALERGEN TERCATAT", "SUMBER DATA", "STATUS ALERGEN", "CATATAN VERIFIKASI"]
    ws.append(headers)
    for i, name in enumerate(ps.MAPELANGGAN_MAKANAN.values(), 1): ws.append([i, name, 300, 40, 10, 10, "1 porsi", "Sedang", "", "", "", "", "", "sumber", "Belum diverifikasi", ""])

    wb.save(foods)
    root = tmp_path / "versions"; registry = tmp_path / "registry.json"
    assert vs.main(["--file", str(survey), "--dataset-version", "v1", "--form-version", "f1", "--source-namespace", "ns", "--mode", "snapshot", "--versions-root", str(root), "--registry", str(registry)]) == 0
    return root / "v1", foods, registry


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def rewrite_sidecar(folder, change):
    path = folder / "submission_identity_map.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
    change(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"][path.name] = pv.digest(path)
    manifest_path.write_text(json.dumps(manifest))


def test_ekspor_identitas_dan_rekonsiliasi(project):
    folder, foods, registry = project
    old = snapshot(folder.parent.parent)
    args = ["--version-dir", str(folder), "--foods", str(foods)]
    assert pv.main(args + ["--dry-run"]) == 0
    assert snapshot(folder.parent.parent) == old
    assert pv.main(args + ["--run-id", "run1"]) == 0
    run = folder / "processing/run1"
    def read(path):
        with path.open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
    responses = read(run / "processed/survey_responses.csv")
    ratings = read(run / "processed/survey_ratings_long.csv")
    candidate = read(run / "candidate/survey_candidate_exploratory.csv")
    excluded = read(run / "candidate/survey_excluded.csv")
    ids = {r["response_id"]: r["submission_uid"] for r in responses}
    assert len(ids) == 2 and len(set(ids.values())) == 2
    assert len(ratings) == 40 and len(candidate) == 0 and len(excluded) == 40
    assert (run / "processed/survey_food_mapping.csv").exists()
    assert len(read(run / "processed/survey_food_mapping.csv")) == 20
    assert (run / "candidate/survey_candidate_report.md").exists()
    assert (run / "candidate/survey_candidate_report.json").exists()
    assert all(row["versi_survei"] == "f1" for row in ratings)
    assert all("definisi_prioritas" in row and "status_pemetaan" in row for row in ratings)
    assert all(row["status_pemetaan"].startswith("ditahan_") for row in ratings)
    assert all(r["submission_uid"] == ids[r["response_id"]] and r["dataset_version"] == "v1" for r in ratings + candidate + excluded)
    report = json.loads((run / "candidate/survey_candidate_report.json").read_text())
    assert {x["submission_uid"] for x in report["kelompok_jawaban_identik_dengan_uid"][0]} == set(ids.values())
    # The candidate builder validates the new audit columns in the canonical versioned pipeline.
    _, _, _, processed_report, candidate_rows, excluded_rows, _ = pv.proses(folder, foods, database_catalog={}, database_verified=False)
    assert len(candidate_rows) + len(excluded_rows) == 40
    assert processed_report["kelayakan_evaluasi_PD11_R2"] == "tidak_layak"
    before = snapshot(folder.parent.parent)
    assert pv.main(args + ["--run-id", "run1"]) != 0
    assert snapshot(folder.parent.parent) == before


@pytest.mark.parametrize("kind", ["kosong", "ganda", "hilang", "berlebih", "metadata", "fingerprint"])
def test_sidecar_tidak_konsisten_ditolak(project, kind):
    folder, foods, registry = project
    def change(rows):
        if kind == "kosong": rows[0]["submission_uid"] = ""
        if kind == "ganda": rows[1]["submission_uid"] = rows[0]["submission_uid"]
        if kind == "hilang": rows.pop()
        if kind == "berlebih": rows.append({**rows[0], "submission_uid": "uid-lain", "source_row": "99"})
        if kind == "metadata": rows[0]["form_version"] = "beda"
        if kind == "fingerprint": rows[0]["fingerprint"] = "beda"
    rewrite_sidecar(folder, change)
    before = snapshot(folder.parent.parent)
    assert pv.main(["--version-dir", str(folder), "--foods", str(foods), "--run-id", "run"]) != 0
    assert snapshot(folder.parent.parent) == before


@pytest.mark.parametrize("kind", ["hash", "tertahan", "incremental"])
def test_manifest_dan_sumber_ditolak(project, kind):
    folder, foods, registry = project
    path = folder / "manifest.json"; manifest = json.loads(path.read_text())
    if kind == "hash": manifest["source_sha256"] = "tidak cocok"
    if kind == "tertahan": manifest["status"] = "tertahan"
    if kind == "incremental": manifest["mode"] = "incremental"
    path.write_text(json.dumps(manifest))
    before = snapshot(folder.parent.parent)
    assert pv.main(["--version-dir", str(folder), "--foods", str(foods), "--run-id", "run"]) != 0
    assert snapshot(folder.parent.parent) == before
