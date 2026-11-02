"""Seleksi data persiapan survei offline; bukan persetujuan pelatihan ML."""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERSI_ATURAN = "kandidat-survei-1"
RESP_FIELDS = {"response_id", "source_row", "target_kalori_asli", "target_kalori_id", "prioritas_asli", "prioritas_id", "status_alergi_asli", "alergen_asli", "alergen_ids", "penanda", "tahan_seluruh_kiriman"}
RATING_FIELDS = {"response_id", "source_row", "target_kalori_id", "prioritas_id", "status_alergi", "alergen_ids", "nama_makanan_survei", "id_makanan", "pemetaan_makanan_terkonfirmasi", "rating_asli", "rating", "penanda", "penanda_kiriman", "penanda_penilaian", "status", "alasan_tahan"}
PROFILE_NAMES = {
    "target_kalori_asli": "Berapa target kalori Anda untuk satu kali makan?",
    "prioritas_asli": "Nutrisi apa yang paling Anda prioritaskan pada makanan?",
    "status_alergi_asli": "Apakah Anda memiliki alergi terhadap makanan?",
}
TARGET = {"Rendah (< 300 kkal)": "1", "Sedang (300-500 kkal)": "2", "Tinggi (> 500 kkal)": "3"}
PRIORITAS = {"Protein tinggi": "1", "Karbohidrat tinggi": "2", "Lemak tinggi": "3", "Seimbang (tidak ada prioritas khusus)": "4"}
STATUS_ALERGI = {"Tidak ada alergi", "Ya, memiliki alergi"}
STATUS = {"lolos_pemeriksaan_dasar", "perlu_tinjau", "kosong", "tidak_valid"}
KONFLIK_TANPA = "konflik_tanpa_alergi_dengan_pilihan"
KONFLIK_DENGAN = "konflik_alergi_tanpa_pilihan"
RATING_SATU = "rating_1_tanpa_alergi"
PENANDA_TAHAN = {KONFLIK_TANPA, KONFLIK_DENGAN, RATING_SATU,
                 "profil_kosong", "profil_tidak_dikenal", "alergen_tidak_dikenal"}
LABEL = {
    "1": "Sangat tidak sesuai (karena mengandung bahan yang membuat saya alergi)",
    "2": "Tidak sesuai (agak jauh dari target)",
    "3": "Sesuai (hampir sesuai target)",
    "4": "Sangat sesuai (sesuai target)",
}


class SumberTidakValid(ValueError):
    pass


def baca_csv(path, fields):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        header = reader.fieldnames
        if not header or len(header) != len(set(header)) or not fields.issubset(header):
            raise SumberTidakValid(f"{path}: header duplikat atau kolom wajib hilang: {sorted(fields - set(header or []))}")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise SumberTidakValid(f"{path}: jumlah kolom tidak sesuai header")
        return header, rows


def boolean(value, lokasi):
    if value == "True":
        return True
    if value == "False":
        return False
    raise SumberTidakValid(f"{lokasi}: boolean tidak valid: {value!r}")


def integer_positif(value, lokasi):
    if not re.fullmatch(r"[1-9][0-9]*", value or ""):
        raise SumberTidakValid(f"{lokasi}: bilangan bulat positif tidak valid: {value!r}")


def distribusi(rows, fields):
    return {field: dict(Counter(row[field] or "(kosong)" for row in rows)) for field in fields}


def penanda(value):
    return {item.strip() for item in value.split(";") if item.strip()}


def validasi(responses, ratings, report):
    if not isinstance(report, dict) or not isinstance(report.get("kesalahan"), list) or report["kesalahan"] or report.get("nilai_tidak_valid_per_kolom") != {} or report.get("nilai_kosong_per_kolom") != {}:
        raise SumberTidakValid("Laporan memuat kesalahan/nilai tidak valid atau format laporan tidak lengkap")
    by_id = {}
    for row in responses:
        rid = row["response_id"]
        if not rid or rid in by_id:
            raise SumberTidakValid(f"response_id kosong atau duplikat: {rid!r}")
        integer_positif(row["source_row"], rid)
        lokasi = f"response_id={rid}, source_row={row['source_row']}"
        ditahan = boolean(row["tahan_seluruh_kiriman"], lokasi)
        if TARGET.get(row["target_kalori_asli"]) != row["target_kalori_id"] or PRIORITAS.get(row["prioritas_asli"]) != row["prioritas_id"] or row["status_alergi_asli"] not in STATUS_ALERGI:
            raise SumberTidakValid(f"{rid}: profil kosong, tidak dikenal, atau ID tidak cocok")
        ids = row["alergen_ids"].split(";") if row["alergen_ids"] else []
        if len(ids) != len(set(ids)) or any(i not in {str(n) for n in range(1, 12)} for i in ids):
            raise SumberTidakValid(f"{rid}: alergen_ids tidak valid")
        flags = penanda(row["penanda"])
        tersedia = bool(row["alergen_asli"].strip() or row["alergen_ids"].strip())
        konflik = (KONFLIK_TANPA if row["status_alergi_asli"] == "Tidak ada alergi" and tersedia
                   else KONFLIK_DENGAN if row["status_alergi_asli"] == "Ya, memiliki alergi" and not tersedia
                   else None)
        if konflik and (not ditahan or konflik not in flags):
            raise SumberTidakValid(f"{lokasi}: konflik {konflik} wajib ditahan dan memiliki penanda")
        if flags.intersection({KONFLIK_TANPA, KONFLIK_DENGAN}) and not ditahan:
            raise SumberTidakValid(f"{lokasi}: penanda konflik tersedia tetapi kiriman tidak ditahan")
        by_id[rid] = row
    seen = set()
    for index, row in enumerate(ratings, 2):
        rid = row["response_id"]
        if rid not in by_id:
            raise SumberTidakValid(f"Penilaian baris {index}: response_id tidak ditemukan: {rid}")
        resp = by_id[rid]
        lokasi = f"response_id={rid}, source_row={row['source_row']}, makanan={row['nama_makanan_survei']!r}"
        for key, resp_key in (("source_row", "source_row"), ("target_kalori_id", "target_kalori_id"), ("prioritas_id", "prioritas_id"), ("status_alergi", "status_alergi_asli"), ("alergen_ids", "alergen_ids"), ("penanda_kiriman", "penanda")):
            if row[key] != resp[resp_key]:
                raise SumberTidakValid(f"Penilaian baris {index}: {key} tidak cocok dengan kiriman {rid}")
        nama = " ".join(re.sub(r"^\s*\d+\.\s*", "", row["nama_makanan_survei"]).casefold().split())
        key = (rid, nama)
        if not nama or key in seen:
            raise SumberTidakValid(f"Penilaian baris {index}: makanan kosong atau pasangan duplikat")
        seen.add(key)
        boolean(row["pemetaan_makanan_terkonfirmasi"], f"penilaian {index}")
        if row["id_makanan"]:
            integer_positif(row["id_makanan"], f"penilaian {index}")
        if row["status"] not in STATUS:
            raise SumberTidakValid(f"Penilaian baris {index}: status tidak dikenal")
        rating = row["rating"]
        raw = row["rating_asli"]
        if rating not in LABEL or " ".join(raw.split()) != f"{rating} = {LABEL.get(rating, '')}":
            raise SumberTidakValid(f"Penilaian baris {index}: rating kosong, tidak valid, atau tidak cocok label")
        if row["status"] in {"kosong", "tidak_valid"}:
            raise SumberTidakValid(f"Penilaian baris {index}: status rating tidak valid")
        alasan = penanda(row["alasan_tahan"])
        flags_rating = penanda(row["penanda"]) | penanda(row["penanda_penilaian"])
        flags_all = flags_rating | penanda(row["penanda_kiriman"])
        if row["status"] == "lolos_pemeriksaan_dasar":
            if boolean(resp["tahan_seluruh_kiriman"], lokasi):
                raise SumberTidakValid(f"{lokasi}: kiriman tertahan tetapi rating lolos")
            if row["alasan_tahan"].strip():
                raise SumberTidakValid(f"{lokasi}: status lolos memiliki alasan_tahan")
            if flags_all & PENANDA_TAHAN:
                raise SumberTidakValid(f"{lokasi}: status lolos bertentangan dengan penanda penahanan {sorted(flags_all & PENANDA_TAHAN)}")
        if row["status"] == "perlu_tinjau" and not row["alasan_tahan"].strip():
            raise SumberTidakValid(f"{lokasi}: perlu_tinjau tanpa alasan_tahan")
        if resp["status_alergi_asli"] == "Tidak ada alergi" and rating == "1":
            if row["status"] != "perlu_tinjau" or RATING_SATU not in flags_rating or RATING_SATU not in alasan:
                raise SumberTidakValid(f"{lokasi}: rating 1 tanpa alergi wajib perlu_tinjau dengan penanda dan alasan {RATING_SATU}")
    checks = {
        "jumlah_kiriman": len(responses), "jumlah_penilaian": len(ratings),
        "status_penilaian": dict(Counter(r["status"] for r in ratings)),
        "rating": dict(Counter(r["rating"] for r in ratings)),
        "distribusi_profil": {label: dict(Counter(r[field] or "(kosong)" for r in responses)) for field, label in PROFILE_NAMES.items()},
    }
    for key, value in checks.items():
        if report.get(key) != value:
            raise SumberTidakValid(f"Laporan tidak cocok dengan CSV: {key}")
    return by_id


def buat_kandidat(responses, ratings, report, hashes):
    by_id = validasi(responses, ratings, report)
    candidate, excluded = [], []
    counts, affected = Counter(), defaultdict(set)
    for item in ratings:
        resp = by_id[item["response_id"]]
        reasons = []
        if boolean(resp["tahan_seluruh_kiriman"], "tahan"):
            reasons.append("tahan_seluruh_kiriman")
        if item["status"] != "lolos_pemeriksaan_dasar":
            reasons.append("status_bukan_lolos_pemeriksaan_dasar")
        if item["rating"] not in LABEL:
            reasons.append("rating_tidak_valid")
        if item["target_kalori_id"] not in TARGET.values() or item["prioritas_id"] not in PRIORITAS.values() or item["status_alergi"] not in STATUS_ALERGI:
            reasons.append("profil_tidak_valid")
        if not item["id_makanan"]:
            reasons.append("id_makanan_kosong")
        if not boolean(item["pemetaan_makanan_terkonfirmasi"], "pemetaan"):
            reasons.append("pemetaan_makanan_belum_dikonfirmasi")
        if "pemetaan_makanan_belum_dikonfirmasi" in (item["penanda"] + ";" + item["penanda_kiriman"] + ";" + item["penanda_penilaian"]).split(";"):
            reasons.append("penanda_pemetaan_belum_dikonfirmasi")
        merged = {key: value for key, value in item.items() if key != "timestamp"}
        for field in ("target_kalori_asli", "prioritas_asli", "status_alergi_asli", "alergen_asli", "tahan_seluruh_kiriman"):
            merged[field] = resp[field]
        merged["penanda_kiriman_asli"] = resp["penanda"]
        if reasons:
            merged["alasan_pengecualian"] = ";".join(reasons)
            excluded.append(merged)
            for reason in reasons:
                counts[reason] += 1
                affected[reason].add(item["response_id"])
        else:
            candidate.append(merged)
    ids_candidate = {r["response_id"] for r in candidate}
    result = {
        "status_dataset": "kandidat_eksperimen", "siap_training": False,
        "versi_aturan_seleksi": VERSI_ATURAN, "hash_masukan_sha256": hashes,
        "jumlah_kiriman_sumber": len(responses), "jumlah_penilaian_sumber": len(ratings),
        "jumlah_kandidat": len(candidate), "jumlah_dikecualikan": len(excluded),
        "jumlah_gabungan_dikecualikan": len(excluded),
        "jumlah_kiriman_kandidat": len(ids_candidate),
        "jumlah_kiriman_seluruhnya_dikecualikan": len(set(by_id) - ids_candidate),
        "alasan_pengecualian": {key: {"penilaian": counts[key], "kiriman_unik": len(affected[key])} for key in counts},
        "distribusi_sebelum": {"rating": dict(Counter(r["rating"] for r in ratings)), "profil_kiriman": distribusi(responses, PROFILE_NAMES)},
        "distribusi_sesudah": {"rating": dict(Counter(r["rating"] for r in candidate)), "profil_penilaian": distribusi(candidate, PROFILE_NAMES), "profil_kiriman": distribusi([r for r in responses if r["response_id"] in ids_candidate], PROFILE_NAMES)},
        "kelompok_jawaban_identik_dalam_kandidat": [[rid for rid in group if rid in ids_candidate] for group in report.get("kelompok_jawaban_identik", []) if sum(rid in ids_candidate for rid in group) >= 2],
        "keputusan_seleksi": "Hanya lolos dasar, profil dan rating valid, kiriman tidak ditahan, serta ID dan pemetaan makanan terkonfirmasi; alasan dapat tumpang tindih.",
        "keterbatasan": ["Seimbang berarti tidak ada prioritas khusus, bukan rasio backend.", "Kecocokan ID backend belum diverifikasi; NO Excel bukan bukti PK aktual.", "Ketimpangan kelompok perlu dievaluasi.", "Jawaban identik dapat menunjukkan pengisian berulang, bukan bukti pasti.", "Kandidat belum merupakan persetujuan pelatihan."],
    }
    assert len(candidate) + len(excluded) == len(ratings)
    return candidate, excluded, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("responses", "ratings", "validation-report", "output-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = [Path(args.responses), Path(args.ratings), Path(args.validation_report)]
        output = Path(args.output_dir)
        destinations = [output / n for n in ("survey_candidate.csv", "survey_excluded.csv", "survey_candidate_report.json")]
        if set(p.resolve() for p in paths) & set(p.resolve() for p in destinations):
            raise SumberTidakValid("Keluaran tidak boleh menimpa masukan")
        _, responses = baca_csv(paths[0], RESP_FIELDS)
        rating_header, ratings = baca_csv(paths[1], RATING_FIELDS)
        report = json.loads(paths[2].read_text(encoding="utf-8-sig"))
        hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in zip(("responses", "ratings", "validation_report"), paths)}
        candidate, excluded, result = buat_kandidat(responses, ratings, report, hashes)
        print(f"Kiriman: {len(responses)}; penilaian: {len(ratings)}; kandidat: {len(candidate)}; dikecualikan: {len(excluded)}")
        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=True)
            fields = [field for field in rating_header if field != "timestamp"] + ["target_kalori_asli", "prioritas_asli", "status_alergi_asli", "alergen_asli", "tahan_seluruh_kiriman", "penanda_kiriman_asli"]
            for path, rows, columns in ((destinations[0], candidate, fields), (destinations[1], excluded, fields + ["alasan_pengecualian"])):
                with path.open("w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
            destinations[2].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Keluaran: {output}")
        else:
            print("DRY RUN: tidak ada berkas ditulis.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Sumber tidak valid: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
