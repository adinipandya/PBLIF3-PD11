"""Proses arsip snapshot survei secara offline dengan metadata identitas."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Mendukung baik pemanggilan langsung maupun import dari tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import prepare_survey as ps
from scripts import build_survey_candidate as bc
from scripts import version_survey as vs

META = ("submission_uid", "dataset_version", "form_version", "source_namespace")
SIDECAR = {"response_id", "source_row", "submission_uid", "timestamp", "fingerprint", "status", *META[1:]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baca_arsip(folder):
    folder = Path(folder)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "selesai":
        raise ValueError("Versi belum selesai atau tertahan untuk review")
    if manifest.get("mode") != "snapshot":
        raise ValueError("Mode incremental belum didukung: rekonstruksi lengkap belum tersedia")
    if manifest.get("identity_rules") != vs.ATURAN:
        raise ValueError("Versi aturan identitas tidak didukung")
    for name in ("dataset_version", "form_version", "source_namespace"):
        if not isinstance(manifest.get(name), str) or not manifest[name].strip():
            raise ValueError(f"Metadata versi tidak valid: {name}")
    if manifest["dataset_version"] != folder.name:
        raise ValueError("Nama folder tidak cocok dengan dataset_version")
    for name in ("source.xlsx", "submission_identity_map.csv", "ingestion_report.json"):
        if manifest.get("output_sha256", {}).get(name) != digest(folder / name):
            raise ValueError(f"Hash arsip tidak cocok: {name}")
    if manifest.get("source_sha256") != digest(folder / "source.xlsx"):
        raise ValueError("Hash sumber tidak cocok dengan manifest")
    ingest = json.loads((folder / "ingestion_report.json").read_text(encoding="utf-8"))
    if ingest.get("review") != []:
        raise ValueError("Laporan ingest masih memiliki review")
    _, mapping = bc.baca_csv(folder / "submission_identity_map.csv", SIDECAR)
    sumber = vs.baca_sumber(folder / "source.xlsx")
    by_row = {}
    seen_uid = set()
    for item in mapping:
        uid = item["submission_uid"].strip()
        if not uid or uid in seen_uid:
            raise ValueError("UID kosong atau duplikat pada sidecar")
        seen_uid.add(uid)
        row = item["source_row"]
        if row in by_row:
            raise ValueError(f"source_row duplikat pada sidecar: {row}")
        if item["status"] not in {"baru", "cocok", "baru_manual", "cocok_manual"}:
            raise ValueError(f"Status identitas belum selesai: {item['status']}")
        for key in META[1:]:
            if item[key] != manifest[key]:
                raise ValueError(f"Metadata sidecar tidak cocok: {key}, baris {row}")
        by_row[row] = item
    if len(sumber) != len(mapping):
        raise ValueError("Jumlah kiriman dan sidecar tidak sama")
    for item in sumber:
        match = by_row.get(str(item["source_row"]))
        if match is None or any(str(item[k]) != match[k] for k in ("response_id", "source_row", "timestamp", "fingerprint")):
            raise ValueError(f"Sidecar tidak cocok dengan sumber pada baris {item['source_row']}")
    return manifest, sumber, by_row


def stringify(rows):
    return [{k: "" if v is None else str(v) for k, v in row.items()} for row in rows]


def proses(folder, foods):
    folder = Path(folder)
    manifest, sumber, identities = baca_arsip(folder)
    rows, errors = ps.baca_survei(str(folder / "source.xlsx"))
    dataset, dataset_errors = ps.baca_dataset(str(foods))
    if errors or dataset_errors:
        raise ValueError("Validasi struktur gagal: " + "; ".join(errors + dataset_errors))
    responses, ratings, report = ps.siapkan_data(rows, dataset)
    responses, ratings = stringify(responses), stringify(ratings)
    if len(responses) != len(sumber):
        raise ValueError("Jumlah kiriman persiapan tidak sesuai arsip")
    for row in responses + ratings:
        identity = identities.get(row["source_row"])
        if identity is None or row["response_id"] != identity["response_id"]:
            raise ValueError("Kiriman hasil persiapan tidak memiliki identitas yang cocok")
        row.update({key: identity[key] for key in META})
    if len({row["response_id"] for row in responses}) != len(sumber):
        raise ValueError("Kiriman hasil persiapan tidak unik")
    # Kandidat memakai aturan lama; metadata ditambahkan pada output setelah seleksi.
    plain_responses = [{k: v for k, v in row.items() if k not in META} for row in responses]
    plain_ratings = [{k: v for k, v in row.items() if k not in META} for row in ratings]
    candidate, excluded, candidate_report = bc.buat_kandidat(plain_responses, plain_ratings, report, {})
    for item in candidate + excluded:
        identity = identities[item["source_row"]]
        item.update({key: identity[key] for key in META})
    key = lambda item: (item["response_id"], item["nama_makanan_survei"])
    all_keys = {key(item) for item in ratings}
    ckeys, ekeys = {key(item) for item in candidate}, {key(item) for item in excluded}
    if ckeys & ekeys or ckeys | ekeys != all_keys or len(candidate) + len(excluded) != len(ratings) or len(all_keys) != len(ratings):
        raise ValueError("Rekonsiliasi partisi penilaian gagal")
    groups = [[{"response_id": rid, "submission_uid": next(r["submission_uid"] for r in responses if r["response_id"] == rid)} for rid in group] for group in report["kelompok_jawaban_identik"]]
    candidate_report["kelompok_jawaban_identik_dengan_uid"] = groups
    return manifest, responses, ratings, report, candidate, excluded, candidate_report


def write_csv(path, rows, fallback):
    fields = list(rows[0]) if rows else fallback
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-dir", required=True)
    parser.add_argument("--foods", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.dry_run and not args.run_id:
            raise ValueError("--run-id wajib untuk ekspor")
        if args.run_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.run_id):
            raise ValueError("run-id tidak valid")
        folder = Path(args.version_dir)
        target = folder / "processing" / (args.run_id or "")
        if args.run_id and target.exists():
            raise ValueError("run-id sudah ada; tidak boleh ditimpa")
        manifest, responses, ratings, report, candidate, excluded, candidate_report = proses(folder, args.foods)
        print(f"Kiriman: {len(responses)}; penilaian: {len(ratings)}; kandidat: {len(candidate)}; pengecualian: {len(excluded)}")
        if args.dry_run:
            print("DRY RUN: tidak menulis berkas")
            return 0
        parent = folder / "processing"
        parent.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=parent))
        try:
            processed = stage / "processed"; processed.mkdir()
            output = stage / "candidate"; output.mkdir()
            write_csv(processed / "survey_responses.csv", responses, list(bc.RESP_FIELDS) + list(META))
            write_csv(processed / "survey_ratings_long.csv", ratings, list(bc.RATING_FIELDS) + list(META))
            report["source_sha256"] = manifest["source_sha256"]
            (processed / "survey_validation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            write_csv(output / "survey_candidate.csv", candidate, list(bc.RATING_FIELDS) + list(META))
            write_csv(output / "survey_excluded.csv", excluded, list(bc.RATING_FIELDS) + list(META) + ["alasan_pengecualian"])
            candidate_report["hash_masukan_sha256"] = {"responses": digest(processed / "survey_responses.csv"), "ratings": digest(processed / "survey_ratings_long.csv"), "validation_report": digest(processed / "survey_validation_report.json")}
            (output / "survey_candidate_report.json").write_text(json.dumps(candidate_report, indent=2, ensure_ascii=False), encoding="utf-8")
            result = {"status": "selesai", "run_id": args.run_id, "dataset_version": manifest["dataset_version"], "form_version": manifest["form_version"], "source_namespace": manifest["source_namespace"], "manifest_versi_sha256": digest(folder / "manifest.json"), "source_sha256": digest(folder / "source.xlsx"), "sidecar_sha256": digest(folder / "submission_identity_map.csv"), "foods_sha256": digest(args.foods), "aturan_identitas": vs.ATURAN, "aturan_pemetaan_persiapan": ps.VERSI_PEMETAAN, "aturan_seleksi": bc.VERSI_ATURAN, "jumlah_kiriman": len(responses), "jumlah_penilaian": len(ratings), "jumlah_kandidat": len(candidate), "jumlah_pengecualian": len(excluded), "output_sha256": {str(p.relative_to(stage)): digest(p) for p in stage.rglob("*") if p.is_file()}, "siap_training": False}
            (stage / "processing_manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            if target.exists():
                raise ValueError("run-id sudah ada; tidak boleh ditimpa")
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        print(f"Hasil: {target}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
