"""Seleksi data persiapan survei offline; bukan persetujuan pelatihan ML."""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERSI_ATURAN = "candidate-survey-2"
RESP_FIELDS = {"response_id", "source_row", "versi_survei", "versi_dataset_makanan", "target_kalori_asli", "target_kalori_id", "prioritas_asli", "prioritas_id", "definisi_prioritas", "status_alergi_asli", "status_alergi_normalisasi", "alergen_asli", "alergen_normalisasi", "alergen_ids", "alergen_ids_normalisasi", "alergen_token_tidak_dikenal", "penanda", "tahan_seluruh_kiriman"}
RATING_FIELDS = {"response_id", "source_row", "versi_survei", "versi_dataset_makanan", "target_kalori_asli", "target_kalori_id", "prioritas_asli", "prioritas_id", "definisi_prioritas", "status_alergi", "status_alergi_asli", "status_alergi_normalisasi", "alergen_asli", "alergen_normalisasi", "alergen_ids", "nama_makanan_survei", "id_makanan_sumber", "id_makanan", "id_makanan_katalog", "nama_makanan_katalog", "varian_pemetaan", "porsi_katalog", "status_pemetaan", "alasan_pemetaan", "kalori_katalog", "protein_katalog", "karbohidrat_katalog", "lemak_katalog", "kategori_kalori_asli", "kategori_kalori_PD11_R2", "alasan_pemeriksaan_gizi", "alergen_katalog_asli", "status_alergen_katalog_asli", "status_pemeriksaan_gizi", "pemetaan_makanan_terkonfirmasi", "rating_asli", "rating_label_asli", "rating", "penanda", "penanda_kiriman", "penanda_penilaian", "status", "status_pemeriksaan", "alasan_tahan", "alasan_penahanan"}
AUDIT_EXTRA_FIELDS = {"versi_survei", "versi_dataset_makanan", "target_kalori_asli", "prioritas_asli", "definisi_prioritas", "status_alergi_asli", "status_alergi_normalisasi", "alergen_asli", "alergen_normalisasi", "alergen_ids_normalisasi", "alergen_token_tidak_dikenal", "id_makanan_sumber", "id_makanan_katalog", "nama_makanan_katalog", "varian_pemetaan", "porsi_katalog", "status_pemetaan", "alasan_pemetaan", "kalori_katalog", "protein_katalog", "karbohidrat_katalog", "lemak_katalog", "kategori_kalori_asli", "kategori_kalori_PD11_R2", "alasan_pemeriksaan_gizi", "alergen_katalog_asli", "status_alergen_katalog_asli", "status_pemeriksaan_gizi", "status_pemeriksaan", "alasan_penahanan", "rating_label_asli"}
PROFILE_NAMES = {
    "target_kalori_asli": "Berapa target kalori Anda untuk satu kali makan?",
    "prioritas_asli": "Nutrisi apa yang paling Anda prioritaskan pada makanan?",
    "status_alergi_asli": "Apakah Anda memiliki alergi terhadap makanan?",
}
TARGET = {"Rendah (< 300 kkal)": "1", "Sedang (300-500 kkal)": "2", "Tinggi (> 500 kkal)": "3"}
PRIORITAS = {"Protein tinggi": "1", "Karbohidrat tinggi": "2", "Lemak tinggi": "3", "Seimbang (tidak ada prioritas khusus)": "4"}
STATUS_ALERGI = {"Tidak ada alergi", "Ya, memiliki alergi"}
VERSI_INSTRUMEN = "legacy-v1"
DEFINISI_SEIMBANG_LEGACY = "tanpa_prioritas_khusus_survei_legacy"
ALLERGEN_CANONICAL = {1: "telur", 2: "kedelai", 3: "jagung", 4: "kelapa", 5: "ayam", 6: "daging sapi", 7: "gandum", 8: "kacang-kacangan", 9: "udang/seafood", 10: "ikan", 11: "beras"}
STATUS = {"lolos_pemeriksaan_dasar", "perlu_tinjau", "kosong", "tidak_valid"}
KONFLIK_TANPA = "konflik_tanpa_alergi_dengan_pilihan"
KONFLIK_DENGAN = "konflik_alergi_tanpa_pilihan"
RATING_SATU = "rating_1_tanpa_alergi"
PENANDA_PEMETAAN = "pemetaan_makanan_belum_dikonfirmasi"
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
        if not row.get("versi_survei"):
            raise SumberTidakValid(f"{rid}: versi instrumen kosong")
        if row.get("versi_survei") != VERSI_INSTRUMEN and row["prioritas_asli"] == "Seimbang (tidak ada prioritas khusus)" and row["definisi_prioritas"] != DEFINISI_SEIMBANG_LEGACY:
            raise SumberTidakValid(f"{rid}: validator untuk definisi prioritas ini belum didefinisikan")
        if not row.get("versi_dataset_makanan"):
            raise SumberTidakValid(f"{rid}: versi katalog makanan kosong")
        lokasi = f"response_id={rid}, source_row={row['source_row']}"
        ditahan = boolean(row["tahan_seluruh_kiriman"], lokasi)
        if TARGET.get(row["target_kalori_asli"]) != row["target_kalori_id"] or PRIORITAS.get(row["prioritas_asli"]) != row["prioritas_id"] or row["status_alergi_normalisasi"] not in STATUS_ALERGI:
            raise SumberTidakValid(f"{rid}: profil kosong, tidak dikenal, atau ID tidak cocok")
        if row["definisi_prioritas"] != (DEFINISI_SEIMBANG_LEGACY if row["prioritas_asli"] == "Seimbang (tidak ada prioritas khusus)" else "pilihan_prioritas_zat_gizi_survei_legacy"):
            raise SumberTidakValid(f"{rid}: profil kosong, tidak dikenal, atau ID tidak cocok")
        ids = row["alergen_ids_normalisasi"].split(";") if row["alergen_ids_normalisasi"] else []
        normalized_names = row["alergen_normalisasi"].split(";") if row["alergen_normalisasi"] else []
        if any(not i.isdigit() or not 1 <= int(i) <= 11 for i in ids):
            raise SumberTidakValid(f"{rid}: alergen_ids normalisasi tidak valid")
        if normalized_names != [ALLERGEN_CANONICAL[int(i)] for i in ids]:
            raise SumberTidakValid(f"{rid}: nama alergen normalisasi tidak cocok dengan ID")
        if len(ids) != len(set(ids)) or any(i not in {str(n) for n in range(1, 12)} for i in ids):
            raise SumberTidakValid(f"{rid}: alergen_ids normalisasi tidak valid")
        flags = penanda(row["penanda"])
        tersedia = bool(ids or row["alergen_token_tidak_dikenal"].strip())
        normalized_status = row["status_alergi_normalisasi"]
        konflik = (KONFLIK_TANPA if normalized_status == "Tidak ada alergi" and tersedia
                   else KONFLIK_DENGAN if normalized_status == "Ya, memiliki alergi" and not tersedia
                   else None)
        if konflik and (not ditahan or konflik not in flags):
            raise SumberTidakValid(f"{lokasi}: konflik {konflik} wajib ditahan dan memiliki penanda")
        if flags.intersection({KONFLIK_TANPA, KONFLIK_DENGAN}) and not ditahan:
            raise SumberTidakValid(f"{lokasi}: penanda konflik tersedia tetapi kiriman tidak ditahan")
        by_id[rid] = row
    seen = set()
    seen_source_food = set()
    duplicate_source_pairs = set()
    for index, row in enumerate(ratings, 2):
        missing_audit = not AUDIT_EXTRA_FIELDS.issubset(row)
        if missing_audit:
            raise SumberTidakValid(f"Penilaian baris {index}: kolom audit/pemetaan versi baru tidak lengkap")
        rid = row["response_id"]
        if rid not in by_id:
            raise SumberTidakValid(f"Penilaian baris {index}: response_id tidak ditemukan: {rid}")
        resp = by_id[rid]
        lokasi = f"response_id={rid}, source_row={row['source_row']}, makanan={row['nama_makanan_survei']!r}"
        for key, resp_key in (("source_row", "source_row"), ("target_kalori_id", "target_kalori_id"), ("prioritas_id", "prioritas_id"), ("status_alergi_asli", "status_alergi_asli"), ("status_alergi_normalisasi", "status_alergi_normalisasi"), ("alergen_asli", "alergen_asli"), ("alergen_normalisasi", "alergen_normalisasi"), ("alergen_ids", "alergen_ids"), ("penanda_kiriman", "penanda")):
            if row[key] != resp[resp_key]:
                raise SumberTidakValid(f"Penilaian baris {index}: {key} tidak cocok dengan kiriman {rid}")
        nama = " ".join(re.sub(r"^\s*\d+\.\s*", "", row["nama_makanan_survei"]).casefold().split())
        key = (rid, nama)
        if not nama or key in seen:
            raise SumberTidakValid(f"Penilaian baris {index}: makanan kosong atau pasangan duplikat")
        seen.add(key)
        source_food_key = (row["source_row"], row["id_makanan_sumber"])
        if row["id_makanan_sumber"] and source_food_key in seen_source_food:
            duplicate_source_pairs.add(source_food_key)
        seen_source_food.add(source_food_key)
        boolean(row["pemetaan_makanan_terkonfirmasi"], f"penilaian {index}")
        if row["id_makanan_sumber"]:
            integer_positif(row["id_makanan_sumber"], f"penilaian {index}")
        if row["id_makanan_katalog"] and row["status_pemetaan"] in {"ditahan_varian_belum_jelas", "ditahan_porsi_varian_belum_jelas", "ditahan_katalog_database_tidak_sama", "ditahan_tidak_ada_pemetaan", "ditahan_katalog_tidak_ditemukan"}:
            raise SumberTidakValid(f"Penilaian baris {index}: ID katalog terisi meski status pemetaan ditahan")
        if row["id_makanan_katalog"]:
            integer_positif(row["id_makanan_katalog"], f"penilaian {index}")
        if row["id_makanan"] != row["id_makanan_katalog"]:
            raise SumberTidakValid(f"Penilaian baris {index}: id_makanan bukan alias ID katalog")
        if row["status_pemetaan"] not in {
            "id_database_cocok_nama_porsi_perlu_review",
            "id_database_cocok_porsi_relasi_transaksi_perlu_review",
        } and row["id_makanan_katalog"]:
            raise SumberTidakValid(f"Penilaian baris {index}: ID katalog diisi untuk status pemetaan tertahan")
        if row["status"] not in STATUS:
            raise SumberTidakValid(f"Penilaian baris {index}: status tidak dikenal")
        if row["status_pemeriksaan_gizi"] != "valid":
            raise SumberTidakValid(f"Penilaian baris {index}: status pemeriksaan gizi tidak valid")
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
        if resp["status_alergi_asli"] == "Tidak ada alergi" and resp["status_alergi_normalisasi"] == "Tidak ada alergi" and rating == "1":
            if row["status"] != "perlu_tinjau" or RATING_SATU not in flags_rating or RATING_SATU not in alasan:
                raise SumberTidakValid(f"{lokasi}: rating 1 tanpa alergi wajib perlu_tinjau dengan penanda dan alasan {RATING_SATU}")
    response_ids = [r["response_id"] for r in responses]
    source_rows = [r["source_row"] for r in responses]
    if len(source_rows) != len(set(source_rows)):
        raise SumberTidakValid("source_row duplikat")
    report["jumlah_rating_duplikat_pasangan"] = len(duplicate_source_pairs)
    conflicts = {}
    for row in responses:
        ids = row["alergen_ids_normalisasi"].split(";") if row["alergen_ids_normalisasi"] else []
        unknown = [x for x in row["alergen_token_tidak_dikenal"].split(";") if x]
        status = row["status_alergi_normalisasi"]
        expected = (KONFLIK_TANPA if status == "Tidak ada alergi" and (ids or unknown)
                    else KONFLIK_DENGAN if status == "Ya, memiliki alergi" and not (ids or unknown)
                    else None)
        actual = penanda(row["penanda"])
        if expected and (not boolean(row["tahan_seluruh_kiriman"], row["response_id"]) or expected not in actual):
            raise SumberTidakValid(f"{row['response_id']}: konflik alergi tidak ditahan sesuai sumber")
        conflicts[row["response_id"]] = expected
    if report.get("jumlah_rating_duplikat_pasangan") not in (None, 0):
        raise SumberTidakValid("Pasangan respons–makanan duplikat: pertahankan semua baris sumber untuk review; jangan deduplikasi diam-diam")
    checks = {
        "jumlah_kiriman": len(responses), "jumlah_penilaian": len(ratings),
        "status_penilaian": dict(Counter(r["status"] for r in ratings)),
        "jumlah_kiriman_konflik_profil": sum(value is not None for value in conflicts.values()),
        "status_kiriman": {"jumlah": len(responses), "konflik_alergi": sum(any(flag in penanda(r["penanda"]) for flag in (KONFLIK_TANPA, KONFLIK_DENGAN)) for r in responses)},
        "status_pemetaan": report.get("status_pemetaan", {}),
        "duplikasi_pasangan": len(duplicate_source_pairs),
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
    source_pairs = len(ratings)
    conflicts = {}
    for response in responses:
        ids = response["alergen_ids_normalisasi"].split(";") if response["alergen_ids_normalisasi"] else []
        unknown = [value for value in response["alergen_token_tidak_dikenal"].split(";") if value]
        status = response["status_alergi_normalisasi"]
        conflicts[response["response_id"]] = (
            KONFLIK_TANPA if status == "Tidak ada alergi" and (ids or unknown)
            else KONFLIK_DENGAN if status == "Ya, memiliki alergi" and not (ids or unknown)
            else None
        )
    for item in ratings:
        resp = by_id[item["response_id"]]
        reasons = []
        if boolean(resp["tahan_seluruh_kiriman"], "tahan"):
            reasons.append("tahan_seluruh_kiriman")
        if resp["status_alergi_asli"] != resp["status_alergi_normalisasi"]:
            reasons.append("profil_alergi_membutuhkan_tinjauan_manual")
        if item["status"] != "lolos_pemeriksaan_dasar":
            reasons.append("status_bukan_lolos_pemeriksaan_dasar")
        if item["rating"] not in LABEL:
            reasons.append("rating_tidak_valid")
        if item["target_kalori_id"] not in TARGET.values() or item["prioritas_id"] not in PRIORITAS.values() or item["status_alergi"] not in STATUS_ALERGI:
            reasons.append("profil_tidak_valid")
        if not item["id_makanan_katalog"]:
            reasons.append("id_makanan_katalog_kosong")
        reasons_main = []
        if item["status_pemetaan"] != "pemetaan_semantik_dan_porsi_terkonfirmasi":
            reasons_main.append("pemetaan_resep_varian_porsi_belum_dikonfirmasi")
        if item["definisi_prioritas"] == DEFINISI_SEIMBANG_LEGACY:
            reasons_main.append("makna_seimbang_survei_legacy_tidak_sebanding_dengan_backend_PD11_R2")
        if item["status_pemeriksaan_gizi"] != "valid":
            reasons.append("data_gizi_katalog_tidak_valid")
        merged = {key: value for key, value in item.items() if key != "timestamp"}
        merged["alasan_penahanan"] = ";".join(dict.fromkeys(reasons))
        if reasons_main:
            merged["status_eksploratif"] = "perlu_tinjau"
            merged["alasan_tinjau_eksploratif"] = ";".join(reasons_main)
        else:
            merged["status_eksploratif"] = "lolos_pemeriksaan_dasar"
            merged["alasan_tinjau_eksploratif"] = ""
        if reasons:
            merged["alasan_pengecualian"] = ";".join(reasons)
            excluded.append(merged)
            for reason in reasons:
                counts[reason] += 1
                affected[reason].add(item["response_id"])
        else:
            candidate.append(merged)
    exploratory = [item for item in candidate if item["status_eksploratif"] == "lolos_pemeriksaan_dasar"]
    exploratory_review = [item for item in candidate if item["status_eksploratif"] == "perlu_tinjau"]
    ids_candidate = {r["response_id"] for r in candidate}
    result = {
        "status_dataset": "kandidat_eksploratif_belum_training", "siap_training": False,
        "versi_aturan_seleksi": VERSI_ATURAN, "hash_masukan_sha256": hashes,
        "jumlah_kiriman_sumber": len(responses), "jumlah_penilaian_sumber": len(ratings),
        "jumlah_kandidat": len(candidate), "jumlah_kandidat_utama": len(candidate), "jumlah_kandidat_eksploratif_diperiksa": len(candidate),
        "jumlah_kandidat_eksploratif_lolos": len(exploratory), "jumlah_kandidat_eksploratif_perlu_tinjau": len(exploratory_review),
        "jumlah_pasangan_rating_kandidat_utama_terpilih": len(exploratory),
        "jumlah_pasangan_rating_eksploratif_perlu_tinjau": len(exploratory_review),
        "jumlah_dikecualikan": len(excluded),
        "jumlah_gabungan_dikecualikan": len(excluded),
        "jumlah_pengecualian_unik": len(excluded),
        "jumlah_rating_duplikat_pasangan": report["duplikasi_pasangan"],
        "jumlah_kiriman_konflik_alergi": sum(value is not None for value in conflicts.values()),
        "jumlah_pemetaan_unik": len({r["nama_makanan_survei"] for r in ratings}),
        "jumlah_pemetaan_terkonfirmasi_nama_id": report.get("jumlah_pemetaan_terkonfirmasi_nama_id", 0),
        "jumlah_pemetaan_ditahan": sum(r["status_pemetaan"].startswith("ditahan_") for r in ratings),
        "jumlah_rating_dengan_seimbang_legacy": sum(r["prioritas_asli"] == "Seimbang (tidak ada prioritas khusus)" for r in ratings),
        "jumlah_rating_seimbang_legacy_dapat_dievaluasi_dengan_PD11_R2": 0,
        "jumlah_kiriman_kandidat": len(ids_candidate),
        "jumlah_kiriman_seluruhnya_dikecualikan": len(set(by_id) - ids_candidate),
        "alasan_pengecualian": {key: {"penilaian": counts[key], "kiriman_unik": len(affected[key])} for key in counts},
        "distribusi_sebelum": {"rating": dict(Counter(r["rating"] for r in ratings)), "profil_kiriman": distribusi(responses, PROFILE_NAMES), "prioritas_asli": dict(Counter(r["prioritas_asli"] for r in responses))},
        "distribusi_sesudah": {"rating": dict(Counter(r["rating"] for r in candidate)), "profil_penilaian": distribusi(candidate, PROFILE_NAMES), "profil_kiriman": distribusi([r for r in responses if r["response_id"] in ids_candidate], PROFILE_NAMES), "prioritas_kiriman": dict(Counter(r["prioritas_asli"] for r in responses if r["response_id"] in ids_candidate))},
        "distribusi_dikecualikan": {"rating": dict(Counter(r["rating"] for r in excluded)), "profil_penilaian": distribusi(excluded, PROFILE_NAMES), "profil_kiriman": distribusi([r for r in responses if r["response_id"] in {e["response_id"] for e in excluded}], PROFILE_NAMES)},
        "distribusi_rating_eksploratif_lolos": dict(Counter(r["rating"] for r in exploratory)),
        "distribusi_rating_eksploratif_review": dict(Counter(r["rating"] for r in exploratory_review)),
        "kelompok_jawaban_identik_dalam_kandidat": [[rid for rid in group if rid in ids_candidate] for group in report.get("kelompok_jawaban_identik", []) if sum(rid in ids_candidate for rid in group) >= 2],
        "keputusan_seleksi": "Kandidat eksploratif mensyaratkan profil/rating valid dan kiriman tidak bertentangan. Pasangan yang masih perlu konfirmasi semantik resep/porsi atau memakai definisi Seimbang survei legacy ditahan dari kandidat utama. Alasan dapat tumpang tindih.",
        "kelayakan_PD11_R2": "tidak_layak_evaluasi", "kelayakan_eksploratif": "terbatas_dengan_penanda_review", "eksploratif_ratings": len(candidate), "eksploratif_lolos_pemeriksaan_dasar": len(exploratory), "eksploratif_perlu_review_porsi_atau_definisi": len(exploratory_review), "jumlah_kiriman": len(responses), "jumlah_pasangan_rating": len(ratings), "jumlah_kelompok_evaluasi_identik": len(report.get("kelompok_jawaban_identik", [])),
        "keterbatasan": ["Seimbang survei legacy berarti tidak ada prioritas khusus; bukan rasio backend 15/55/30.", "Porsi/resep yang dinilai responden belum terbukti sama dengan katalog.", "Kelompok jawaban identik bukan bukti responden yang sama.", "Rating bukan bukti bahan/alergi aman atau terverifikasi.", "Kandidat belum merupakan persetujuan pelatihan."],
        "kebutuhan_survei_tambahan_PD11_R2": ["Instrumen dan rating baru untuk definisi prioritas backend termasuk Seimbang 15/55/30.", "Definisi responden/group untuk evaluasi atau rencana pembagian evaluasi tanpa identitas yang tidak tersedia."] ,
    }
    assert len(candidate) + len(excluded) == source_pairs == len(ratings)
    result["rekonsiliasi_pasangan_rating"] = {
        "baris_sumber": source_pairs,
        "kandidat": len(candidate),
        "ditahan_atau_dikecualikan": len(excluded),
        "sama": len(candidate) + len(excluded) == source_pairs,
    }
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
