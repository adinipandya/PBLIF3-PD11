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
import math
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.core.recommendation_rules import calorie_category

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

ALLERGEN_ALIASES: dict[str, str] = {
    "telur": "telur",
    "telor": "telur",
    "kedelai": "kedelai",
    "soybean": "kedelai",
    "soy": "kedelai",
    "jagung": "jagung",
    "maize": "jagung",
    "corn": "jagung",
    "kelapa": "kelapa",
    "santan": "kelapa",
    "ayam": "ayam",
    "daging ayam": "ayam",
    "daging sapi": "daging sapi",
    "sapi": "daging sapi",
    "beef": "daging sapi",
    "gandum": "gandum",
    "terigu": "gandum",
    "gluten": "gandum",
    "kacang-kacangan": "kacang-kacangan",
    "kacang kacangan": "kacang-kacangan",
    "udang/seafood": "udang/seafood",
    "udang": "udang/seafood",
    "seafood": "udang/seafood",
    "ikan": "ikan",
    "ikan lele": "ikan",
    "beras": "beras",
    "nasi": "beras",
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
ALLERGEN_ID_CANONICAL = {value: name for name, value in ALLERGEN_KEYWORD_ID.items()}
ALLERGEN_KANONIK = {8: "kacang-kacangan", 9: "udang/seafood", 6: "daging sapi"}

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
VERSI_INSTRUMEN_SURVEI = "legacy-v1"
DEFINISI_PRIORITAS = {
    "Protein tinggi": "pilihan_prioritas_zat_gizi_survei_legacy",
    "Karbohidrat tinggi": "pilihan_prioritas_zat_gizi_survei_legacy",
    "Lemak tinggi": "pilihan_prioritas_zat_gizi_survei_legacy",
    "Seimbang (tidak ada prioritas khusus)": "tanpa_prioritas_khusus_survei_legacy",
}

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
    " ".join(re.sub(r"^\s*\d+\.\s*", "", k).strip().split()).casefold(): v
    for k, v in MAPELANGGAN_MAKANAN.items()
}
VERSI_PEMETAAN = "survei-PD11-2"


# ─── Utilitas ──────────────────────────────────────────────────────────────────

def norm_teks(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def kunci_header_makanan(header: str) -> str:
    """Key food prompt text; the prompt number is not a catalog primary key."""
    return norm_teks(re.sub(r"^\s*\d+\.\s*", "", str(header))).casefold()


def normalisasi_status_alergi(status: str) -> str:
    """Explicit alias normalization; preserve the original answer separately."""
    aliases = {
        "tidak ada alergi": "Tidak ada alergi",
        "tidak alergi": "Tidak ada alergi",
        "tidak memiliki alergi": "Tidak ada alergi",
        "no allergy": "Tidak ada alergi",
        "ya, memiliki alergi": "Ya, memiliki alergi",
        "ya memiliki alergi": "Ya, memiliki alergi",
        "memiliki alergi": "Ya, memiliki alergi",
        "ya": "Ya, memiliki alergi",
    }
    return aliases.get(norm_teks(status).casefold(), "")

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
        nama_asli = token.casefold()
        nama = ALLERGEN_ALIASES.get(nama_asli, nama_asli)
        if nama == "kacang-kacangan (tauge, kacang tanah, buncis)":
            nama = "kacang-kacangan"
        if nama in ALLERGEN_KEYWORD_ID:
            mapped = ALLERGEN_KEYWORD_ID[nama]
            if mapped not in ids:
                ids.append(mapped)
        elif token:
            unknown.append(token)
    return ids, unknown


def baca_dataset_detail(xlsx_path: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    workbook = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
    if "Dataset" not in workbook.sheetnames:
        raise ValueError(f"Sheet 'Dataset' tidak ditemukan pada file: {xlsx_path}")
    sheet = workbook["Dataset"]
    mapping: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    headers = [norm_teks(x).casefold() for x in next(sheet.iter_rows(max_row=1, values_only=True))]
    for header in ("no", "nama makanan"):
        if headers.count(header) != 1:
            errors.append(f"Dataset: header {header!r} hilang atau duplikat")
    optional_audit_columns = ("kalori (kkal)", "karbo (g)", "lemak (g)", "protein (g)", "porsi", "kelompok kalori", "prioritas nutrisi", "alergen tercatat", "sumber data", "status alergen", "catatan verifikasi")
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
        audit_columns_available = all(headers.count(column) == 1 for column in optional_audit_columns)
        if nama:
            def cell(name: str, default: Any = "") -> Any:
                col = headers.index(name.casefold()) if headers.count(name.casefold()) == 1 else None
                return values[col] if col is not None and col < len(values) else default
            mapping[nama] = {
                "id_sumber": int(no),
                "nama": nama,
                "kalori": cell("kalori (kkal)"),
                "karbohidrat": cell("karbo (g)"),
                "lemak": cell("lemak (g)"),
                "protein": cell("protein (g)"),
                "porsi": norm_teks(cell("porsi")),
                "kategori_kalori_asli": norm_teks(cell("kelompok kalori")),
                "label_prioritas_asli": norm_teks(cell("prioritas nutrisi")),
                "alergen_asli": norm_teks(cell("alergen tercatat")),
                "status_alergen_asli": norm_teks(cell("status alergen")),
                "catatan": norm_teks(cell("catatan verifikasi")),
                "audit_columns_available": audit_columns_available,
            }
    workbook.close()
    return mapping, errors


def baca_dataset(xlsx_path: str) -> tuple[dict[str, int], list[str]]:
    detail, errors = baca_dataset_detail(xlsx_path)
    return {name: row["id_sumber"] for name, row in detail.items()}, errors

def validasi_gizi_katalog(catalog: dict[str, dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    labels, reasons = {}, {}
    for name, item in catalog.items():
        try:
            calories, carbs, fat, protein = [float(item[key]) for key in ("kalori", "karbohidrat", "lemak", "protein")]
        except (TypeError, ValueError, OverflowError):
            reasons[name] = "nilai_gizi_kosong_atau_non_numerik"
            continue
        if not all(math.isfinite(v) and v >= 0 for v in (calories, carbs, fat, protein)):
            reasons[name] = "nilai_gizi_nonfinite_atau_negatif"
            continue
        energy = 4 * protein + 4 * carbs + 9 * fat
        if not math.isfinite(energy) or energy <= 0:
            reasons[name] = "energi_makro_nonpositive"
            continue
        labels[name] = calorie_category(calories)
    return labels, reasons


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
    *,
    catalog_details: dict[str, dict[str, Any]] | None = None,
    database_catalog: dict[int, dict[str, Any]] | None = None,
    dataset_version: str = "unknown",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if catalog_details is None:
        catalog_details = {name: {"id_sumber": food_id, "nama": name, "porsi": "", "kalori": "", "protein": "", "karbohidrat": "", "lemak": "", "kategori_kalori_asli": "", "label_prioritas_asli": "", "alergen_asli": "", "status_alergen_asli": "", "catatan": ""} for name, food_id in dataset_nama_ids.items()}
    database_catalog = database_catalog or {}
    kategori_turunan, alasan_gizi = validasi_gizi_katalog(catalog_details)
    katalog_by_name = {name.casefold(): info for name, info in catalog_details.items()}
    responses_out: list[dict[str, Any]] = []
    ratings_out: list[dict[str, Any]] = []
    status_counter: Counter[str] = Counter()
    rating_counter: Counter[str] = Counter()
    penanda_counter: Counter[str] = Counter()
    rating_1_ids: set[str] = set()
    pemetaan_belum: set[str] = set()
    report_mapping_rows: list[dict[str, Any]] = []
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
        status_normalisasi = normalisasi_status_alergi(status_asli)
        status_alergi = STATUS_ALLERGI.get(status_normalisasi)
        alergen_ids, alergen_unknown = parse_alergen(alergen_asli)
        definisi_prioritas = DEFINISI_PRIORITAS.get(prioritas_asli, "tidak_dikenal")

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
        if status_alergi is False and (norm_teks(alergen_asli) or alergen_ids or alergen_unknown):
            flags.append(PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN)
            hold.append(PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN)
        if status_alergi is True and not (alergen_ids or alergen_unknown):
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
            original_food_header = str(header)
            source_number_match = re.match(r"^\s*(\d+)\.", original_food_header)
            source_number = source_number_match.group(1) if source_number_match else ""
            id_makanan_excel = ""
            id_makanan_katalog = ""
            nama_makanan_katalog = ""
            varian = ""
            deskripsi_porsi_katalog = ""
            status_pemetaan = "belum_dipetakan"
            alasan_pemetaan = ""
            dataset_name = MAPELANGGAN_MAKANAN_NORMALIZED.get(key_mapping, "")
            if dataset_name:
                matched = katalog_by_name.get(dataset_name.casefold())
                if matched:
                    id_makanan_excel = str(matched["id_sumber"])
                    nama_makanan_katalog = matched["nama"]
                    deskripsi_porsi_katalog = matched["porsi"]
                    varian = "nama sama; verifikasi semantik resep/porsi tetap diperlukan"
                    if not matched.get("audit_columns_available", True):
                        status_pemetaan = "ditahan_metadata_katalog_tidak_lengkap"
                        alasan_pemetaan = "Workbook lacks nutrition/portion/source/allergen audit columns."
                    elif key_mapping == kunci_header_makanan("Capcay Kuah (Ayam)"):
                        status_pemetaan = "ditahan_varian_belum_jelas"
                        alasan_pemetaan = "Survei menyebut Capcay Kuah; katalog mencakup Goreng / Kuah. Varian goreng/kuah yang benar-benar dinilai responden tidak tercatat."
                    elif key_mapping == kunci_header_makanan("Ayam Goreng (Tanpa Nasi)") and "tanpa nasi" not in deskripsi_porsi_katalog.casefold():
                        status_pemetaan = "ditahan_porsi_varian_belum_jelas"
                        alasan_pemetaan = "Survei menyebut ayam goreng tanpa nasi; deskripsi porsi katalog tidak secara eksplisit menyebut tanpa nasi."
                    elif key_mapping == kunci_header_makanan("Nasi Putih (Dijual Terpisah)"):
                        status_pemetaan = "id_database_cocok_porsi_relasi_transaksi_perlu_review"
                        id_makanan_katalog = str(database_catalog.get(matched["id_sumber"], {}).get("id_makanan", ""))
                        alasan_pemetaan = "ID butir nasi putih cocok; survei tidak menyatakan lauk/ukuran transaksi yang dimaksud. Jangan gabungkan otomatis dengan rating lauk."
                    elif (database_match := database_catalog.get(matched["id_sumber"])) is None:
                        status_pemetaan = "id_database_belum_diverifikasi"
                        alasan_pemetaan = "ID database belum terverifikasi terhadap database aktif."
                    else:
                        id_makanan_katalog = str(database_match["id_makanan"])
                        status_pemetaan = "id_database_cocok_nama_porsi_perlu_review"
                        alasan_pemetaan = "ID database dan nama cocok saat baca-saja; sumber tidak membuktikan kesetaraan resep atau apakah porsi yang dinilai responden sama dengan porsi katalog."
                else:
                    status_pemetaan = "ditahan_katalog_tidak_ditemukan"
                    alasan_pemetaan = "Nama katalog yang ditunjuk konfigurasi pemetaan tidak ditemukan."
            else:
                status_pemetaan = "ditahan_tidak_ada_pemetaan"
                alasan_pemetaan = "Tidak ada pemetaan eksplisit yang dikonfigurasi."
            if id_makanan_excel and id_makanan_katalog and not status_pemetaan.startswith("ditahan_"):
                db_match = database_catalog.get(int(id_makanan_excel), {})
                numeric_fields_match = all(
                    db_match.get(db_key) is not None
                    and Decimal(str(db_match[db_key])) == Decimal(str(matched[source_key]))
                    for db_key, source_key in (("kalori", "kalori"), ("protein", "protein"), ("karbohidrat", "karbohidrat"), ("lemak", "lemak"))
                )
                if (db_match.get("nama", "").casefold() != nama_makanan_katalog.casefold()
                    or str(db_match.get("porsi", "")) != deskripsi_porsi_katalog
                    or db_match.get("versi_dataset") != dataset_version
                    or not numeric_fields_match):
                    id_makanan_katalog = ""
                    status_pemetaan = "ditahan_katalog_database_tidak_sama"
                    alasan_pemetaan = "ID/nama/porsi/versi/nilai gizi katalog aktif tidak sama dengan snapshot sumber; mapping PK ditahan."
            perlu_konfirmasi = status_pemetaan.startswith("ditahan_")
            if perlu_konfirmasi:
                pemetaan_belum.add(survey_name)
            food_columns.append(
                {
                    "nama_makanan_survei": str(header),
                    "nama_makanan_bersih": survey_name,
                    "nomor_makanan_sumber": source_number,
                    "id_makanan_sumber": id_makanan_excel,
                    "id_makanan_katalog": id_makanan_katalog,
                    "nama_makanan_katalog": nama_makanan_katalog,
                    "varian_pemetaan": varian,
                    "porsi_katalog": deskripsi_porsi_katalog,
                    "status_pemetaan": status_pemetaan,
                    "alasan_pemetaan": alasan_pemetaan,
                    "versi_dataset_makanan": dataset_version,
                    "versi_survei": VERSI_INSTRUMEN_SURVEI,
                    "definisi_prioritas": DEFINISI_PRIORITAS.get(prioritas_asli, "tidak_dikenal"),
                    "kalori_katalog": matched["kalori"] if dataset_name and matched else "",
                    "protein_katalog": matched["protein"] if dataset_name and matched else "",
                    "karbohidrat_katalog": matched["karbohidrat"] if dataset_name and matched else "",
                    "lemak_katalog": matched["lemak"] if dataset_name and matched else "",
                    "kategori_kalori_asli": matched.get("kategori_kalori_asli", "") if dataset_name and matched else "",
                    "kategori_kalori_PD11_R2": kategori_turunan.get(dataset_name, "") if dataset_name else "",
                    "status_pemeriksaan_gizi": "valid" if dataset_name in kategori_turunan else "tidak_valid",
                    "alasan_pemeriksaan_gizi": alasan_gizi.get(dataset_name, "") if dataset_name else "",
                    "alergen_katalog_asli": matched.get("alergen_asli", "") if dataset_name and matched else "",
                    "status_alergen_katalog_asli": matched.get("status_alergen_asli", "") if dataset_name and matched else "",
                    "perlu_konfirmasi": perlu_konfirmasi,
                    "rating": parsed,
                    "raw": row.get(header),
                }
            )

        for fc in food_columns:
            report_mapping_rows.append({
                "nama_makanan_survei": fc["nama_makanan_survei"],
                "nomor_makanan_sumber": fc["nomor_makanan_sumber"],
                "id_makanan_sumber": fc["id_makanan_sumber"],
                "id_makanan_katalog": fc["id_makanan_katalog"],
                "nama_makanan_katalog": fc["nama_makanan_katalog"],
                "kategori_kalori_asli": fc["kategori_kalori_asli"],
                "kategori_kalori_PD11_R2": fc["kategori_kalori_PD11_R2"],
                "alasan_pemeriksaan_gizi": fc["alasan_pemeriksaan_gizi"],
                "varian_pemetaan": fc["varian_pemetaan"],
                "porsi_katalog": fc["porsi_katalog"],
                "status_alergen_katalog_asli": fc["status_alergen_katalog_asli"],
                "status_pemetaan": fc["status_pemetaan"],
                "alasan_pemetaan": fc["alasan_pemetaan"],
                "versi_dataset_makanan": dataset_version,
                "versi_survei": VERSI_INSTRUMEN_SURVEI,
                "definisi_prioritas": definisi_prioritas,
                "status_pemeriksaan_gizi": fc["status_pemeriksaan_gizi"],
            })
        ratings_values: list[int] = [
            fc["rating"]["rating"] for fc in food_columns if fc["rating"]["status"] == "valid"
        ]
        if ratings_values and len(set(ratings_values)) == 1:
            flags.append(PENANDA_RATING_SERAGAM)

        responses_out.append(
            {
                "response_id": response_id,
                "source_row": source_row,
                "versi_survei": VERSI_INSTRUMEN_SURVEI,
                "versi_dataset_makanan": dataset_version,
                "timestamp": row.get("Timestamp"),
                "target_kalori_asli": target_asli,
                "target_kalori_id": target_mapped["id"] if target_mapped else None,
                "prioritas_asli": prioritas_asli,
                "prioritas_id": prioritas_mapped["id"] if prioritas_mapped else None,
                "definisi_prioritas": definisi_prioritas,
                "status_alergi_asli": status_asli,
                "status_alergi_normalisasi": status_normalisasi,
                "alergen_asli": alergen_asli,
                "alergen_ids": ";".join(str(i) for i in alergen_ids),
                "alergen_normalisasi": ";".join(ALLERGEN_KANONIK.get(i, ALLERGEN_ID_CANONICAL[i]) for i in alergen_ids),
                "alergen_ids_normalisasi": ";".join(str(i) for i in alergen_ids),
                "alergen_token_tidak_dikenal": ";".join(alergen_unknown),
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
                    "versi_survei": VERSI_INSTRUMEN_SURVEI,
                    "versi_dataset_makanan": dataset_version,
                    "target_kalori_asli": target_asli,
                    "target_kalori_id": target_mapped["id"] if target_mapped else None,
                    "prioritas_asli": prioritas_asli,
                    "prioritas_id": prioritas_mapped["id"] if prioritas_mapped else None,
                    "definisi_prioritas": definisi_prioritas,
                    "status_alergi": status_normalisasi,
                    "status_alergi_asli": status_asli,
                    "status_alergi_normalisasi": status_normalisasi,
                    "alergen_asli": alergen_asli,
                    "alergen_ids": ";".join(str(i) for i in alergen_ids),
                    "alergen_ids_normalisasi": ";".join(str(i) for i in alergen_ids),
                    "alergen_normalisasi": ";".join(ALLERGEN_KANONIK.get(i, ALLERGEN_ID_CANONICAL[i]) for i in alergen_ids),
                    "alergen_token_tidak_dikenal": ";".join(alergen_unknown),
                    "nama_makanan_survei": fc["nama_makanan_survei"],
                    "nomor_makanan_sumber": fc["nomor_makanan_sumber"],
                    "id_makanan_sumber": fc["id_makanan_sumber"],
                    "id_makanan": fc["id_makanan_katalog"],
                    "id_makanan_katalog": fc["id_makanan_katalog"],
                    "nama_makanan_katalog": fc["nama_makanan_katalog"],
                    "varian_pemetaan": fc["varian_pemetaan"],
                    "porsi_katalog": fc["porsi_katalog"],
                    "status_pemetaan": fc["status_pemetaan"],
                    "alasan_pemetaan": fc["alasan_pemetaan"],
                    "kalori_katalog": fc["kalori_katalog"],
                    "protein_katalog": fc["protein_katalog"],
                    "karbohidrat_katalog": fc["karbohidrat_katalog"],
                    "lemak_katalog": fc["lemak_katalog"],
                    "kategori_kalori_asli": fc["kategori_kalori_asli"],
                    "alergen_katalog_asli": fc["alergen_katalog_asli"],
                    "status_alergen_katalog_asli": fc["status_alergen_katalog_asli"],
                    "kategori_kalori_PD11_R2": fc["kategori_kalori_PD11_R2"],
                    "alasan_pemeriksaan_gizi": fc["alasan_pemeriksaan_gizi"],
                    "status_pemeriksaan_gizi": fc["status_pemeriksaan_gizi"],
                    "pemetaan_makanan_terkonfirmasi": not fc["perlu_konfirmasi"],
                    "rating_asli": fc.get("raw"),
                    "rating_label_asli": parsed["label"],
                    "rating": parsed["rating"],
                    "penanda": ";".join(dict.fromkeys(penanda_rating)) if penanda_rating else None,
                    "penanda_kiriman": ";".join(dict.fromkeys(flags)),
                    "penanda_penilaian": ";".join(dict.fromkeys(penanda_rating)),
                    "status": status_rating,
                    "status_pemeriksaan": status_rating,
                    "alasan_tahan": ";".join(dict.fromkeys(reasons)) if reasons else None,
                    "alasan_penahanan": ";".join(dict.fromkeys(reasons)) if reasons else None,
                }
            )

    for response in responses_out:
        if response.get("penanda"):
            for flag in str(response["penanda"]).split(";"):
                if flag:
                    penanda_counter[flag] += 1

    report: dict[str, Any] = {
        "source_sha256": "",
        "versi_survei": VERSI_INSTRUMEN_SURVEI,
        "definisi_prioritas": DEFINISI_PRIORITAS,
        "definisi_backend_PD11_R2": "Seimbang berbasis proporsi energi 15/55/30; berbeda dari definisi survei lama.",
        "versi_aturan_rekomendasi": "PD11-R2",
        "versi_pemetaan": VERSI_PEMETAAN,
        "id_database_diverifikasi_saat_proses": bool(database_catalog),
        "database_katalog_sha256": hashlib.sha256(json.dumps(database_catalog, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest() if database_catalog else None,
        "dataset_makanan_sumber_hash": "",
        "dataset_makanan_versi": dataset_version,
        "jumlah_kiriman": len(responses_out),
        "jumlah_penilaian": len(ratings_out),
        "status_penilaian": dict(status_counter),
        "status_kiriman": {"jumlah": len(responses_out), "konflik_alergi": sum(1 for response in responses_out if any(flag in (response["penanda"] or "") for flag in (PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN, PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN)))},
        "jumlah_kiriman_konflik_profil": sum(1 for response in responses_out if any(flag in (response["penanda"] or "") for flag in (PENANDA_KONFLIK_TANPA_ALLERGI_DENGAN_PILIHAN, PENANDA_KONFLIK_ALLERGI_DENGAN_PILIHAN))),
        "rating": {str(k): v for k, v in sorted(rating_counter.items())},
        "jumlah_kiriman_unik": len({r["response_id"] for r in responses_out}),
        "jumlah_source_row_unik": len({r["source_row"] for r in responses_out}),
        "jumlah_pasangan_rating_unik": len({(r["response_id"], r["nomor_makanan_sumber"]) for r in ratings_out}),
        "jumlah_makanan_survei_unik": len({r["nama_makanan_survei"] for r in ratings_out}),
        "jumlah_makanan_survei_unik": len({r["nama_makanan_survei"] for r in ratings_out}),
        "distribusi_rating_sebelum": {str(k): v for k, v in sorted(rating_counter.items())},
        "distribusi_prioritas_asli": dict(Counter(r["prioritas_asli"] for r in responses_out)),
        "distribusi_status_alergi_asli": dict(Counter(r["status_alergi_asli"] for r in responses_out)),
        "distribusi_status_pemetaan": dict(Counter(r["status_pemetaan"] for r in ratings_out)),
        "distribusi_status_verifikasi_alergen_katalog": dict(Counter(item["status_alergen_katalog_asli"] or "(kosong)" for item in report_mapping_rows)),
        "distribusi_status_pemeriksaan_gizi": dict(Counter(item["status_pemeriksaan_gizi"] for item in report_mapping_rows)),
        "jumlah_rating_dengan_seimbang_legacy": sum(r["prioritas_asli"] == "Seimbang (tidak ada prioritas khusus)" for r in ratings_out),
        "jumlah_rating_duplikat_pasangan": len(ratings_out) - len({(r["response_id"], r["nomor_makanan_sumber"]) for r in ratings_out}),
        "duplikasi_pasangan": len(ratings_out) - len({(r["response_id"], r["nomor_makanan_sumber"]) for r in ratings_out}),
        "status_pemetaan": dict(Counter(r["status_pemetaan"] for r in ratings_out)),
        "jumlah_pemetaan_unik": len(report_mapping_rows),
        "jumlah_pemetaan_terkonfirmasi_nama_id": sum(item["status_pemetaan"] in {"id_database_cocok_nama_porsi_perlu_review", "id_database_cocok_porsi_relasi_transaksi_perlu_review"} for item in report_mapping_rows),
        "jumlah_kiriman_per_penanda": dict(penanda_counter),
        "kiriman_rating_1_tanpa_alergi": sorted(rating_1_ids),
        "kelompok_jawaban_identik": kelompok,
        "jumlah_kelompok_jawaban_identik": len(kelompok),
        "jumlah_response_id_dalam_kelompok_identik": sum(len(group) for group in kelompok),
        "kebijakan_duplikasi": "Kelompok nilai identik dihitung dan diberi penanda; tidak dikeluarkan otomatis. Response ID dan timestamp bukan identitas orang.",
        "pemetaan_makanan_belum_dikonfirmasi": sorted(pemetaan_belum),
        "pemetaan_makanan": sorted(
            {item["nama_makanan_survei"]: {
                "nama_makanan_survei": item["nama_makanan_survei"],
                "nomor_makanan_sumber": item["nomor_makanan_sumber"],
                "nama_makanan_katalog": item["nama_makanan_katalog"],
                "id_makanan_sumber": item["id_makanan_sumber"],
                "id_makanan_katalog": item["id_makanan_katalog"],
                "kategori_kalori_asli": item["kategori_kalori_asli"],
                "kategori_kalori_PD11_R2": item["kategori_kalori_PD11_R2"],
                "varian_pemetaan": item["varian_pemetaan"],
                "porsi_katalog": item["porsi_katalog"],
                "status_alergen_katalog_asli": item["status_alergen_katalog_asli"],
                "status_pemetaan": item["status_pemetaan"],
                "alasan_pemetaan": item["alasan_pemetaan"],
                "versi_survei": item["versi_survei"],
                "versi_dataset_makanan": item["versi_dataset_makanan"],
                "kategori_kalori_PD11_R2": item["kategori_kalori_PD11_R2"],
                "status_pemeriksaan_gizi": item["status_pemeriksaan_gizi"],
                "alasan_pemeriksaan_gizi": item["alasan_pemeriksaan_gizi"],
            } for item in report_mapping_rows}.values(),
            key=lambda item: int(item["nomor_makanan_sumber"] or 999),
        ),
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
            normalized_profile = normalisasi_status_alergi(text) if column == REQUIRED_COLUMNS[3] else text
            if not text or (normalized_profile not in options):
                (kosong if not text else invalid)[column] += 1
                errors.append({"response_id": rid, "source_row": row["source_row"], "kolom": column, "nilai_asli": original, "jenis": "kosong" if not text else "tidak_dikenal"})
        for token in parse_alergen(row.get(REQUIRED_COLUMNS[4]))[1]:
            invalid[REQUIRED_COLUMNS[4]] += 1
            errors.append({"response_id": rid, "source_row": row["source_row"], "kolom": REQUIRED_COLUMNS[4], "nilai_asli": row.get(REQUIRED_COLUMNS[4]), "token": token, "jenis": "tidak_dikenal"})
        raw_status = norm_teks(row.get(REQUIRED_COLUMNS[3]))
        normalized_status = normalisasi_status_alergi(raw_status)
        if raw_status and normalized_status and raw_status != normalized_status:
            errors.append({"response_id": rid, "source_row": row["source_row"], "kolom": REQUIRED_COLUMNS[3], "nilai_asli": raw_status, "nilai_normalisasi": normalized_status, "jenis": "alias_terkontrol"})
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
    alasan = ["Tahap persiapan: data final belum disetujui untuk pelatihan."]
    if not database_catalog:
        alasan.append("ID database belum diverifikasi terhadap database terpasang.")
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
    report.update({"kesalahan": errors, "peringatan": [] if database_catalog else [{"jenis": "id_database_belum_diverifikasi", "lokasi": "database aplikasi tidak diakses"}],
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
