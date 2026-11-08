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

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

# Mendukung baik pemanggilan langsung maupun import dari tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import prepare_survey as ps
from scripts import build_survey_candidate as bc
from scripts import version_survey as vs
from app.db.session import SessionLocal
from app.models.makanan import Makanan

META = ("submission_uid", "dataset_version", "form_version", "source_namespace")
MAP_FIELDS = [
    "nama_makanan_survei", "nomor_makanan_sumber", "id_makanan_sumber",
    "id_makanan_katalog", "nama_makanan_katalog", "varian", "porsi",
    "status_pemetaan", "alasan", "status_gizi", "kategori_kalori_PD11_R2", "kategori_kalori_asli", "versi_dataset_makanan",
    "versi_survei", "id_database_diverifikasi",
]
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


def baca_database_catalog():
    """Read-only snapshot used to verify catalog PK/name/source nutrition mappings."""
    with SessionLocal() as db:
        foods = db.scalars(
            select(Makanan).options(joinedload(Makanan.informasi_gizi)).order_by(Makanan.id_makanan)
        ).unique().all()
        return {
            food.id_makanan: {
                "id_makanan": food.id_makanan,
                "nama": food.nama_makanan,
                "porsi": food.deskripsi_porsi,
                "kelompok_kalori": food.kelompok_kalori,
                "versi_dataset": food.versi_dataset,
                "kalori": food.informasi_gizi.kalori if food.informasi_gizi else None,
                "protein": food.informasi_gizi.protein if food.informasi_gizi else None,
                "karbohidrat": food.informasi_gizi.karbohidrat if food.informasi_gizi else None,
                "lemak": food.informasi_gizi.lemak if food.informasi_gizi else None,
            }
            for food in foods
        }

def proses(folder, foods, *, database_catalog=None, database_verified=False):
    folder = Path(folder)
    manifest, sumber, identities = baca_arsip(folder)
    rows, errors = ps.baca_survei(str(folder / "source.xlsx"))
    catalog_details, dataset_errors = ps.baca_dataset_detail(str(foods))
    if errors or dataset_errors:
        raise ValueError("Validasi struktur gagal: " + "; ".join(errors + dataset_errors))
    dataset = {name: item["id_sumber"] for name, item in catalog_details.items()}
    database_catalog = database_catalog or {}
    food_versions = {str(item["versi_dataset"]) for item in database_catalog.values() if item.get("versi_dataset")}
    if database_verified and len(food_versions) != 1:
        raise ValueError("Snapshot database tidak memiliki satu versi dataset makanan yang unik.")
    food_dataset_version = next(iter(food_versions)) if database_verified else "unknown"
    responses, ratings, report = ps.siapkan_data(
        rows, dataset, catalog_details=catalog_details,
        database_catalog=database_catalog if database_verified else {},
        dataset_version=food_dataset_version,
    )
    report["dataset_makanan_sumber_hash"] = digest(foods)
    report["dataset_makanan_version"] = food_dataset_version
    report["nama_sumber_survei"] = str(folder / "source.xlsx")
    report["nama_sumber_katalog"] = str(Path(foods).resolve())
    report["hash_sidecar_identitas"] = digest(folder / "submission_identity_map.csv")
    report["hash_manifest_survei"] = digest(folder / "manifest.json")
    report["hash_laporan_ingest"] = digest(folder / "ingestion_report.json")
    report["versi_survei"] = manifest["form_version"]
    report["prioritas_definisi"] = ps.DEFINISI_PRIORITAS
    report["versi_aturan_rekomendasi"] = "PD11-R2"
    report["database_katalog_diperiksa"] = database_verified
    report["kelayakan_evaluasi_PD11_R2"] = "tidak_layak"
    report["alasan_tidak_layak_evaluasi_PD11_R2"] = [
        "Definisi Seimbang survei lama adalah tidak ada prioritas khusus; bukan rating rasio 15/55/30.",
        "ID group adalah ID kiriman, bukan identitas responden yang terverifikasi.",
    ]
    report["kebutuhan_survei_tambahan_PD11_R2"] = [
        "Kumpulkan respons dengan instrumen yang secara eksplisit menjelaskan definisi prioritas PD11-R2, termasuk acuan Seimbang 15/55/30.",
        "Kumpulkan identitas group responden yang etis dan terpisah dari fitur model, atau tetapkan protokol evaluasi tanpa data itu.",
    ]

    responses, ratings = stringify(responses), stringify(ratings)
    if len(responses) != len(sumber):
        raise ValueError("Jumlah kiriman persiapan tidak sesuai arsip")
    for row in responses + ratings:
        identity = identities.get(row["source_row"])
        if identity is None or row["response_id"] != identity["response_id"]:
            raise ValueError("Kiriman hasil persiapan tidak memiliki identitas yang cocok")
        row["versi_survei"] = manifest["form_version"]
        row.update({key: identity[key] for key in META})
    if len({row["response_id"] for row in responses}) != len(sumber):
        raise ValueError("Kiriman hasil persiapan tidak unik")
    candidate, excluded, candidate_report = bc.buat_kandidat(responses, ratings, report, {})
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


def buat_laporan_pemetaan(report):
    rows = []
    for mapping in report.get("pemetaan_makanan", []):
        rows.append({
            "nama_makanan_survei": mapping["nama_makanan_survei"],
            "nomor_makanan_sumber": mapping["nomor_makanan_sumber"],
            "id_makanan_sumber": mapping["id_makanan_sumber"],
            "id_makanan_katalog": mapping["id_makanan_katalog"],
            "nama_makanan_katalog": mapping["nama_makanan_katalog"],
            "varian": mapping["varian_pemetaan"],
            "porsi": mapping["porsi_katalog"],
            "status_pemetaan": mapping["status_pemetaan"],
            "alasan": mapping["alasan_pemetaan"],
            "status_gizi": mapping["status_pemeriksaan_gizi"],
            "kategori_kalori_PD11_R2": mapping["kategori_kalori_PD11_R2"],
            "kategori_kalori_asli": mapping["kategori_kalori_asli"],
            "versi_dataset_makanan": report["dataset_makanan_version"],
            "versi_survei": report["versi_survei"],
            "id_database_diverifikasi": str(report["id_database_diverifikasi_saat_proses"]),
        })
    return rows

def laporan_markdown(report, candidate_report):
    lines = [
        "# Laporan perapian dataset survei NutriRec",
        "",
        f"- Versi survei: `{report['versi_survei']}`; sumber hash SHA-256 `{report['source_sha256']}`.",
        f"- Katalog makanan: `{report['dataset_makanan_version']}`; hash `{report['dataset_makanan_sumber_hash']}`.",
        f"- Aturan: pemetaan `{report['versi_pemetaan']}`, seleksi `{candidate_report['versi_aturan_seleksi']}`, rekomendasi backend `PD11-R2`.",
        f"- Kiriman: {report['jumlah_kiriman']}; rating source: {report['jumlah_penilaian']}.",
        f"- Pasangan rating diekspor eksploratif: {candidate_report['jumlah_kandidat']}; di antaranya lolos pemeriksaan dasar: {candidate_report['jumlah_kandidat_eksploratif_lolos']}; perlu tinjau: {candidate_report['jumlah_kandidat_eksploratif_perlu_tinjau']}; dikecualikan: {candidate_report['jumlah_dikecualikan']}; partisi eksploratif + dikecualikan = rating sumber.",
        f"- ID respons unik: {report['jumlah_kiriman']}; UID kiriman: {report['jumlah_kiriman']} (tidak membuktikan orang unik).",
        "- Konflik alergi: status tanpa alergi namun bahan terisi ditahan seluruh kiriman; profil sebaliknya juga ditahan jika terjadi.",
        "- Rating 1 tidak digunakan sebagai bukti alergi atau keamanan; 1 tanpa profil alergi ditahan pada pasangan rating terkait.",
        "- Definisi Seimbang survei lama = tanpa prioritas khusus; berbeda dari skor rasio backend 15/55/30. Data/rating asli tidak diubah.",
        f"- Evaluasi PD11-R2: `{report['kelayakan_evaluasi_PD11_R2']}`. Data Seimbang legacy tidak dapat mengevaluasi rasio 15/55/30; diperlukan survei dengan definisi baru dan protokol identitas kelompok yang sesuai.",
        "- Pemetaan nama/nomor Excel bukan bukti kesetaraan resep/porsi. ID database dibaca saja dan dicocokkan pada snapshot; tidak ada impor atau migrasi.",
        f"- Status verifikasi alergi dari katalog: `{report['distribusi_status_verifikasi_alergen_katalog']}`. Semua relasi alergen yang tersedia masih harus ditafsirkan sesuai sumber; rating survei bukan verifikasi keamanan.",
        "- Jawaban identik ditandai, tidak dibuang. Kemungkinan duplikat bukan bukti responden yang sama.",
        "- Alasan pengecualian per kategori dapat tumpang tindih; jumlah baris pengecualian unik adalah jumlah pasangan yang ditahan.",
        "",
        "## Distribusi rating",
        "",
        f"- Sebelum: `{candidate_report['distribusi_sebelum']['rating']}`.",
        f"- Sesudah seleksi eksploratif: `{candidate_report['distribusi_sesudah']['rating']}`.",
        f"- Ditahan/dikecualikan: `{candidate_report['distribusi_dikecualikan']['rating']}`.",
        f"- Pengecualian: `{candidate_report['alasan_pengecualian']}`.",
        "",
        "## Keterbatasan dan keputusan manusia",
        "",
        "- Konfirmasi varian, resep, serta kesepadanan porsi dan konteks saat rating diberikan.",
        "- Jangan menafsirkan pasangan nasi/lauk sebagai makanan yang sama; nasi terpisah tidak digabungkan dengan lauk tanpa bukti.",
        "- Jangan menafsirkan ‘tanpa nasi’ sebagai identitas resep/porsi yang sama tanpa validasi instrumen.",
        "- Dapatkan label/kohort responden yang sah atau rancangan evaluasi kelompok untuk mencegah kebocoran kiriman yang sama.",
        "- Kandidat ini untuk eksplorasi data/fitur saja; tidak disetujui untuk training final.",
    ]
    return "\n".join(lines) + "\n"

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
        database_catalog = baca_database_catalog()
        manifest, responses, ratings, report, candidate, excluded, candidate_report = proses(
            folder, args.foods, database_catalog=database_catalog, database_verified=True
        )
        print(f"Kiriman: {len(responses)}; penilaian: {len(ratings)}; kandidat eksploratif: {len(candidate)}; dikecualikan: {len(excluded)}")
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
            write_csv(processed / "survey_food_mapping.csv", buat_laporan_pemetaan(report), MAP_FIELDS)
            report["source_sha256"] = manifest["source_sha256"]
            report["hash_masukan_sha256"] = {
                "survey_snapshot": digest(folder / "source.xlsx"),
                "identity_sidecar": digest(folder / "submission_identity_map.csv"),
                "ingestion_report": digest(folder / "ingestion_report.json"),
                "survey_manifest": digest(folder / "manifest.json"),
                "food_catalog": digest(args.foods),
            }
            (processed / "survey_validation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            candidate_report["hash_masukan_sha256"] = {"responses": digest(processed / "survey_responses.csv"), "ratings": digest(processed / "survey_ratings_long.csv"), "validation_report": digest(processed / "survey_validation_report.json")}
            candidate_fields = (bc.RATING_FIELDS - {"timestamp"}) | bc.AUDIT_EXTRA_FIELDS | set(META)
            write_csv(output / "survey_candidate.csv", candidate, sorted(candidate_fields))
            write_csv(output / "survey_candidate_exploratory.csv", candidate, sorted(candidate_fields))
            write_csv(output / "survey_excluded.csv", excluded, sorted(candidate_fields | {"alasan_pengecualian"}))
            (output / "survey_candidate_report.json").write_text(json.dumps(candidate_report, indent=2, ensure_ascii=False), encoding="utf-8")
            (output / "survey_candidate_report.md").write_text(laporan_markdown(report, candidate_report), encoding="utf-8")
            result = {"status": "selesai", "run_id": args.run_id, "dataset_version": manifest["dataset_version"], "form_version": manifest["form_version"], "source_namespace": manifest["source_namespace"], "manifest_versi_sha256": digest(folder / "manifest.json"), "source_sha256": digest(folder / "source.xlsx"), "sidecar_sha256": digest(folder / "submission_identity_map.csv"), "foods_sha256": digest(args.foods), "aturan_identitas": vs.ATURAN, "aturan_pemetaan_persiapan": ps.VERSI_PEMETAAN, "aturan_seleksi": bc.VERSI_ATURAN, "jumlah_kiriman": len(responses), "jumlah_penilaian": len(ratings), "jumlah_kandidat": len(candidate), "jumlah_kandidat_eksploratif": len(candidate), "jumlah_kandidat_eksploratif_lolos": candidate_report["jumlah_kandidat_eksploratif_lolos"], "jumlah_kandidat_eksploratif_perlu_tinjau": candidate_report["jumlah_kandidat_eksploratif_perlu_tinjau"], "jumlah_pengecualian": len(excluded), "database_read_only_used": True, "siap_training": False, "output_sha256": {str(p.relative_to(stage)): digest(p) for p in stage.rglob("*") if p.is_file()}}
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
