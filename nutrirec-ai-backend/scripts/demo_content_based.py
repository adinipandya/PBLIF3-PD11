"""Run the PD11-R2 content-based recommender directly against a local catalog."""

import argparse
import csv
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.recommendation_rules import NUTRIENT_PRIORITIES  # noqa: E402
from app.models.alergen import Alergen, KandunganAlergen  # noqa: E402
from app.models.makanan import InformasiGizi, Makanan  # noqa: E402
from app.models.referensi import PrioritasNutrisi, TargetKalori  # noqa: E402
from app.schemas.personalisasi import PermintaanPersonalisasi  # noqa: E402
from app.services.makanan_service import (  # noqa: E402
    VERSI_ATURAN,
    _baca_nutrisi,
    filter_dan_rekomendasikan,
    hitung_skor_katalog,
)
import app.services.makanan_service as recommender_service  # noqa: E402
from scripts.import_dataset import baca_dataset, parse_alergen_tercatat  # noqa: E402

ALERGEN_IDS = {"Telur": 1, "Kedelai": 2, "Jagung": 3, "Kelapa": 4, "Ayam": 5,
               "Daging sapi": 6, "Gandum": 7, "Kacang-kacangan": 8,
               "Udang/seafood": 9, "Ikan": 10, "Beras": 11}
TARGET_IDS = {"Rendah": 1, "Sedang": 2, "Tinggi": 3}
PRIORITY_IDS = {name: i for i, name in enumerate((*NUTRIENT_PRIORITIES, "Seimbang"), 1)}


def load_records(path: Path) -> tuple[list[dict], str]:
    if path.suffix.lower() == ".xlsx":
        rows = baca_dataset(str(path))
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError("CSV katalog kosong.")
        mapping = {"A": "NO", "B": "NAMA", "C": "KALORI", "D": "KARBO", "E": "LEMAK", "F": "PROTEIN", "G": "PORSI", "M": "ALERGEN", "O": "STATUS AL."}
        headers = set(rows[0])
        if not set(mapping.values()).issubset(headers):
            raise ValueError("Header CSV wajib: NO,NAMA,KALORI,KARBO,LEMAK,PROTEIN,PORSI,ALERGEN,STATUS AL.")
        rows = [{key: row.get(column) for key, column in mapping.items()} for row in rows]
    else:
        raise ValueError("Dataset harus berformat .xlsx atau .csv.")
    return rows, hashlib.sha256(path.read_bytes()).hexdigest()


def decimal(value, field):
    if value is None or str(value).strip() == "":
        raise ValueError(f"kolom {field} kosong")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"kolom {field} bukan numerik")
    if not result.is_finite() or result < 0:
        raise ValueError(f"kolom {field} harus finite dan tidak negatif")
    return result


def build_catalog(rows):
    foods, exclusions = [], []
    for row_number, row in enumerate(rows, 1):
        try:
            food_id = int(row["A"])
            name = str(row["B"] or "").strip()
            if food_id <= 0 or not name:
                raise ValueError("ID makanan harus positif dan nama wajib ada")
            nutrition = [decimal(row.get(key), key) for key in ("C", "F", "D", "E")]
            calories, protein, carbs, fat = nutrition
            if 4 * protein + 4 * carbs + 9 * fat <= 0:
                raise ValueError("energi makro harus lebih dari nol")
            tokens = parse_alergen_tercatat(row.get("M"))
        except (KeyError, ValueError) as exc:
            exclusions.append({"baris_sumber": row_number, "id_makanan": row.get("A"), "nama": row.get("B"), "alasan": str(exc)})
            continue
        food = Makanan(id_makanan=food_id, nama_makanan=name,
                       deskripsi_porsi=row.get("G") or "Tidak tersedia",
                       sumber_data=row.get("N") or "Tidak tersedia",
                       versi_dataset=row.get("Q") or "revisi-PD11-R1")
        food.informasi_gizi = InformasiGizi(id_makanan=food_id, kalori=calories,
                                             protein=protein, karbohidrat=carbs, lemak=fat)
        status = row.get("O")
        food.kandungan_alergen = [KandunganAlergen(id_makanan=food_id,
            id_alergen=ALERGEN_IDS[token], status_verifikasi=status or "Belum diverifikasi",
            bahan_penyebab=token) for token in tokens]
        foods.append(food)
    if len({food.id_makanan for food in foods}) != len(foods):
        raise ValueError("ID makanan duplikat pada katalog.")
    return foods, exclusions


def calculate_details(foods, target, priority):
    valid = []
    for food in foods:
        nutrition = _baca_nutrisi(food)
        if nutrition is not None:
            calories, proportions = nutrition
            valid.append((food, calories, proportions))
    details, low, high = hitung_skor_katalog(valid, target, priority)
    return details, low, high


def run(dataset, target, priority, allergy, allergen_ids):
    if target not in TARGET_IDS or priority not in PRIORITY_IDS:
        raise ValueError("Target kalori/prioritas tidak dikenali.")
    if allergy not in {"memiliki", "tidak"}:
        raise ValueError("Status alergi harus 'memiliki' atau 'tidak'.")
    if len(allergen_ids) != len(set(allergen_ids)):
        raise ValueError("ID alergen duplikat tidak diperbolehkan.")
    if any(i not in ALERGEN_IDS.values() for i in allergen_ids):
        raise ValueError("ID alergen tidak dikenal; ID yang tersedia 1–11.")
    if allergy == "memiliki" and not allergen_ids:
        raise ValueError("Jika memiliki alergi, pilih minimal satu ID alergen.")
    if allergy == "tidak" and allergen_ids:
        raise ValueError("Jika tidak memiliki alergi, --alergen-ids harus kosong.")
    rows, digest = load_records(dataset)
    foods, invalid = build_catalog(rows)
    details, minimum, maximum = calculate_details(foods, target, priority)
    by_category = {i: TargetKalori(id_target=i, nama_kategori=n) for n, i in TARGET_IDS.items()}
    priorities = {i: PrioritasNutrisi(id_prioritas=i, nama_prioritas=n) for n, i in PRIORITY_IDS.items()}
    allergens = {i: Alergen(id_alergen=i, nama_alergen=n, kata_kunci=n.lower()) for n, i in ALERGEN_IDS.items()}
    class LocalCatalog:
        def get(self, model, key):
            return {TargetKalori: by_category, PrioritasNutrisi: priorities, Alergen: allergens}[model].get(key)
    class Request:
        target_kalori_id = TARGET_IDS[target]
        prioritas_id = PRIORITY_IDS[priority]
        status_alergi = allergy == "memiliki"
        alergen_ids = allergen_ids
    original_get = recommender_service.get_semua_makanan
    recommender_service.get_semua_makanan = lambda _db: foods
    try:
        result = filter_dan_rekomendasikan(LocalCatalog(), Request())
    finally:
        recommender_service.get_semua_makanan = original_get
    eligible_count = sum(1 for f in foods if f.id_makanan in details)
    filtered = []
    selected = set(allergen_ids)
    if allergy == "memiliki":
        for food in foods:
            if food.id_makanan not in details:
                continue
            links = food.kandungan_alergen
            if not links:
                reason = "relasi alergen kosong"
            elif any(link.id_alergen in selected for link in links):
                reason = "mengandung alergen pilihan"
            elif any(link.status_verifikasi != "Terverifikasi" for link in links):
                reason = "informasi alergen belum diverifikasi"
            else:
                continue
            filtered.append({"id_makanan": food.id_makanan, "nama": food.nama_makanan, "alasan": reason})
    recommendations = []
    for item in result:
        food = item["makanan"]
        d = details[food.id_makanan]
        if any(d[key] != item[key] for key in ("skor_kalori", "skor_prioritas", "skor_content_based")):
            raise RuntimeError("Skor CLI tidak cocok dengan mesin rekomendasi layanan.")
        g = food.informasi_gizi
        recommendations.append({"id_makanan": food.id_makanan, "nama_makanan": food.nama_makanan,
            "porsi": food.deskripsi_porsi, "kalori_kkal": float(g.kalori), "protein_g": float(g.protein),
            "karbohidrat_g": float(g.karbohidrat), "lemak_g": float(g.lemak), **d,
            "penjelasan": f"Skor kalori {d['skor_kalori']:.4f} dan skor prioritas {d['skor_prioritas']:.4f}; bobot masing-masing 0,5."})
    metadata = {"path": str(dataset.resolve()), "sha256": digest,
                "versi": next(iter({str(r.get("Q") or "revisi-PD11-R1") for r in rows}), "sumber-katalog")}
    payload = {"status": "ok" if recommendations else "kosong", "mode": "content_based", "versi_aturan": VERSI_ATURAN,
        "sumber_dataset": metadata, "input": {"target_kalori": target, "prioritas": priority, "status_alergi": allergy, "alergen_ids": allergen_ids},
        "ringkasan": {"jumlah_makanan_sumber": len(rows), "jumlah_makanan_bergizi_valid": eligible_count,
            "jumlah_dikeluarkan_data_invalid": len(invalid), "jumlah_kandidat_sebelum_top3": sum(1 for f in foods if f.id_makanan in details and (allergy != "memiliki" or f.id_makanan not in {x['id_makanan'] for x in filtered})),
            "jumlah_hasil": len(recommendations), "rentang_normalisasi_prioritas": {"minimum": minimum, "maksimum": maximum}},
        "rekomendasi": recommendations, "dikeluarkan_alergi": filtered, "jumlah_dikeluarkan_alergi": len(filtered), "data_gizi_invalid": invalid,
        "alasan_kosong": "Tidak ada kandidat setelah filter alergi wajib." if not recommendations else None,
        "catatan": "Bobot 0,5/0,5 dan rasio Seimbang 15/55/30 adalah parameter prototipe. Skor CB bukan prediksi ML atau probabilitas keamanan alergi.",
        "aturan_prioritas": {"metode": "min_max_proporsi_energi_katalog_valid_sebelum_filter_alergi" if priority in NUTRIENT_PRIORITIES else "kedekatan_ke_rasio_prototipe_15_55_30", "rentang_katalog": {"minimum": minimum, "maksimum": maximum}}}
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--target-kalori", required=True, choices=TARGET_IDS)
    parser.add_argument("--prioritas", required=True, choices=PRIORITY_IDS)
    parser.add_argument("--status-alergi", required=True, choices=("memiliki", "tidak"))
    parser.add_argument("--alergen-ids", type=int, nargs="*", default=[])
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = run(args.dataset, args.target_kalori, args.prioritas, args.status_alergi, args.alergen_ids)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.output_json:
            args.output_json.write_text(json.dumps({"status": "error", "mode": "content_based", "versi_aturan": VERSI_ATURAN, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
