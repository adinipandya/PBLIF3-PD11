"""Siapkan fitur mentah dan laporan kelayakan; tidak melakukan training atau split."""
import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import prepare_survey as ps
from scripts import build_survey_candidate as bc

VERSION = "fitur-mentah-v1"
ALLERGENS = dict(ps.ALLERGEN_KEYWORD_ID)
FEATURES = ["target_kalori", "prioritas", "status_alergi"] + [f"alergen_{i}" for i in sorted(ALLERGENS.values())] + ["kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g"]
METADATA = ["response_id", "submission_uid", "source_row", "dataset_version", "form_version", "source_namespace", "evaluation_group_id", "nama_makanan_survei", "nama_makanan_dataset", "no_makanan_excel", "rating_asli", "penanda_kiriman", "penanda_penilaian"]


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def foods_data(path):
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if "Dataset" not in wb.sheetnames:
            raise ValueError("Sheet Dataset tidak ditemukan")
        it = iter(wb["Dataset"].values)
        headers = [ps.norm_teks(x).casefold() for x in next(it)]
        required = ["no", "nama makanan", "kalori (kkal)", "protein (g)", "karbo (g)", "lemak (g)", "porsi"]
        if any(headers.count(x) != 1 for x in required):
            raise ValueError("Header makanan, nutrisi atau satuan tidak unik atau tidak ditemukan")
        result, ids = {}, set()
        for number, values in enumerate(it, 2):
            if not any(v is not None for v in values):
                continue
            get = lambda name: values[headers.index(name)]
            no, name = get("no"), ps.norm_teks(get("nama makanan"))
            if isinstance(no, bool) or not isinstance(no, (int, float)) or not math.isfinite(no) or no <= 0 or int(no) != no or int(no) in ids or not name or name.casefold() in result:
                raise ValueError(f"Dataset baris {number}: NO/nama kosong, tidak valid, atau duplikat")
            nutrient = []
            for col in required[2:6]:
                value = get(col)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"Dataset baris {number}: {col} kosong atau tidak valid")
                nutrient.append(value)
            if not ps.norm_teks(get("porsi")):
                raise ValueError(f"Dataset baris {number}: porsi kosong")
            ids.add(int(no)); result[name.casefold()] = {"no": int(no), "nama": name, "nutrisi": nutrient}
        return result
    finally:
        wb.close()


def groups_for(uids, groups):
    parent = {uid: uid for uid in uids}
    def find(uid):
        while parent[uid] != uid:
            uid = parent[uid]
        return uid
    for group in groups:
        members = [uid for uid in group if uid in parent]
        for uid in members[1:]:
            a, b = find(members[0]), find(uid)
            parent[max(a, b)] = min(a, b)
    components = defaultdict(list)
    for uid in sorted(parent): components[find(uid)].append(uid)
    mapping = {}
    for members in components.values():
        gid = "G" + hashlib.sha256("\n".join(members).encode()).hexdigest()[:20]
        for uid in members: mapping[uid] = (gid, "jawaban_identik" if len(members) > 1 else "kiriman_tunggal")
    return mapping


def build(run, foods):
    run = Path(run)
    manifest = json.loads((run / "processing_manifest.json").read_text())
    if manifest.get("status") != "selesai" or manifest.get("siap_training") is not False:
        raise ValueError("Run tidak selesai atau status tidak sesuai")
    paths = ["candidate/survey_candidate.csv", "candidate/survey_candidate_report.json", "processed/survey_responses.csv"]
    for name in paths:
        if manifest.get("output_sha256", {}).get(name) != hash_file(run / name):
            raise ValueError(f"Hash masukan tidak cocok: {name}")
    if hash_file(foods) != manifest.get("foods_sha256"):
        raise ValueError("Hash Excel makanan tidak cocok dengan run")
    _, candidate = bc.baca_csv(run / paths[0], bc.RATING_FIELDS | {"submission_uid", "dataset_version", "form_version", "source_namespace", "target_kalori_asli", "prioritas_asli"})
    _, responses = bc.baca_csv(run / paths[2], bc.RESP_FIELDS | {"submission_uid", "dataset_version", "form_version", "source_namespace"})
    report = json.loads((run / paths[1]).read_text())
    if len(candidate) != manifest.get("jumlah_kandidat") or len(candidate) != report.get("jumlah_kandidat") or len(responses) != manifest.get("jumlah_kiriman"):
        raise ValueError("Jumlah kandidat atau kiriman tidak cocok")
    by_response, by_uid = {}, {}
    for r in responses:
        rid, uid = r["response_id"], r["submission_uid"]
        if not rid or not uid or rid in by_response or uid in by_uid:
            raise ValueError("Identitas kiriman kosong atau duplikat")
        if any(r[k] != manifest.get(k) for k in ("dataset_version", "form_version", "source_namespace")):
            raise ValueError("Metadata versi kiriman tidak cocok")
        by_response[rid] = r; by_uid[uid] = r
    groups = []
    for group in report["kelompok_jawaban_identik_dengan_uid"]:
        members = []
        for member in group:
            r = by_response.get(member["response_id"])
            if r is None or r["submission_uid"] != member["submission_uid"]:
                raise ValueError("Anggota kelompok identik tidak cocok dengan sumber processed")
            members.append(member["submission_uid"])
        groups.append(members)
    foodmap = foods_data(foods)
    candidate_uids = {r["submission_uid"] for r in candidate}
    if not candidate_uids <= set(by_uid): raise ValueError("UID kandidat tidak dikenal")
    # Bentuk komponen atas semua kiriman agar hubungan transitif melalui non-kandidat tidak hilang.
    mapping = groups_for(by_uid, groups)
    output, seen, profiles = [], set(), {}
    for r in candidate:
        uid = r["submission_uid"]; source = by_uid[uid]
        for field in ("response_id", "source_row", "dataset_version", "form_version", "source_namespace", "target_kalori_asli", "prioritas_asli", "alergen_ids"):
            if r[field] != source[field]: raise ValueError(f"Profil/identitas kandidat tidak cocok: {field}")
        if r["status_alergi"] != source["status_alergi_asli"] or r["rating"] not in bc.LABEL or " ".join(r["rating_asli"].split()) != f"{r['rating']} = {bc.LABEL[r['rating']]}" or r["status"] != "lolos_pemeriksaan_dasar":
            raise ValueError("Status, alergi atau rating kandidat tidak valid")
        if not bc.boolean(r["pemetaan_makanan_terkonfirmasi"], uid): raise ValueError("Pemetaan makanan belum dikonfirmasi")
        survey_name = ps.kunci_header_makanan(r["nama_makanan_survei"])
        dataset_name = ps.MAPELANGGAN_MAKANAN_NORMALIZED.get(survey_name)
        food = foodmap.get(dataset_name.casefold()) if dataset_name else None
        if not food or str(food["no"]) != r["id_makanan"] or survey_name == ps.kunci_header_makanan("Capcay Kuah (Ayam)"):
            raise ValueError(f"Pemetaan makanan hilang atau bertentangan: {r['nama_makanan_survei']}")
        key = (uid, food["no"])
        if key in seen: raise ValueError("Pasangan kiriman–makanan duplikat")
        seen.add(key)
        target = ps.TARGET_OPTIONS.get(r["target_kalori_asli"]); priority = ps.PRIORITY_OPTIONS.get(r["prioritas_asli"])
        if not target or not priority or r["status_alergi"] not in ps.STATUS_ALLERGI: raise ValueError("Profil tidak dikenal")
        ids = r["alergen_ids"].split(";") if r["alergen_ids"] else []
        if len(ids) != len(set(ids)) or any(i not in {str(n) for n in ALLERGENS.values()} for i in ids): raise ValueError("ID alergen tidak dikenal")
        nama_prioritas = r["prioritas_asli"] if priority["nama"] == "Seimbang" else priority["nama"]
        profile = (target["nama"], nama_prioritas, r["status_alergi"], tuple(ids))
        if uid in profiles and profiles[uid] != profile: raise ValueError("Profil UID tidak konsisten")
        profiles[uid] = profile
        features = {"target_kalori": target["nama"], "prioritas": nama_prioritas, "status_alergi": ps.STATUS_ALLERGI[r["status_alergi"]]}
        features.update({f"alergen_{i}": int(str(i) in ids) for i in sorted(ALLERGENS.values())})
        features.update(dict(zip(("kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g"), food["nutrisi"])))
        metadata = {k: r[k] for k in ("response_id", "submission_uid", "source_row", "dataset_version", "form_version", "source_namespace", "nama_makanan_survei", "rating_asli", "penanda_kiriman", "penanda_penilaian")}
        metadata.update(evaluation_group_id=mapping[uid][0], nama_makanan_dataset=food["nama"], no_makanan_excel=food["no"])
        output.append({**features, "y": int(r["rating"]), **metadata})
    group_rows = [{"submission_uid": uid, "evaluation_group_id": mapping[uid][0], "alasan": mapping[uid][1]} for uid in sorted(candidate_uids)]
    class_groups = {str(i): sorted({r["evaluation_group_id"] for r in output if r["y"] == i}) for i in range(1, 5)}
    class_uids = {str(i): sorted({r["submission_uid"] for r in output if r["y"] == i}) for i in range(1, 5)}
    class_counts = {str(i): sum(r["y"] == i for r in output) for i in range(1, 5)}
    profile_counts = {}
    for field in ("target_kalori", "prioritas", "status_alergi"):
        profile_counts[field] = {"uid": dict(Counter(next(r[field] for r in output if r["submission_uid"] == uid) for uid in candidate_uids)), "kelompok": {str(value): len({r["evaluation_group_id"] for r in output if r[field] == value}) for value in {r[field] for r in output}}}
    feasibility = {"jumlah_baris": len(output), "jumlah_uid": len(candidate_uids), "jumlah_makanan": len({r["no_makanan_excel"] for r in output}), "jumlah_kelompok": len({r["evaluation_group_id"] for r in output}), "distribusi_kelas_penilaian": class_counts, "distribusi_kelas_uid": {k: len(v) for k, v in class_uids.items()}, "distribusi_kelas_kelompok": {k: len(v) for k, v in class_groups.items()}, "kelompok_per_kelas": class_groups, "uid_per_kelas": class_uids, "distribusi_profil": profile_counts, "batas_maksimum_fold_dengan_semua_kelas_pada_test": min(map(len, class_groups.values())), "catatan": ["Grouped cross-validation mungkin dilakukan jika jumlah kelompok memadai, tetapi tidak menjamin semua kelas di setiap fold.", "Jumlah kelompok per kelas membatasi jumlah fold test yang dapat memuat setiap kelas; kelayakan aktual perlu diperiksa.", f"Prioritas Lemak memiliki {profile_counts['prioritas']['uid'].get('Lemak', 0)} kiriman; generalisasi kelompok perlu dievaluasi.", "Kelompok jawaban identik bukan bukti identitas orang.", "Pemetaan diverifikasi ke NO dan nama Excel, bukan primary key database."]}
    return manifest, output, group_rows, feasibility


PLAN = """# Rancangan eksperimen\n\nSasaran: prediksi kiriman baru untuk katalog makanan dikenal. Pembagian berdasarkan kiriman tidak menguji makanan baru.\n\nBandingkan Dummy baseline, Decision Tree, Random Forest dan KNN. Laporkan klasifikasi per kelas, macro-F1 dengan label tetap [1,2,3,4], confusion matrix, MAE dan support. Jelaskan kelas yang tidak muncul pada fold.\n\nGunakan grouped cross-validation dengan kelompok identik bersama; semua preprocessing yang belajar dari data di-fit hanya pada data latih setiap fold. Tuning memakai pembagian kelompok di dalam data latih, bukan evaluasi luar. Ranking Top 3 dan penggabungan content-based/ML adalah tahap terpisah. Tidak ada split atau pelatihan pada tahap ini.\n"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("run-dir", "foods", "output-dir"): parser.add_argument("--" + field, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        target = Path(args.output_dir)
        if target.exists(): raise ValueError("Direktori keluaran sudah ada; tidak boleh ditimpa")
        manifest, rows, groups, report = build(args.run_dir, args.foods)
        print(f"Baris: {len(rows)}; UID: {report['jumlah_uid']}; kelompok: {report['jumlah_kelompok']}; kelas 1 pada {report['distribusi_kelas_kelompok']['1']} kelompok")
        if args.dry_run:
            print("DRY RUN: tidak menulis berkas")
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".fitur-stage-", dir=target.parent))
        try:
            for filename, data, fields in (("ml_feature_table.csv", rows, FEATURES + ["y"] + METADATA), ("evaluation_groups.csv", groups, ["submission_uid", "evaluation_group_id", "alasan"])):
                with (stage / filename).open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(data)
            schema = {"fitur_diizinkan": FEATURES, "target": {"y": "rating kesesuaian 1–4"}, "metadata_bukan_fitur": METADATA, "kategori": {"target_kalori": ["Rendah", "Sedang", "Tinggi"], "prioritas": ["Protein", "Karbohidrat", "Lemak", "Seimbang (tidak ada prioritas khusus)"]}, "kamus_alergen_id": ALLERGENS, "satuan": {"kalori_kkal": "kkal/porsi", "protein_g": "g/porsi", "karbohidrat_g": "g/porsi", "lemak_g": "g/porsi"}, "tipe": {"kategori": FEATURES[:2], "boolean": ["status_alergi"], "indikator_biner": [f"alergen_{i}" for i in sorted(ALLERGENS.values())], "numerik": FEATURES[-4:]}, "preprocessing": "Encoder/scaler/imputasi hanya fit pada data latih tiap fold."}
            (stage / "feature_schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False))
            (stage / "evaluation_feasibility_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
            (stage / "experiment_plan.md").write_text(PLAN)
            m = {"status": "fitur_eksperimen", "siap_training": False, "versi_aturan_fitur": VERSION, "dataset_version": manifest["dataset_version"], "run_id": manifest["run_id"], "jumlah_baris": len(rows), "masukan_sha256": {"processing_manifest": hash_file(Path(args.run_dir) / "processing_manifest.json"), "candidate": hash_file(Path(args.run_dir) / "candidate/survey_candidate.csv"), "candidate_report": hash_file(Path(args.run_dir) / "candidate/survey_candidate_report.json"), "responses": hash_file(Path(args.run_dir) / "processed/survey_responses.csv"), "foods": hash_file(args.foods)}, "output_sha256": {p.name: hash_file(p) for p in stage.iterdir()}}
            (stage / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False))
            if target.exists(): raise ValueError("Direktori keluaran sudah ada")
            os.rename(stage, target)
        finally:
            if stage.exists(): shutil.rmtree(stage)
        print(f"Hasil: {target}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
