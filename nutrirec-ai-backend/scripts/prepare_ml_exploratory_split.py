"""Build exploratory features and a deterministic grouped holdout without fitting models."""

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import prepare_ml_features as features

FEATURES = features.FEATURES
ALLERGENS = features.ALLERGENS
VERSION = "fitur-eksploratif-grouped-holdout-v1"
SEED = 42
TEST_FRACTION = 0.20
GROUP_POLICY = "UID kiriman sebagai unit; kelompok jawaban identik yang tercatat digabung melalui komponen transitif"
EXPLORATORY_NOTICE = (
    "Kandidat ini belum siap training final. Baris hanya untuk eksplorasi; "
    "pemetaan resep/porsi perlu tinjauan, semua relasi alergen belum diverifikasi, "
    "rating Seimbang survei legacy bermakna tanpa prioritas khusus dan bukan rasio 15/55/30."
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Header hilang/duplikat: {path}")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError(f"Kolom tidak lengkap: {path}")
        return reader.fieldnames, rows


def validate_run(run_dir, foods_path):
    run = Path(run_dir)
    manifest_path = run / "processing_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "selesai":
        raise ValueError("Run pipeline belum selesai")
    if manifest.get("siap_training") is not False:
        raise ValueError("Run tidak ditandai belum siap training")
    required = {
        "candidate/survey_candidate_exploratory.csv",
        "candidate/survey_excluded.csv",
        "candidate/survey_candidate_report.json",
        "processed/survey_responses.csv",
        "processed/survey_ratings_long.csv",
        "processed/survey_validation_report.json",
    }
    output_hashes = manifest.get("output_sha256", {})
    if not required.issubset(output_hashes):
        raise ValueError("Manifest tidak memuat hash semua artefak eksploratif wajib")
    for relative in required:
        if digest(run / relative) != output_hashes[relative]:
            raise ValueError(f"Hash output run tidak cocok: {relative}")
    if digest(foods_path) != manifest.get("foods_sha256"):
        raise ValueError("Hash katalog tidak sama dengan run dataset")
    report = json.loads((run / "candidate/survey_candidate_report.json").read_text(encoding="utf-8"))
    if report.get("siap_training") is not False:
        raise ValueError("Laporan kandidat tidak mengunci status belum siap training")
    if report.get("kelayakan_PD11_R2") != "tidak_layak_evaluasi":
        raise ValueError("Status kelayakan PD11-R2 tidak sesuai")
    if report.get("jumlah_kandidat_eksploratif_lolos") != 0:
        raise ValueError("Run menyatakan ada baris bersih; mode ini hanya menerima kandidat berpenanda review")
    if report.get("jumlah_kandidat_eksploratif_perlu_tinjau") != report.get("jumlah_kandidat"):
        raise ValueError("Tidak semua baris eksploratif memiliki penanda tinjauan")
    return manifest, report


def make_rows(run_dir, foods_path):
    manifest, report = validate_run(run_dir, foods_path)
    run = Path(run_dir)
    candidates = read_csv(run / "candidate/survey_candidate_exploratory.csv")[1]
    excluded = read_csv(run / "candidate/survey_excluded.csv")[1]
    responses = read_csv(run / "processed/survey_responses.csv")[1]
    ratings = read_csv(run / "processed/survey_ratings_long.csv")[1]
    if len(candidates) + len(excluded) != len(ratings) or len(ratings) != manifest.get("jumlah_penilaian"):
        raise ValueError("Rekonsiliasi rating sumber, kandidat dan yang ditahan gagal")
    foodmap = features.foods_data(foods_path)
    responses_by_uid = {}
    for row in responses:
        uid = row["submission_uid"]
        if not uid or uid in responses_by_uid:
            raise ValueError("submission_uid kosong atau berulang pada tabel respons")
        responses_by_uid[uid] = row
    if len(responses) != manifest.get("jumlah_kiriman"):
        raise ValueError("Jumlah respons berbeda dari manifest run")

    groups = []
    identical_groups = report.get("kelompok_jawaban_identik_dengan_uid", [])
    for group in identical_groups:
        members = []
        for item in group:
            uid = item.get("submission_uid")
            if uid not in responses_by_uid or responses_by_uid[uid]["response_id"] != item.get("response_id"):
                raise ValueError("Kelompok jawaban identik tidak cocok dengan respons run")
            members.append(uid)
        if len(members) > 1:
            groups.append(members)
    group_map = features.groups_for(responses_by_uid, groups)

    output, seen_pairs = [], set()
    for row in candidates:
        uid = row["submission_uid"]
        response = responses_by_uid.get(uid)
        if response is None:
            raise ValueError(f"UID kandidat tidak dikenal: {uid}")
        if row["response_id"] != response["response_id"]:
            raise ValueError("response_id kandidat tidak cocok dengan UID")
        if row["rating"] not in {"1", "2", "3", "4"}:
            raise ValueError(f"Rating tidak valid untuk {uid}")
        if not row["rating_asli"].startswith(row["rating"] + " = "):
            raise ValueError(f"Rating asli berubah/tidak sesuai untuk {uid}")
        if not row["target_kalori_id"] or not row["prioritas_id"] or not row["status_alergi_normalisasi"]:
            raise ValueError(f"Profil tidak lengkap untuk {uid}")
        if row["definisi_prioritas"] != response["definisi_prioritas"]:
            raise ValueError(f"Definisi prioritas berubah untuk {uid}")
        if row["prioritas_asli"] == "Seimbang (tidak ada prioritas khusus)" and row["definisi_prioritas"] != "tanpa_prioritas_khusus_survei_legacy":
            raise ValueError("Makna Seimbang survei legacy tidak terjaga")
        if row["status_pemeriksaan_gizi"] != "valid":
            raise ValueError(f"Kandidat dengan gizi invalid tidak boleh masuk: {uid}")
        source_name = features.ps.kunci_header_makanan(row["nama_makanan_survei"])
        catalog_name = features.ps.MAPELANGGAN_MAKANAN_NORMALIZED.get(source_name)
        food = foodmap.get(catalog_name.casefold()) if catalog_name else None
        if not food or str(food["no"]) != row["id_makanan_sumber"]:
            raise ValueError(f"Pemetaan eksploratif tidak cocok: {row['nama_makanan_survei']}")
        pair = (uid, food["no"])
        if pair in seen_pairs:
            raise ValueError(f"Pasangan respons-makanan duplikat: {pair}")
        seen_pairs.add(pair)
        ids = row["alergen_ids_normalisasi"].split(";") if row["alergen_ids_normalisasi"] else []
        if len(ids) != len(set(ids)) or any(value not in {str(i) for i in features.ALLERGENS.values()} for value in ids):
            raise ValueError(f"ID alergen tidak valid: {uid}")
        target = features.ps.TARGET_OPTIONS.get(row["target_kalori_asli"])
        priority = features.ps.PRIORITY_OPTIONS.get(row["prioritas_asli"])
        if not target or not priority:
            raise ValueError(f"Kategori profil tidak dikenal: {uid}")
        priority_value = row["prioritas_asli"] if priority["nama"] == "Seimbang" else priority["nama"]
        pflags = row["penanda_kiriman"]
        rflags = row["penanda_penilaian"]
        profile = {
            "target_kalori": target["nama"],
            "prioritas": priority_value,
            "status_alergi": features.ps.STATUS_ALLERGI[row["status_alergi_normalisasi"]],
        }
        profile.update({f"alergen_{i}": int(str(i) in ids) for i in sorted(features.ALLERGENS.values())})
        nutrition = dict(zip(("kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g"), [float(x) for x in (row["kalori_katalog"], row["protein_katalog"], row["karbohidrat_katalog"], row["lemak_katalog"])]))
        if any(not math.isfinite(v) or v < 0 for v in nutrition.values()):
            raise ValueError(f"Nilai gizi invalid: {uid}")
        if 4 * nutrition["protein_g"] + 4 * nutrition["karbohidrat_g"] + 9 * nutrition["lemak_g"] <= 0:
            raise ValueError(f"Energi makro tidak positif: {uid}")
        metadata = {
            "response_id": row["response_id"], "submission_uid": uid,
            "evaluation_group_id": group_map[uid][0],
            "source_row": row["source_row"], "timestamp": response.get("timestamp", ""),
            "dataset_version": row["dataset_version"], "form_version": row["form_version"],
            "source_namespace": row["source_namespace"], "nama_makanan_survei": row["nama_makanan_survei"],
            "nama_makanan_dataset": food["nama"], "no_makanan_excel": str(food["no"]),
            "rating_asli": row["rating_asli"], "penanda_kiriman": pflags,
            "penanda_penilaian": rflags, "status_eksploratif": row["status_eksploratif"],
            "alasan_tinjau_eksploratif": row["alasan_tinjau_eksploratif"],
            "status_pemetaan": row["status_pemetaan"], "alasan_pemetaan": row["alasan_pemetaan"],
            "status_alergen_katalog": row["status_alergen_katalog_asli"],
            "definisi_prioritas": row["definisi_prioritas"],
        }
        output.append({**profile, **nutrition, "y": int(row["rating"]), **metadata})

    candidate_uids = {row["submission_uid"] for row in output}
    group_rows = [{"submission_uid": uid, "evaluation_group_id": group_map[uid][0], "alasan": group_map[uid][1]} for uid in sorted(candidate_uids)]
    raw_distribution = dict(Counter(str(row["rating"]) for row in ratings))
    candidate_distribution = dict(Counter(str(row["y"]) for row in output))
    excluded_distribution = dict(Counter(str(row["rating"]) for row in excluded))
    if sum(map(int, raw_distribution.values())) != len(output) + len(excluded):
        raise ValueError("Jumlah baris sumber tidak sama dengan kandidat ditambah ditahan")
    unique_duplicate_pairs = sum(len(group) for group in groups)
    return manifest, report, output, group_rows, {
        "jumlah_kiriman_sumber": len(responses), "jumlah_id_respons": len({r['response_id'] for r in responses}),
        "jumlah_uid_sumber": len(responses_by_uid), "jumlah_kandidat_baris": len(output),
        "jumlah_kandidat_uid": len(candidate_uids), "jumlah_kelompok_identik_terdokumentasi": len(groups),
        "jumlah_uid_dalam_kelompok_identik": unique_duplicate_pairs,
        "jumlah_kiriman_sumber_tidak_masuk_kandidat": len(set(responses_by_uid) - candidate_uids),
        "jumlah_pasangan_rating_yang_tidak_dipilih": len(excluded),
        "jumlah_evaluation_groups_kandidat": len({r['evaluation_group_id'] for r in output}),
        "jumlah_pasangan_rating_sumber": len(ratings), "jumlah_ditahan_atau_dikecualikan": len(excluded),
        "distribusi_rating_sumber": raw_distribution, "distribusi_rating_kandidat": candidate_distribution,
        "distribusi_rating_ditahan": excluded_distribution,
        "jumlah_baris_dengan_seimbang_legacy": sum(r['prioritas'] == 'Seimbang (tidak ada prioritas khusus)' for r in output),
        "seluruh_seimbang_legacy_ditandai_tanpa_prioritas_khusus": all(r['definisi_prioritas'] == 'tanpa_prioritas_khusus_survei_legacy' for r in output if r['prioritas'] == 'Seimbang (tidak ada prioritas khusus)'),
        "kelayakan": "eksploratif_berpenanda_tinjauan; bukan_dataset_training_final_atau_evaluasi_PD11_R2",
        "peringatan": EXPLORATORY_NOTICE,
    }


def split_groups(groups, test_fraction=TEST_FRACTION, seed=SEED):
    """Deterministic shuffle of whole groups; no stratification or metric-based tuning."""
    import random
    unique = sorted({row["evaluation_group_id"] for row in groups})
    if len(unique) < 2:
        raise ValueError("Minimal dua kelompok evaluasi diperlukan untuk split")
    shuffled = list(unique)
    random.Random(seed).shuffle(shuffled)
    n_test = max(1, min(len(unique) - 1, round(len(unique) * test_fraction)))
    test_groups = set(shuffled[:n_test])
    train_groups = set(unique) - test_groups
    return train_groups, test_groups


def split_report(rows, train_groups, test_groups, group_rows):
    by_side = {}
    for label, group_set in (("train", train_groups), ("test", test_groups)):
        subset = [row for row in rows if row["evaluation_group_id"] in group_set]
        counts = Counter(row["y"] for row in subset)
        priority_counts = Counter(row["prioritas"] for row in subset)
        by_side[label] = {
            "jumlah_kelompok": len(group_set), "persentase_kelompok": 100 * len(group_set) / (len(train_groups) + len(test_groups)),
            "jumlah_baris": len(subset), "persentase_baris": 100 * len(subset) / len(rows),
            "jumlah_uid": len({row["submission_uid"] for row in subset}),
            "distribusi_rating": {str(k): counts[k] for k in (1, 2, 3, 4)},
            "distribusi_prioritas": dict(priority_counts),
            "kelas_rating_tidak_ada": [k for k in (1, 2, 3, 4) if counts[k] == 0],
            "kelompok_tanpa_rating_1": len(group_set) - len({r['evaluation_group_id'] for r in subset if r['y'] == 1}),
        }
    train_uids = {row["submission_uid"] for row in rows if row["evaluation_group_id"] in train_groups}
    test_uids = {row["submission_uid"] for row in rows if row["evaluation_group_id"] in test_groups}
    train_gids = {row["evaluation_group_id"] for row in rows if row["evaluation_group_id"] in train_groups}
    test_gids = {row["evaluation_group_id"] for row in rows if row["evaluation_group_id"] in test_groups}
    if train_uids & test_uids or train_gids & test_gids:
        raise ValueError("Kebocoran UID atau kelompok antar split")
    if len(train_uids | test_uids) != len({row["submission_uid"] for row in rows}):
        raise ValueError("Split tidak mencakup semua UID kandidat")
    return {"train": by_side["train"], "test": by_side["test"], "tidak_ada_uid_lintas_split": True,
            "tidak_ada_kelompok_lintas_split": True,
            "holdout_untuk": "kiriman/group baru pada katalog makanan dikenal; tidak menguji makanan baru",
            "kebijakan": GROUP_POLICY, "seed": SEED, "test_fraction_target": TEST_FRACTION,
            "unit_split": "evaluation_group_id; setiap UID dan semua ratingnya ikut ke sisi kelompok yang sama"}


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def create_artifacts(run_dir, foods_path, out_dir, seed=SEED):
    if seed != SEED:
        raise ValueError(f"Seed versi ini dipatok ke {SEED}; buat versi konfigurasi baru untuk seed lain")
    manifest, source_report, rows, groups, counts = make_rows(run_dir, foods_path)
    train_groups, test_groups = split_groups(groups, seed=seed)
    split = split_report(rows, train_groups, test_groups, groups)
    train_rows = [r for r in rows if r["evaluation_group_id"] in train_groups]
    test_rows = [r for r in rows if r["evaluation_group_id"] in test_groups]
    if len(train_rows) + len(test_rows) != len(rows):
        raise ValueError("Rekonsiliasi train/test gagal")
    out = Path(out_dir)
    if out.exists():
        raise ValueError(f"Direktori keluaran sudah ada: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".features-stage-", dir=out.parent))
    try:
        feature_fields = FEATURES + ["y"] + [f for f in ["response_id", "submission_uid", "evaluation_group_id", "source_row", "timestamp", "dataset_version", "form_version", "source_namespace", "nama_makanan_survei", "nama_makanan_dataset", "no_makanan_excel", "rating_asli", "penanda_kiriman", "penanda_penilaian", "status_eksploratif", "alasan_tinjau_eksploratif", "status_pemetaan", "alasan_pemetaan", "status_alergen_katalog", "definisi_prioritas"]]
        write_csv(stage / "ml_feature_table_exploratory.csv", rows, feature_fields)
        write_csv(stage / "train.csv", train_rows, feature_fields)
        write_csv(stage / "test.csv", test_rows, feature_fields)
        write_csv(stage / "evaluation_groups.csv", groups, ["submission_uid", "evaluation_group_id", "alasan"])
        group_assignments = [{"evaluation_group_id": g, "split": "test" if g in test_groups else "train"} for g in sorted(train_groups | test_groups)]
        write_csv(stage / "split_groups.csv", group_assignments, ["evaluation_group_id", "split"])
        schema = {"fitur_diizinkan": FEATURES, "target": {"y": "rating asli survei, 1-4"}, "metadata_bukan_fitur": [f for f in feature_fields if f not in FEATURES and f != "y"], "kategori": {"target_kalori": ["Rendah", "Sedang", "Tinggi"], "prioritas": ["Protein", "Karbohidrat", "Lemak", "Seimbang (tidak ada prioritas khusus), makna legacy"]}, "kamus_alergen_id": ALLERGENS, "satuan": {"kalori_kkal": "kkal/porsi", "protein_g": "g/porsi", "karbohidrat_g": "g/porsi", "lemak_g": "g/porsi"}, "encoding": "fit encoder/scaler/imputer hanya pada train di tahap training; artefak fitur ini menyimpan nilai mentah/kategori", "seimbang_legacy": "tanpa prioritas khusus; bukan rasio PD11-R2 15/55/30"}
        (stage / "feature_schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        feasibility = {"dataset_ready_for_final_training": False, "dataset_ready_for_PD11_R2_evaluation": False, "reason": "Run sumber secara eksplisit siap_training=false; eksplorasi opt-in tidak mengubah keputusan kelayakan.", **counts}
        (stage / "exploratory_feasibility_report.json").write_text(json.dumps(feasibility, indent=2, ensure_ascii=False), encoding="utf-8")
        (stage / "split_report.json").write_text(json.dumps(split, indent=2, ensure_ascii=False), encoding="utf-8")
        config = {"versi": VERSION, "mode": "exploratory_only", "seed": seed, "test_fraction_target": TEST_FRACTION, "kelompok": GROUP_POLICY, "rows_sorted_before_split": True, "strategy": "deterministic shuffle of whole sorted evaluation groups; no stratification/search", "training": False, "preprocessing_fit_scope": "train only later; none fitted now", "source_run_id": manifest["run_id"], "source_feature_run_used": "pd11-r2-cleanup-003"}
        (stage / "split_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        source_inputs = {
            "processing_manifest": digest(Path(run_dir) / "processing_manifest.json"),
            "candidate_exploratory": digest(Path(run_dir) / "candidate/survey_candidate_exploratory.csv"),
            "candidate_report": digest(Path(run_dir) / "candidate/survey_candidate_report.json"),
            "responses": digest(Path(run_dir) / "processed/survey_responses.csv"),
            "ratings": digest(Path(run_dir) / "processed/survey_ratings_long.csv"),
            "catalog": digest(foods_path),
        }
        result = {"status": "exploratory_features_and_holdout_created", "ready_for_training": False, "ready_for_PD11_R2_evaluation": False, "versi": VERSION, "source_dataset_version": manifest["dataset_version"], "source_run_id": manifest["run_id"], "source_run_training_flag": manifest["siap_training"], "seed": seed, "jumlah_baris": len(rows), "jumlah_train": len(train_rows), "jumlah_test": len(test_rows), "input_sha256": source_inputs}
        (stage / "manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["output_sha256"] = {p.name: digest(p) for p in stage.iterdir() if p.is_file() and p.name != "manifest.json"}
        (stage / "manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        os.rename(stage, out)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return split, counts, out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--foods", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, report, rows, groups, counts = make_rows(args.run_dir, args.foods)
        train_groups, test_groups = split_groups(groups, seed=args.seed)
        split = split_report(rows, train_groups, test_groups, groups)
        print(f"Mode exploratory-only; source={manifest['run_id']}; rows={len(rows)}; UIDs={counts['jumlah_kandidat_uid']}; groups={counts['jumlah_evaluation_groups_kandidat']}")
        print(f"Train: {split['train']['jumlah_kelompok']} groups ({split['train']['persentase_kelompok']:.2f}%), {split['train']['jumlah_baris']} rows ({split['train']['persentase_baris']:.2f}%)")
        print(f"Test: {split['test']['jumlah_kelompok']} groups ({split['test']['persentase_kelompok']:.2f}%), {split['test']['jumlah_baris']} rows ({split['test']['persentase_baris']:.2f}%)")
        print(f"Rating train/test: {split['train']['distribusi_rating']} / {split['test']['distribusi_rating']}")
        if args.dry_run:
            print("DRY RUN: no outputs written")
            return 0
        split, counts, out = create_artifacts(args.run_dir, args.foods, args.output_dir, args.seed)
        print(f"Artifacts: {out}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
