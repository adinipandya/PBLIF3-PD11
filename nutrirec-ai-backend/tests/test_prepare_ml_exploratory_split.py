import csv
import json
import shutil
from pathlib import Path

import pytest

from scripts import prepare_ml_exploratory_split as split

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/survey_versions/survey-v001/processing/pd11-r2-cleanup-003"
FOODS = ROOT / "data/Dataset_makanan_revisi.xlsx"


def test_cleanup003_integrity_features_and_group_split(tmp_path):
    out = tmp_path / "features-exploratory-split"
    split_report, counts, result_dir = split.create_artifacts(RUN, FOODS, out)

    assert result_dir == out
    assert counts["jumlah_pasangan_rating_sumber"] == 1300
    assert counts["jumlah_kandidat_baris"] == 1050
    assert counts["jumlah_pasangan_rating_yang_tidak_dipilih"] == 250
    assert counts["jumlah_kandidat_uid"] == 56
    assert counts["jumlah_evaluation_groups_kandidat"] == 54
    assert counts["seluruh_seimbang_legacy_ditandai_tanpa_prioritas_khusus"] is True
    assert counts["jumlah_baris_dengan_seimbang_legacy"] == 544
    assert counts["distribusi_rating_sumber"] == {"1": 32, "2": 226, "3": 644, "4": 398}
    assert counts["distribusi_rating_kandidat"] == {"1": 7, "2": 181, "3": 518, "4": 344}
    assert counts["distribusi_rating_ditahan"] == {"1": 25, "2": 45, "3": 126, "4": 54}
    assert len(split.read_csv(out / "ml_feature_table_exploratory.csv")[1]) == 1050
    assert split_report["tidak_ada_uid_lintas_split"]
    assert split_report["tidak_ada_kelompok_lintas_split"]
    assert split_report["train"]["jumlah_kelompok"] == 43
    assert split_report["test"]["jumlah_kelompok"] == 11
    assert split_report["train"]["jumlah_baris"] + split_report["test"]["jumlah_baris"] == 1050
    assert split_report["train"]["distribusi_rating"]["1"] == 7
    assert split_report["test"]["distribusi_rating"]["1"] == 0

    with (out / "train.csv").open(encoding="utf-8-sig", newline="") as stream:
        train = list(csv.DictReader(stream))
    with (out / "test.csv").open(encoding="utf-8-sig", newline="") as stream:
        test = list(csv.DictReader(stream))
    assert {r["submission_uid"] for r in train}.isdisjoint({r["submission_uid"] for r in test})
    assert {r["evaluation_group_id"] for r in train}.isdisjoint({r["evaluation_group_id"] for r in test})
    assert all(r["status_eksploratif"] == "perlu_tinjau" for r in train + test)
    assert all(r["prioritas"] == "Seimbang (tidak ada prioritas khusus)" and r["definisi_prioritas"] == "tanpa_prioritas_khusus_survei_legacy" for r in train + test if r["prioritas"] == "Seimbang (tidak ada prioritas khusus)")
    assert "rating_asli" not in split.features.FEATURES
    assert "submission_uid" not in split.features.FEATURES
    assert "timestamp" not in split.features.FEATURES

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["ready_for_training"] is False
    assert manifest["ready_for_PD11_R2_evaluation"] is False
    assert manifest["source_run_training_flag"] is False
    assert manifest["source_run_id"] == "pd11-r2-cleanup-003"
    for name, expected in manifest["output_sha256"].items():
        import hashlib
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected


def test_grouped_split_is_seeded_and_keeps_identical_groups_together():
    groups = []
    for idx in range(10):
        gid = f"G{idx:02}"
        for suffix in ("a", "b"):
            groups.append({"submission_uid": f"u{idx}{suffix}", "evaluation_group_id": gid, "alasan": "jawaban_identik"})
    train1, test1 = split.split_groups(groups, seed=42)
    train2, test2 = split.split_groups(groups, seed=42)
    assert (train1, test1) == (train2, test2)
    assert train1.isdisjoint(test1)
    assert len(test1) == 2
    assert len(train1) == 8


def test_source_run_not_ready_flag_is_preserved_and_bad_hash_rejected(tmp_path):
    source_manifest = json.loads((RUN / "processing_manifest.json").read_text())
    assert source_manifest["siap_training"] is False
    bad_run = tmp_path / "bad-run"
    shutil.copytree(RUN, bad_run)
    (bad_run / "candidate/survey_candidate_exploratory.csv").write_text("tampered\n")
    with pytest.raises(ValueError, match="Hash output run tidak cocok"):
        split.make_rows(bad_run, FOODS)


def test_split_requires_distinct_groups():
    with pytest.raises(ValueError, match="Minimal dua kelompok"):
        split.split_groups([{"evaluation_group_id": "only"}])
