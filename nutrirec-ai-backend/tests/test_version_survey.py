import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from scripts import version_survey as vs


def workbook(path, records, headers=("Timestamp", "Pertanyaan A", "Pertanyaan B")):
    wb = Workbook(); ws = wb.active; ws.title = "Form Responses 1"
    ws.append(headers)
    for record in records:
        ws.append([record.get(header) for header in headers])
    wb.save(path)


def args(tmp_path, source, version="v1", mode="snapshot", previous=None):
    result = ["--file", str(source), "--dataset-version", version, "--form-version", "f1",
              "--source-namespace", "form", "--mode", mode, "--versions-root", str(tmp_path / "versions"),
              "--registry", str(tmp_path / "registry.json")]
    return result + (["--previous-version", previous] if previous else [])


def contents(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_awal_urut_idempotensi_dan_tambahan(tmp_path):
    a = {"Timestamp": "t1", "Pertanyaan A": "ya", "Pertanyaan B": "3"}
    b = {"Timestamp": "t2", "Pertanyaan A": "ya", "Pertanyaan B": "3"}
    source = tmp_path / "source.xlsx"; workbook(source, [a, b])
    assert vs.main(args(tmp_path, source) + ["--dry-run"]) == 0
    assert not (tmp_path / "registry.json").exists()
    assert vs.main(args(tmp_path, source)) == 0
    original = json.loads((tmp_path / "registry.json").read_text())
    assert len({e["submission_uid"] for e in original["submissions"]}) == 2
    before = contents(tmp_path)
    assert vs.main(args(tmp_path, source)) == 0
    assert contents(tmp_path) == before
    workbook(source, [b, a, {"Timestamp": "t3", "Pertanyaan A": "baru"}], headers=("Pertanyaan B", "Timestamp", "Pertanyaan A"))
    assert vs.main(args(tmp_path, source, "v2", previous="v1")) == 0
    after = json.loads((tmp_path / "registry.json").read_text())
    assert len(after["submissions"]) == 3
    assert set(original["versions"]["v1"]["submission_uids"]) <= set(after["versions"]["v2"]["submission_uids"])


def test_perubahan_ambigu_dan_keputusan(tmp_path):
    source = tmp_path / "source.xlsx"
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "awal"}])
    assert vs.main(args(tmp_path, source)) == 0
    old = json.loads((tmp_path / "registry.json").read_text())
    uid = old["submissions"][0]["submission_uid"]
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "berubah"}])
    before = contents(tmp_path)
    assert vs.main(args(tmp_path, source, "v2", previous="v1")) != 0
    assert contents(tmp_path) == before
    decision = tmp_path / "decisions.json"
    decision.write_text(json.dumps({"2": {"submission_uid": uid, "alasan": "ditinjau"}}))
    assert vs.main(args(tmp_path, source, "v2", previous="v1") + ["--decisions", str(decision)]) == 0
    assert "ditinjau" in (tmp_path / "versions/v2/submission_identity_map.csv").read_text(encoding="utf-8-sig")
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "berubah"}] * 2)
    assert vs.main(args(tmp_path, source, "v3", previous="v2")) != 0


def test_incremental_dan_snapshot_tidak_menghapus(tmp_path):
    source = tmp_path / "source.xlsx"
    a = {"Timestamp": "t1", "Pertanyaan A": "a"}; b = {"Timestamp": "t2", "Pertanyaan A": "b"}
    workbook(source, [a, b]); assert vs.main(args(tmp_path, source)) == 0
    workbook(source, [a]); assert vs.main(args(tmp_path, source, "v2", previous="v1")) == 0
    report = json.loads((tmp_path / "versions/v2/ingestion_report.json").read_text())
    assert report["counts"]["tidak_muncul"] == 1
    assert (tmp_path / "versions/v1/source.xlsx").exists()
    assert vs.main(args(tmp_path, source, "v3", "incremental", "v1")) == 0
    registry = json.loads((tmp_path / "registry.json").read_text())
    assert len(registry["submissions"]) == 2
    assert len(registry["versions"]["v3"]["submission_uids"]) == 2


def test_versi_form_dan_versi_existing_ditolak(tmp_path):
    source = tmp_path / "source.xlsx"; workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "a"}])
    assert vs.main(args(tmp_path, source)) == 0
    before = contents(tmp_path)
    changed = args(tmp_path, source, "v2", previous="v1")
    changed[changed.index("f1")] = "f2"
    assert vs.main(changed) != 0
    assert contents(tmp_path) == before
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "b"}])
    assert vs.main(args(tmp_path, source)) != 0


def test_sumber_sama_versi_baru_tidak_menambah_uid(tmp_path):
    source = tmp_path / "source.xlsx"
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "a"}])
    assert vs.main(args(tmp_path, source)) == 0
    assert vs.main(args(tmp_path, source, "v2", previous="v1")) == 0
    registry = json.loads((tmp_path / "registry.json").read_text())
    assert len(registry["submissions"]) == 1
    assert registry["versions"]["v1"]["submission_uids"] == registry["versions"]["v2"]["submission_uids"]


def test_keputusan_tidak_valid_dan_timestamp_ganda_ditahan(tmp_path):
    source = tmp_path / "source.xlsx"
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "a"}])
    assert vs.main(args(tmp_path, source)) == 0
    workbook(source, [{"Timestamp": "t1", "Pertanyaan A": "b"}])
    decision = tmp_path / "decisions.json"
    decision.write_text(json.dumps({"2": {"submission_uid": "tidak-ada", "alasan": "review"}}))
    before = contents(tmp_path)
    assert vs.main(args(tmp_path, source, "v2", previous="v1") + ["--decisions", str(decision)]) != 0
    assert contents(tmp_path) == before
    workbook(source, [{"Timestamp": "t2", "Pertanyaan A": "x"}] * 2)
    assert vs.main(args(tmp_path, source, "v2", previous="v1")) != 0
