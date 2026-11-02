"""
scripts/prepare_survey.py
Skrip persiapan data survei NutriRec AI untuk keperluan ML.

Cara pakai:
  python scripts/prepare_survey.py \
    --file "data/NutriRec-AI (Jawaban).xlsx" \
    --foods "data/Dataset_makanan_revisi.xlsx" \
    --output-dir data/processed \
    --dry-run

Fitur:
  - Membaca sheet "Form Responses 1" dari file survei (openpyxl, data_only=True).
  - Memvalidasi struktur kolom (wajib, header ambigu/duplikat, baris kosong).
  - Membuat response_id anonim (R001, R002, ...) dari urutan baris sumber.
  - Membuat rating long format (satu baris per penilaian makanan).
  - Mendeteksi penanda kualitas (konflik, duplikat, rating_1 tanpa alergi, ...).
  - Membuat pemetaan makanan survei -> dataset (eksplisit, butuh konfirmasi).
  - Menulis CSV + JSON laporan; mode --dry-run tidak menulis file.

Catatan:
  - Rating mengukur kesesuaian (suitability) terhadap pilihan pengguna,
    bukan kesukaan. Label 1-4 pada mode ini mengikuti definisi survei.
  - "Seimbang (tidak ada prioritas khusus)" pada survei membedakan makna
    dengan acuan komposisi backend (15/55/30). Tidak diubah di sini.
  - Tidak ada pelatihan model pada skrip ini; output adalah data persiapan.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

# Tambahkan root proyek ke sys.path agar import app.* berjalan (sama seperti skrip lain).
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ─── Konstanta ────────────────────────────────────────────────────────────────

SHEET_SURVEI = "Form Responses 1"

RATING_LABELS: dict[int, str] = {
    1: "Sangat tidak sesuai (karena mengandung bahan yang membuat saya alergi)",
    2: "Tidak sesuai (agak jauh dari target)",
    3: "Sesuai (hampir sesuai target)",
    4: "Sangat sesuai (sesuai target)",
}

RATING_PATTERN = re.compile(r"^\s*([1-4])\s*=\s*(.+)$")

TARGET_OPTIONS: dict[str, dict[str, Any]] = {
    "Rendah (< 300 kkal)": {"id": 1, "nama": "Rendah"},
    "Sedang (300-500 kkal)": {"id": 2, "nama": "Sedang"},
    "Tinggi (> 500 kkal)": {"id": 3, "nama": "Tinggi"},
}

PRIORITY_OPTIONS: dict[str, dict[str, Any]] = {
    "Protein tinggi": {"id": 1, "nama": "Protein"},
    "Karbohidrat tinggi": {"id": 2, "nama": "Karbohidrat"},
    "Lemak tinggi": {"id": 3, "nama": "Lemak"},
    "Seimbang (tidak ada prioritas khusus)": {"id": 4, "nama": "Seimbang"},
}

STATUS_ALLERGI: dict[str, bool] = {
    "Tidak ada alergi": False,
    "Ya, memiliki alergi": True,
}

ALLERGEN_KEYWORD_ID: dict[str, int] = {
    "telur": 1,
    "kedelai": 2,
    "jagung": 3,
    "kelapa": 4,
    "ayam": 5,
    "daging sapi": 6,
    "gandum": 7,
    "kacang-kacangan": 8,
    "udang/seafood": 9,
    "ikan": 10,
    "beras": 11,
}

REQUIRED_COLUMNS: list[str] = [
    "Timestamp",
    "Berapa target kalori Anda untuk satu kali makan?",
    "Nutrisi apa yang paling Anda prioritaskan pada makanan?",
    "Apakah Anda memiliki alergi terhadap makanan?",
    "Jika Anda memiliki alergi makanan, bahan makanan apa saja yang perlu dihindari?",
]

PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN = "konflik_tanpa_alergi_dengan_pilihan"
PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN = "konflik_alergi_tanpa_pilihan"
PENANDA_RATING_1_TANPA_ALLERGI = "rating_1_tanpa_alergi"
PENANDA_KEMUNGKINAN_DUPLIKAT = "kemungkinan_duplikat"
PENANDA_RATING_SERAGAM = "rating_seragam"
PENANDA_PEMETAAN_MAKANAN_BELUM_KONFIRMASI = "pemetaan_makanan_belum_dikonfirmasi"
PENANDA_MEANSAING_BELUM_SELARASKAN = "makna_seimbang_perlu_diselaraskan"

MAPELANGGAN_MAKANAN: dict[str, str] = {
    "Bihun Goreng Sayur": "Bihun Goreng Sayur",
    "Nasi Uduk": "Nasi Uduk",
    "Sup Tahu Telur": "Sup Tahu Telur",
    "Lemper Ayam": "Lemper Ayam",
    "Soto Ayam Bening": "Soto Ayam Bening",
    "Bakso Sapi Kuah (Tanpa Mie)": "Bakso Sapi Kuah (Tanpa Mie)",
    "Rawon Daging Sapi": "Rawon Daging Sapi",
    "Nasi Goreng": "Nasi Goreng",
    "Ayam Geprek": "Ayam Geprek",
    "Ayam Bakar Taliwang": "Ayam Bakar Taliwang",
    "Ayam Goreng (Tanpa Nasi)": "Ayam Goreng",
    "Bubur Ayam": "Bubur Ayam",
    "Dendeng Balado Basah": "Dendeng Balado Basah",
    "Nasi Putih (Dijual Terpisah)": "Nasi Putih (Dijual Terpisah)",
    "Pecel Lele": "Pecel Lele",
    "Sayur Sop": "Sayur Sop",
    "Lontong Sayur": "Lontong Sayur",
    "Mie Ayam": "Mie Ayam",
    "Nasi Padang Ayam Pop": "Nasi Padang Ayam Pop",
    "Capcay Kuah (Ayam)": "Capcay Goreng / Kuah (Ayam)",
}

MAPELANGGAN_MAKANAN_NORMALIZED: dict[str, str] = {
    k.strip().lower(): v for k, v in MAPELANGGAN_MAKANAN.items()
}
VERSI_PEMETAAN = "survei-PD11-1"


# ─── Utilitas ──────────────────────────────────────────────────────────────────

def norm_teks(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def kunci_header_makanan(header: str) -> str:
    """Kunci nama makanan; nomor pertanyaan bukan ID makanan."""
    return norm_teks(re.sub(r"^\s*\d+\.\s*", "", str(header))).casefold()


def buat_response_id(source_row: int) -> str:
    return f"R{source_row - 1:03d}"


def parse_rating(value: Any) -> dict[str, Any]:
    teks = norm_teks(value)
    if not teks:
        return {"rating": None, "status": "kosong", "label": None}
    m = RATING_PATTERN.match(teks)
    if not m:
        return {"rating": None, "status": "tidak_valid", "label": None}
    angka = int(m.group(1))
    label = norm_teks(m.group(2))
    if RATING_LABELS.get(angka) != label:
        return {"rating": None, "status": "tidak_valid", "label": label}
    return {"rating": angka, "status": "valid", "label": label}


def split_top_level(teks: str, pemisah: str = ",") -> list[str]:
    bagian: list[str] = []
    depth = 0
    current = ""
    for ch in teks:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == pemisah and depth == 0:
            bagian.append(current)
            current = ""
        else:
            current += ch
    bagian.append(current)
    return [norm_teks(b) for b in bagian if norm_teks(b)]


def parse_alergen(value: Any) -> tuple[list[int], list[str]]:
    teks = norm_teks(value)
    ids: list[int] = []
    unknown: list[str] = []
    if not teks:
        return [], []
    for token in split_top_level(teks, ","):
        nama = token.lower()
        if nama == "kacang-kacangan (tauge, kacang tanah, buncis)":
            nama = "kacang-kacangan"
        if nama in ALLERGEN_KEYWORD_ID:
            mapped = ALLERGEN_KEYWORD_ID[nama]
            if mapped not in ids:
                ids.append(mapped)
        elif token:
            unknown.append(token)
    return ids, unknown


def baca_dataset(xlsx_path: str) -> tuple[dict[str, int], list[str]]:
    workbook = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
    if "Dataset" not in workbook.sheetnames:
        raise ValueError(f"Sheet 'Dataset' tidak ditemukan pada file: {xlsx_path}")
    sheet = workbook["Dataset"]
    mapping: dict[str, int] = {}
    errors: list[str] = []
    headers = [norm_teks(x).casefold() for x in next(sheet.iter_rows(max_row=1, values_only=True))]
    for header in ("no", "nama makanan"):
        if headers.count(header) != 1:
            errors.append(f"Dataset: header {header!r} hilang atau duplikat")
    if errors:
        workbook.close()
        return mapping, errors
    idx_id, idx_nama = headers.index("no"), headers.index("nama makanan")
    ids = set()
    names = set()
    for nomor_baris, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None or str(v).strip() == "" for v in values):
            continue
        nama = norm_teks(values[idx_nama])
        no = values[idx_id]
        if not nama or nama.casefold() in names:
            errors.append(f"Dataset baris {nomor_baris}: nama kosong atau ambigu: {nama!r}")
        if isinstance(no, bool) or not isinstance(no, (int, float)) or int(no) != no or no <= 0 or no in ids:
            errors.append(f"Dataset baris {nomor_baris}: ID kosong, tidak valid, atau duplikat: {no!r}")
            continue
        ids.add(no)
        names.add(nama.casefold())
        if nama:
            mapping[nama] = int(no)
    workbook.close()
    return mapping, errors


def baca_survei(xlsx_path: str) -> tuple[list[dict[str, Any]], list[str]]:
    workbook = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
    if SHEET_SURVEI not in workbook.sheetnames:
        raise ValueError(f"Sheet '{SHEET_SURVEI}' tidak ditemukan pada file: {xlsx_path}")
    sheet = workbook[SHEET_SURVEI]
    rows_iter = sheet.iter_rows(values_only=True)
    headers: list[str] = []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        raw_headers = next(rows_iter)
        headers = ["" if c is None else str(c) for c in raw_headers]
    except StopIteration:
        workbook.close()
        return [], ["Sheet survei kosong: tidak ada baris header."]
    seen: set[str] = set()
    for header in headers:
        if not header:
            errors.append("Header kosong ditemukan.")
        elif header in seen:
            errors.append(f"Header duplikat: '{header}'.")
        seen.add(header)
    for column in REQUIRED_COLUMNS:
        if column not in headers:
            errors.append(f"Kolom wajib tidak ditemukan: '{column}'.")
    food_headers = [h for h in headers if h not in REQUIRED_COLUMNS and h]
    food_names = [kunci_header_makanan(h) for h in food_headers]
    expected = set(MAPELANGGAN_MAKANAN_NORMALIZED)
    for name in sorted(expected - set(food_names)):
        errors.append(f"Kolom makanan hilang: {name}")
    for name in food_names:
        if name not in expected:
            errors.append(f"Kolom makanan tidak dikenal: {name}")
        if food_names.count(name) > 1:
            errors.append(f"Kolom makanan ambigu atau duplikat: {name}")
    for nomor_baris, values in enumerate(rows_iter, start=2):
        row_dict: dict[str, Any] = {"source_row": nomor_baris}
        for i, header in enumerate(headers):
            row_dict[header] = values[i] if i < len(values) else None
        if all(
            v is None or (isinstance(v, str) and v.strip() == "") or v == ""
            for k, v in row_dict.items()
            if k != "source_row"
        ):
            continue
        rows.append(row_dict)
    workbook.close()
    return rows, errors


def deteksi_kelompok_jawaban_identik(rows: list[dict[str, Any]]) -> list[list[str]]:
    groups: dict[tuple, list[str]] = defaultdict(list)
    for row in rows:
        key = tuple(
            (k, norm_teks(row.get(k)))
            for k in sorted(row)
            if k != "source_row" and k != "Timestamp"
        )
        groups[key].append(buat_response_id(int(row.get("source_row") or 0)))
    hasil: list[list[str]] = []
    for key in sorted(groups, key=lambda k: groups[k][0]):
        ids = sorted(set(groups[key]))
        if len(ids) > 1:
            hasil.append(ids)
    return hasil


# ─── Pemrosesan utama ─────────────────────────────────────────────────────────

def siapkan_data(
    rows: list[dict[str, Any]],
    dataset_nama_ids: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    responses_out: list[dict[str, Any]] = []
    ratings_out: list[dict[str, Any]] = []
    status_counter: Counter[str] = Counter()
    rating_counter: Counter[str] = Counter()
    penanda_counter: Counter[str] = Counter()
    rating_1_ids: set[str] = set()
    pemetaan_belum: set[str] = set()
    kelompok = deteksi_kelompok_jawaban_identik(rows)
    dup_ids: set[str] = set()
    for ids in kelompok:
        dup_ids.update(ids)

    for row in rows:
        source_row = int(row.get("source_row") or 0)
        response_id = buat_response_id(source_row)
        target_asli = norm_teks(row.get("Berapa target kalori Anda untuk satu kali makan?"))
        prioritas_asli = norm_teks(row.get("Nutrisi apa yang paling Anda prioritaskan pada makanan?"))
        status_asli = norm_teks(row.get("Apakah Anda memiliki alergi terhadap makanan?"))
        alergen_asli = norm_teks(row.get("Jika Anda memiliki alergi makanan, bahan makanan apa saja yang perlu dihindari?"))

        target_mapped = TARGET_OPTIONS.get(target_asli)
        prioritas_mapped = PRIORITY_OPTIONS.get(prioritas_asli)
        status_alergi = STATUS_ALLERGI.get(status_asli)
        alergen_ids, alergen_unknown = parse_alergen(alergen_asli)

        flags: list[str] = []
        hold: list[str] = []
        for column, mapped in zip(REQUIRED_COLUMNS[1:4], (target_mapped, prioritas_mapped, status_alergi)):
            if mapped is None:
                reason = "profil_kosong" if not norm_teks(row.get(column)) else "profil_tidak_dikenal"
                flags.append(reason)
                hold.append(reason)
        if alergen_unknown:
            flags.append("alergen_tidak_dikenal")
            hold.append("alergen_tidak_dikenal")
        if status_asli == "Tidak ada alergi" and norm_teks(alergen_asli):
            flags.append(PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN)
            hold.append(PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN)
        if status_asli == "Ya, memiliki alergi" and not norm_teks(alergen_asli):
            flags.append(PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN)
            hold.append(PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN)
        if prioritas_asli == "Seimbang (tidak ada prioritas khusus)":
            flags.append(PENANDA_MEANSAING_BELUM_SELARASKAN)
        if response_id in dup_ids:
            flags.append(PENANDA_KEMUNGKINAN_DUPLIKAT)

        headers_sorted = sorted(
            (k for k in row if k != "source_row"),
            key=lambda k: (
                int(re.match(r"^\s*(\d+)", str(k)).group(1)) if re.match(r"^\s*(\d+)", str(k)) else 999,
                str(k),
            ),
        )
        food_columns: list[dict[str, Any]] = []
        for header in headers_sorted:
            key_mapping = kunci_header_makanan(header)
            if key_mapping not in MAPELANGGAN_MAKANAN_NORMALIZED:
                continue
            survey_name = norm_teks(re.sub(r"^\s*\d+\.\s*", "", str(header)))
            parsed = parse_rating(row.get(header))
            id_makanan = ""
            perlu_konfirmasi = False
            if key_mapping in MAPELANGGAN_MAKANAN_NORMALIZED:
                dataset_name = MAPELANGGAN_MAKANAN_NORMALIZED[key_mapping]
                if key_mapping == kunci_header_makanan("Capcay Kuah (Ayam)"):
                    perlu_konfirmasi = True
                else:
                    id_makanan = str(dataset_nama_ids.get(dataset_name, ""))
                    if not id_makanan:
                        perlu_konfirmasi = True
            else:
                perlu_konfirmasi = True
            if perlu_konfirmasi:
                pemetaan_belum.add(survey_name)
            food_columns.append(
                {
                    "nama_makanan_survei": str(header),
                    "nama_makanan_bersih": survey_name,
                    "id_makanan": id_makanan,
                    "perlu_konfirmasi": perlu_konfirmasi,
                    "rating": parsed,
                    "raw": row.get(header),
                }
            )

        ratings_values: list[int] = [
            fc["rating"]["rating"] for fc in food_columns if fc["rating"]["status"] == "valid"
        ]
        if ratings_values and len(set(ratings_values)) == 1:
            flags.append(PENANDA_RATING_SERAGAM)

        responses_out.append(
            {
                "response_id": response_id,
                "source_row": source_row,
                "timestamp": row.get("Timestamp"),
                "target_kalori_asli": target_asli,
                "target_kalori_id": target_mapped["id"] if target_mapped else None,
                "prioritas_asli": prioritas_asli,
                "prioritas_id": prioritas_mapped["id"] if prioritas_mapped else None,
                "status_alergi_asli": status_asli,
                "alergen_asli": alergen_asli,
                "alergen_ids": ";".join(str(i) for i in alergen_ids),
                "penanda": ";".join(dict.fromkeys(flags)) if flags else None,
                "tahan_seluruh_kiriman": bool(hold),
            }
        )

        for fc in food_columns:
            parsed = fc["rating"]
            reasons = list(hold)
            penanda_rating: list[str] = list(hold)
            status_rating = "kosong"
            if parsed["status"] == "valid":
                status_rating = "perlu_tinjau" if reasons else "lolos_pemeriksaan_dasar"
                if parsed["rating"] == 1 and status_alergi is False:
                    reasons.append(PENANDA_RATING_1_TANPA_ALLERGI)
                    penanda_rating.append(PENANDA_RATING_1_TANPA_ALLERGI)
                    rating_1_ids.add(response_id)
                if reasons:
                    status_rating = "perlu_tinjau"
                else:
                    status_rating = "lolos_pemeriksaan_dasar"
                rating_counter[str(parsed["rating"])] += 1
            elif parsed["status"] == "tidak_valid":
                status_rating = "tidak_valid"
                reasons.append("rating_tidak_valid")
            if fc["perlu_konfirmasi"]:
                penanda_rating.append(PENANDA_PEMETAAN_MAKANAN_BELUM_KONFIRMASI)
            status_counter[status_rating] += 1
            ratings_out.append(
                {
                    "response_id": response_id,
                    "source_row": source_row,
                    "target_kalori_id": target_mapped["id"] if target_mapped else None,
                    "prioritas_id": prioritas_mapped["id"] if prioritas_mapped else None,
                    "status_alergi": status_asli,
                    "alergen_ids": ";".join(str(i) for i in alergen_ids),
                    "nama_makanan_survei": fc["nama_makanan_survei"],
                    "id_makanan": fc["id_makanan"],
                    "pemetaan_makanan_terkonfirmasi": not fc["perlu_konfirmasi"],
                    "rating_asli": fc.get("raw"),
                    "rating": parsed["rating"],
                    "penanda": ";".join(dict.fromkeys(penanda_rating)) if penanda_rating else None,
                    "penanda_kiriman": ";".join(dict.fromkeys(flags)),
                    "penanda_penilaian": ";".join(dict.fromkeys(penanda_rating)),
                    "status": status_rating,
                    "alasan_tahan": ";".join(dict.fromkeys(reasons)) if reasons else None,
                }
            )

    for response in responses_out:
        if response.get("penanda"):
            for flag in str(response["penanda"]).split(";"):
                if flag:
                    penanda_counter[flag] += 1

    report: dict[str, Any] = {
        "source_sha256": "",
        "jumlah_kiriman": len(responses_out),
        "jumlah_penilaian": len(ratings_out),
        "status_penilaian": dict(status_counter),
        "rating": {str(k): v for k, v in sorted(rating_counter.items())},
        "jumlah_kiriman_per_penanda": dict(penanda_counter),
        "kiriman_rating_1_tanpa_alergi": sorted(rating_1_ids),
        "kelompok_jawaban_identik": kelompok,
        "pemetaan_makanan_belum_dikonfirmasi": sorted(pemetaan_belum),
        "siap_ml": False,
        "catatan": "Lolos pemeriksaan dasar bukan persetujuan untuk pelatihan ML.",
    }
    errors = []
    kosong, invalid = Counter(), Counter()
    distribusi = {c: Counter() for c in REQUIRED_COLUMNS[1:4]}
    for row in rows:
        rid = buat_response_id(row["source_row"])
        for column, options in zip(REQUIRED_COLUMNS[1:4], (TARGET_OPTIONS, PRIORITY_OPTIONS, STATUS_ALLERGI)):
            original = row.get(column)
            text = norm_teks(original)
            distribusi[column][text or "(kosong)"] += 1
            if not text or text not in options:
                (kosong if not text else invalid)[column] += 1
                errors.append({"response_id": rid, "source_row": row["source_row"], "kolom": column, "nilai_asli": original, "jenis": "kosong" if not text else "tidak_dikenal"})
        for token in parse_alergen(row.get(REQUIRED_COLUMNS[4]))[1]:
            invalid[REQUIRED_COLUMNS[4]] += 1
            errors.append({"response_id": rid, "source_row": row["source_row"], "kolom": REQUIRED_COLUMNS[4], "nilai_asli": row.get(REQUIRED_COLUMNS[4]), "token": token, "jenis": "tidak_dikenal"})
    for rating in ratings_out:
        parsed = parse_rating(rating["rating_asli"])
        if parsed["status"] != "valid":
            column = rating["nama_makanan_survei"]
            (kosong if parsed["status"] == "kosong" else invalid)[column] += 1
            errors.append({"response_id": rating["response_id"], "source_row": rating["source_row"], "kolom": column, "nilai_asli": rating["rating_asli"], "jenis": parsed["status"]})
    markers = defaultdict(set)
    marker_ratings = Counter()
    for r in ratings_out:
        for flag in set(filter(None, (r["penanda_kiriman"] + ";" + r["penanda_penilaian"]).split(";"))):
            markers[flag].add(r["response_id"])
            marker_ratings[flag] += 1
    alasan = ["Tahap persiapan: data final belum disetujui untuk pelatihan.",
              "ID database belum diverifikasi terhadap database terpasang."]
    if any(kunci_header_makanan(n) == kunci_header_makanan("Capcay Kuah (Ayam)") for n in pemetaan_belum):
        alasan.append("Pemetaan Capcay belum dikonfirmasi.")
    if any(kunci_header_makanan(n) != kunci_header_makanan("Capcay Kuah (Ayam)") for n in pemetaan_belum):
        alasan.append("Ada pemetaan makanan lain yang belum selesai.")
    if PENANDA_MEANSAING_BELUM_SELARASKAN in markers:
        alasan.append("Makna Seimbang survei perlu ditinjau.")
    if any(flag in markers for flag in (PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN,
                                        PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN,
                                        PENANDA_RATING_1_TANPA_ALLERGI)):
        alasan.append("Konflik alergi atau rating 1 tanpa alergi perlu ditinjau.")
    if errors:
        alasan.append("Nilai kosong atau tidak valid perlu ditinjau.")
    report.update({"kesalahan": errors, "peringatan": [{"jenis": "id_database_belum_diverifikasi", "lokasi": "database aplikasi tidak diakses"}],
        "nilai_kosong_per_kolom": dict(kosong), "nilai_tidak_valid_per_kolom": dict(invalid),
        "distribusi_profil": {k: dict(v) for k, v in distribusi.items()},
        "jumlah_kiriman_per_penanda": {k: len(v) for k, v in markers.items()},
        "jumlah_penilaian_per_penanda": dict(marker_ratings),
        "jumlah_kiriman_terdampak_unik": len(set().union(*markers.values())) if markers else 0,
        "versi_konfigurasi_pemetaan": VERSI_PEMETAAN,
        "verifikasi_id_referensi": "Belum diverifikasi terhadap database; migrasi menggunakan auto-increment; importer memakai NO sebagai PK.",
        "alasan_belum_siap_ml": alasan})
    return responses_out, ratings_out, report


# ─── Output ────────────────────────────────────────────────────────────────────

def tulis_csv(output_dir: Path, nama: str, fieldnames: list[str], data: list[dict[str, Any]]) -> None:
    path = output_dir / nama
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def tulis_output(
    output_dir: Path,
    responses: list[dict[str, Any]],
    ratings: list[dict[str, Any]],
    report: dict[str, Any],
    source_path: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha256 = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    report["source_sha256"] = source_sha256

    fields_response = [
        "response_id", "source_row", "timestamp", "target_kalori_asli", "target_kalori_id",
        "prioritas_asli", "prioritas_id", "status_alergi_asli", "alergen_asli",
        "alergen_ids", "penanda", "tahan_seluruh_kiriman",
    ]
    tulis_csv(
        output_dir,
        "survey_responses.csv",
        fields_response,
        responses,
    )

    fields_rating = [
        "response_id", "source_row", "target_kalori_id", "prioritas_id", "status_alergi",
        "alergen_ids", "nama_makanan_survei", "id_makanan", "pemetaan_makanan_terkonfirmasi", "rating_asli", "rating",
        "penanda", "penanda_kiriman", "penanda_penilaian", "status", "alasan_tahan",
    ]
    tulis_csv(
        output_dir,
        "survey_ratings_long.csv",
        fields_rating,
        ratings,
    )

    (output_dir / "survey_validation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persiapan data survei NutriRec AI untuk keperluan ML.",
    )
    parser.add_argument(
        "--file",
        required=True,
        help='Path file survei Excel, mis. "data/NutriRec-AI (Jawaban).xlsx"',
    )
    parser.add_argument(
        "--foods",
        required=True,
        help='Path file dataset Excel, mis. "data/Dataset_makanan_revisi.xlsx"',
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Direktori output (default: data/processed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hanya baca, validasi, dan tampilkan ringkasan; tidak menulis file.",
    )
    args = parser.parse_args(argv)

    try:
        rows, errors = baca_survei(args.file)
        dataset_nama_ids, dataset_errors = baca_dataset(args.foods)
    except (OSError, ValueError) as exc:
        print(f"Kesalahan sumber: {exc}", file=sys.stderr)
        return 2
    errors.extend(dataset_errors)

    if errors:
        print("ERROR VALIDASI HEADER/Kolom:")
        for e in errors:
            print(f"  - {e}")
        return 2

    responses, ratings, report = siapkan_data(rows, dataset_nama_ids)
    if Path(args.file).is_file() and Path(args.foods).is_file():
        report["hash_sumber"] = {"survei_sha256": hashlib.sha256(Path(args.file).read_bytes()).hexdigest(), "makanan_sha256": hashlib.sha256(Path(args.foods).read_bytes()).hexdigest()}

    print(f"Jumlah kiriman: {report['jumlah_kiriman']}")
    print(f"Jumlah penilaian: {report['jumlah_penilaian']}")
    print(f"Status penilaian: {report['status_penilaian']}")
    print(f"Rating: {report['rating']}")
    print(f"Siap ML: {report['siap_ml']}")

    if args.dry_run:
        print("DRY RUN: tidak ada file yang ditulis.")
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tulis_output(output_dir, responses, ratings, report, args.file)
    print(f"Output ditulis ke: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
