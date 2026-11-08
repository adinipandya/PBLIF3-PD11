"""Read-only inference demo for saved exploratory ML pipelines; never trains models."""

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.prepare_ml_features import FEATURES
from scripts.prepare_ml_exploratory_split import ALLERGENS, TEST_FRACTION, VERSION as SPLIT_VERSION
from scripts.train_ml_exploratory import LABELS, class_probabilities, read_csv, sha
from app.core.recommendation_rules import NUTRIENT_PRIORITIES
from app.services.makanan_service import (
    _baca_nutrisi,
    urutkan_katalog_kandidat,
    hitung_skor_katalog,
)
from app.models.alergen import Alergen, KandunganAlergen
from app.models.makanan import InformasiGizi, Makanan
from app.models.referensi import PrioritasNutrisi, TargetKalori
from app.schemas.personalisasi import PermintaanPersonalisasi

TARGETS = {"Rendah": "Rendah", 1: "Rendah", "Sedang": "Sedang", 2: "Sedang", "Tinggi": "Tinggi", 3: "Tinggi"}
PRIORITIES = {"Protein": "Protein", "Karbohidrat": "Karbohidrat", "Lemak": "Lemak", "Seimbang": "Seimbang (tidak ada prioritas khusus)"}
ALLERGEN_IDS = {"telur": 1, "Telur": 1, "kedelai": 2, "Kedelai": 2, "jagung": 3, "Jagung": 3, "kelapa": 4, "Kelapa": 4, "ayam": 5, "Ayam": 5, "daging sapi": 6, "Daging sapi": 6, "gandum": 7, "Gandum": 7, "kacang-kacangan": 8, "Kacang-kacangan": 8, "udang/seafood": 9, "Udang/seafood": 9, "ikan": 10, "Ikan": 10, "beras": 11, "Beras": 11}
DISPLAY = {1: "Sangat tidak sesuai (mengandung bahan yang membuat saya alergi)", 2: "Tidak sesuai", 3: "Sesuai", 4: "Sangat sesuai"}


def validate_artifacts(model_dir, model_name):
    folder = Path(model_dir)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed_exploratory_holdout_evaluation" or manifest.get("production_model") is not False:
        raise ValueError("Artefak bukan kandidat eksperimen eksploratif yang didukung")
    if model_name not in manifest.get("models", {}):
        raise ValueError(f"Model tidak tersedia: {model_name}")
    expected = manifest["models"][model_name]["sha256"]
    model_path = folder / manifest["models"][model_name]["file"]
    if sha(model_path) != expected:
        raise ValueError("Hash model tersimpan tidak cocok dengan manifest")
    return manifest, model_path


def load_catalog(path):
    p = Path(path)
    if p.suffix.lower() == ".xlsx":
        from scripts.import_dataset import baca_dataset
        rows = baca_dataset(str(p))
        mapped = [{"id": r["A"], "name": r["B"], "calories": r["C"], "carbs": r["D"], "fat": r["E"], "protein": r["F"], "portion": r["G"], "allergens": r.get("M"), "allergen_status": r.get("O") or "Belum diverifikasi"} for r in rows]
    elif p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8-sig", newline="") as f:
            records = list(csv.DictReader(f))
        required = {"NO", "NAMA", "KALORI", "KARBO", "LEMAK", "PROTEIN", "PORSI"}
        if not records or not required.issubset(records[0]):
            raise ValueError("CSV perlu header NO,NAMA,KALORI,KARBO,LEMAK,PROTEIN,PORSI")
        mapped = [{"id": r["NO"], "name": r["NAMA"], "calories": r["KALORI"], "carbs": r["KARBO"], "fat": r["LEMAK"], "protein": r["PROTEIN"], "portion": r["PORSI"], "allergens": r.get("ALERGEN"), "allergen_status": r.get("STATUS AL.") or "Belum diverifikasi"} for r in records]
    else:
        raise ValueError("Katalog harus .xlsx atau .csv")
    return mapped, hashlib.sha256(p.read_bytes()).hexdigest()


def parse_number(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} harus berupa angka") from exc
    if not np.isfinite(number) or number < 0:
        raise ValueError(f"{field} harus finite dan tidak negatif")
    return number


def input_features(target, priority, allergy_status, allergen_ids, calories, protein, carbs, fat):
    if target not in PRIORITIES and target not in {"Rendah", "Sedang", "Tinggi"}:
        raise ValueError("Target kalori atau prioritas tidak dikenal")
    if priority not in PRIORITIES:
        raise ValueError("Prioritas tidak dikenal")
    if allergy_status not in {"memiliki", "tidak"}:
        raise ValueError("Status alergi harus memiliki/tidak")
    if len(set(allergen_ids)) != len(allergen_ids):
        raise ValueError("ID alergen duplikat")
    if any(i not in ALLERGENS.values() for i in allergen_ids):
        raise ValueError("ID alergen harus ada pada kamus eksplisit 1–11")
    if allergy_status == "memiliki" and not allergen_ids:
        raise ValueError("Pilih minimal satu ID jika memiliki alergi")
    if allergy_status == "tidak" and allergen_ids:
        raise ValueError("Daftar alergen harus kosong jika tidak memiliki alergi")
    vals = {"kalori_kkal": calories, "protein_g": protein, "karbohidrat_g": carbs, "lemak_g": fat}
    if 4 * protein + 4 * carbs + 9 * fat <= 0:
        raise ValueError("Energi makro harus positif")
    features = {
        "target_kalori": target if isinstance(target, str) else TARGETS[target],
        "prioritas": PRIORITIES[priority],
        "status_alergi": 1 if allergy_status == "memiliki" else 0,
    }
    features.update({f"alergen_{i}": int(i in allergen_ids) for i in ALLERGENS.values()})
    features.update(vals)
    return features


def combine_and_rank(cb_by_id, ml_rows, alpha):
    """Combine two already-filtered score maps, keeping original-precision scores."""
    combined = []
    for row in ml_rows:
        cb = cb_by_id[row["makanan"].id_makanan]
        score = alpha * cb["skor_content_based"] + (1.0 - alpha) * row["S_ML"]
        combined.append({**row, "CB": cb, "S_hybrid": score})
    return sorted(combined, key=lambda item: (-item["S_hybrid"], item["makanan"].id_makanan))

def _load_model_context(model_dir, model_name):
    manifest, model_path = validate_artifacts(model_dir, model_name)
    split_dir = Path(manifest["source_split"])
    if not split_dir.exists():
        raise ValueError("Direktori split sumber tidak tersedia")
    split_manifest = json.loads((split_dir / "manifest.json").read_text(encoding="utf-8"))
    if split_manifest.get("source_run_id") != "pd11-r2-cleanup-003" or split_manifest.get("ready_for_training") is not False:
        raise ValueError("Model tidak berakar pada split eksploratif cleanup-003")
    schema_path = split_dir / "feature_schema.json"
    if sha(schema_path) != manifest["input_sha256"]["schema"]:
        raise ValueError("Hash schema fitur tidak cocok")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    config = json.loads((Path(model_dir) / "experiment_config.json").read_text(encoding="utf-8"))
    if schema.get("fitur_diizinkan") != FEATURES or config.get("feature_order") != FEATURES:
        raise ValueError("Urutan/schema fitur tidak cocok dengan artefak model")
    model = joblib.load(model_path)
    if not hasattr(model, "predict") or not hasattr(model, "predict_proba"):
        raise ValueError("Pipeline tersimpan tidak menyediakan predict dan predict_proba")
    return manifest, model_path, config, model

def _infer_hybrid(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids, alpha=0.5):
    if priority not in PRIORITIES:
        raise ValueError("Prioritas tidak dikenal")
    if not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("Alpha harus angka finite pada rentang 0 sampai 1")
    manifest, model_path, config, model = _load_model_context(model_dir, model_name)
    records, catalog_hash = load_catalog(dataset)
    from scripts.import_dataset import parse_alergen_tercatat

    target_ids = {"Rendah": 1, "Sedang": 2, "Tinggi": 3}
    priority_ids = {"Protein": 1, "Karbohidrat": 2, "Lemak": 3, "Seimbang": 4}
    targets = {1: "Rendah", 2: "Sedang", 3: "Tinggi"}
    ref_targets = {i: TargetKalori(id_target=i, nama_kategori=n) for i, n in targets.items()}
    ref_priorities = {i: PrioritasNutrisi(id_prioritas=i, nama_prioritas=n) for n, i in priority_ids.items()}
    ref_allergens = {i: Alergen(id_alergen=i, nama_alergen=n, kata_kunci=str(n).lower()) for n, i in ALLERGEN_IDS.items()}

    foods, features_by_id, invalid = [], {}, []
    for item in records:
        try:
            food_id = int(item["id"])
            calories = parse_number(item["calories"], "Kalori")
            protein = parse_number(item["protein"], "Protein")
            carbs = parse_number(item["carbs"], "Karbohidrat")
            fat = parse_number(item["fat"], "Lemak")
            name = str(item["name"]).strip()
            if not name:
                raise ValueError("Nama makanan kosong")
            tokens = parse_alergen_tercatat(item.get("allergens"))
            feature = input_features(target, priority, allergy_status, allergen_ids, calories, protein, carbs, fat)
        except (ValueError, KeyError) as exc:
            invalid.append({"id": item.get("id"), "name": item.get("name"), "reason": str(exc)})
            continue
        food = Makanan(id_makanan=food_id, nama_makanan=name,
                       deskripsi_porsi=item.get("portion") or "Tidak tersedia",
                       sumber_data="local catalog")
        food.informasi_gizi = InformasiGizi(id_makanan=food_id, kalori=calories,
            protein=protein, karbohidrat=carbs, lemak=fat)
        food.kandungan_alergen = [KandunganAlergen(
            id_makanan=food_id, id_alergen=ALLERGEN_IDS[token],
            status_verifikasi=item.get("allergen_status") or "Belum diverifikasi",
            bahan_penyebab=token) for token in tokens]
        if _baca_nutrisi(food) is None:
            invalid.append({"id": food_id, "name": name, "reason": "Gizi invalid menurut layanan CB"})
            continue
        if food_id in features_by_id:
            raise ValueError(f"ID makanan duplikat dalam katalog: {food_id}")
        foods.append(food)
        features_by_id[food_id] = {"features": feature, "source": item}

    class LocalCatalog:
        def get(self, model_class, key):
            return {TargetKalori: ref_targets, PrioritasNutrisi: ref_priorities,
                    Alergen: ref_allergens}[model_class].get(key)

    class Request:
        target_kalori_id = target_ids[target]
        prioritas_id = priority_ids[priority]
        status_alergi = allergy_status == "memiliki"
        alergen_ids = allergen_ids

    import app.services.makanan_service as shared_service
    original_get = shared_service.get_semua_makanan
    shared_service.get_semua_makanan = lambda _db: foods
    try:
        # This common service helper applies mandatory allergy validation/filtering and returns all eligible candidates.
        eligible = urutkan_katalog_kandidat(LocalCatalog(), Request())
    finally:
        shared_service.get_semua_makanan = original_get

    allergy_excluded = []
    if allergy_status == "memiliki":
        selected_ids = set(allergen_ids)
        eligible_ids = {row["makanan"].id_makanan for row in eligible}
        for food in foods:
            if food.id_makanan in eligible_ids:
                continue
            links = food.kandungan_alergen
            if any(link.id_alergen in selected_ids for link in links):
                reason = "mengandung alergen pilihan"
            elif not links:
                reason = "relasi alergen kosong"
            else:
                reason = "informasi alergen belum diverifikasi"
            allergy_excluded.append({"id_makanan": food.id_makanan, "nama_makanan": food.nama_makanan, "alasan": reason})

    if not eligible:
        return {"mode": "hybrid_eksploratif", "status": "kosong", "model": model_name,
                "jumlah_kandidat_setelah_filter_alergi": 0, "jumlah_hasil_top3": 0,
                "rekomendasi_demo": [], "alasan_kosong": "Tidak ada kandidat setelah filter alergi wajib.",
                "makanan_dikeluarkan_input_invalid": invalid, "makanan_dikeluarkan_alergi": allergy_excluded,
                "peringatan": "Tidak ada makanan yang dimasukkan kembali setelah filter alergi."}

    cb_supported = priority != "Seimbang"
    if cb_supported:
        # Preserve the full candidate ranking from the shared service helper.
        cb_ranked_full = eligible
        cb_details_by_id = {row["makanan"].id_makanan: {key: row[key] for key in ("skor_kalori", "skor_prioritas", "skor_content_based")} for row in cb_ranked_full}
        eligible = cb_ranked_full
    else:
        # Do not invoke CB with legacy "no special priority" as if it meant the new 15/55/30 ratio.
        ml_eligible_foods = [food for food in foods if allergy_status != "memiliki" or _lolos_alergi(food, set(allergen_ids))]
        cb_details_by_id = {}
        cb_ranked_full = []
        ml_features_by_id = features_by_id
        if not ml_eligible_foods:
            return {"mode": "ml_eksploratif_cb_seimbang_tidak_didukung", "status": "kosong", "model": model_name,
                    "dukungan_cb_seimbang": False, "jumlah_kandidat_setelah_filter_alergi": 0,
                    "top3_cb": [], "top3_ml": [], "rekomendasi_demo": [], "catatan_cb": "Seimbang legacy tidak dipetakan ke CB 15/55/30.",
                    "alasan_kosong": "Tidak ada kandidat setelah filter alergi wajib; fallback ML tidak mengendurkan filter."}
        eligible = [{"makanan": food} for food in ml_eligible_foods]
        features_by_id = {food.id_makanan: features_by_id[food.id_makanan] for food in ml_eligible_foods}

    matrix = np.asarray([[features_by_id[row["makanan"].id_makanan]["features"][name] for name in FEATURES] for row in eligible], dtype=object)
    predictions = model.predict(matrix).astype(int)
    aligned_probabilities = class_probabilities(model, matrix)
    scored = []
    for candidate, prediction, probabilities in zip(eligible, predictions, aligned_probabilities):
        if int(prediction) not in LABELS or not np.isclose(probabilities.sum(), 1.0, atol=1e-8):
            raise ValueError("Model prediction/probabilities do not match rating classes 1-4")
        expected_rating = float(sum(label * probabilities[label - 1] for label in LABELS))
        score_ml = 100.0 * (expected_rating - 1.0) / 3.0
        food = candidate["makanan"]
        cb = cb_details_by_id.get(food.id_makanan)
        score_hybrid = alpha * cb["skor_content_based"] + (1.0 - alpha) * score_ml if cb else None
        scored.append({"makanan": food, "features": features_by_id[food.id_makanan]["features"],
                       "prediction": int(prediction), "probabilities": probabilities,
                       "expected_rating": expected_rating, "S_ML": score_ml,
                       "CB": cb, "S_hybrid": score_hybrid})

    ml_ranked = sorted(scored, key=lambda row: (-row["S_ML"], row["makanan"].id_makanan))
    if cb_supported:
        by_id = {row["makanan"].id_makanan: row for row in scored}
        cb_ranked = [by_id[row["makanan"].id_makanan] for row in cb_ranked_full]
        hybrid_ranked = combine_and_rank(cb_details_by_id, ml_ranked, alpha)
    else:
        cb_ranked = []
        hybrid_ranked = ml_ranked

    def present(row):
        food, cb = row["makanan"], row["CB"]
        return {"id_makanan": food.id_makanan, "nama_makanan": food.nama_makanan,
                "porsi": food.deskripsi_porsi, "kalori_kkal": row["features"]["kalori_kkal"],
                "protein_g": row["features"]["protein_g"], "karbohidrat_g": row["features"]["karbohidrat_g"],
                "lemak_g": row["features"]["lemak_g"], "skor_kalori": cb["skor_kalori"] if cb else None,
                "skor_prioritas": cb["skor_prioritas"] if cb else None, "S_CB": cb["skor_content_based"] if cb else None,
                "prediksi_rating": row["prediction"], "probabilitas_kelas": {str(label): float(row["probabilities"][label - 1]) for label in LABELS},
                "expected_rating": row["expected_rating"], "S_ML": row["S_ML"], "alpha": alpha if cb else None,
                "S_hybrid": row["S_hybrid"], "fitur_input": row["features"]}

    ml_only_mode = not cb_supported
    candidate_count = len(scored)
    return {"mode": "ml_eksploratif_cb_seimbang_tidak_didukung" if ml_only_mode else "hybrid_eksploratif",
            "status": "ok", "model": model_name, "versi_eksperimen": config["mode"] + ":" + config["source_run_id"],
            "sumber_model": str(model_path.resolve()), "hash_katalog": catalog_hash,
            "input_pengguna": {"target_kalori": target, "prioritas_survei": PRIORITIES[priority], "status_alergi": allergy_status,
                               "alergen_ids": allergen_ids, "alpha": alpha if cb_supported else None},
            "jumlah_kandidat_setelah_filter_alergi": candidate_count, "jumlah_kandidat_sama_untuk_semua_ranking": candidate_count,
            "jumlah_hasil_top3": min(3, len(hybrid_ranked)), "dukungan_cb_seimbang": cb_supported,
            "peringatan": "Hybrid/ML eksploratif; S_ML adalah nilai harapan rating tertransformasi, bukan akurasi/keamanan. Filter alergi wajib tetap berlaku. Belum model produksi atau klaim peningkatan.",
            "catatan_cb": "Seimbang survei legacy = tanpa prioritas khusus; tidak dipetakan ke 15/55/30." if ml_only_mode else "S_CB dihitung oleh helper layanan CB bersama.",
            "top3_cb": [present(row) for row in cb_ranked[:3]], "top3_ml": [present(row) for row in ml_ranked[:3]],
            "top3_hybrid_all": [present(row) for row in hybrid_ranked], "rekomendasi_demo": [present(row) for row in hybrid_ranked[:3]],
            "makanan_dikeluarkan_input_invalid": invalid, "makanan_dikeluarkan_alergi": allergy_excluded}

def _infer_ml_only(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids):
    """Standalone exploratory rating inference, retaining the previous infer() contract."""
    manifest, model_path, config, model = _load_model_context(model_dir, model_name)
    records, catalog_hash = load_catalog(dataset)
    from scripts.import_dataset import parse_alergen_tercatat
    foods, features_by_id, excluded = [], {}, []
    for item in records:
        try:
            food_id = int(item["id"])
            values = {"calories": parse_number(item["calories"], "Kalori"), "protein": parse_number(item["protein"], "Protein"),
                      "carbs": parse_number(item["carbs"], "Karbohidrat"), "fat": parse_number(item["fat"], "Lemak")}
            tokens = parse_alergen_tercatat(item.get("allergens"))
            feature = input_features(target, priority, allergy_status, allergen_ids, values["calories"], values["protein"], values["carbs"], values["fat"])
        except (ValueError, KeyError) as exc:
            excluded.append({"id": item.get("id"), "name": item.get("name"), "reason": str(exc)})
            continue
        food = Makanan(id_makanan=food_id, nama_makanan=str(item["name"]), deskripsi_porsi=item.get("portion") or "Tidak tersedia", sumber_data="local catalog")
        food.informasi_gizi = InformasiGizi(id_makanan=food_id, kalori=values["calories"], protein=values["protein"], karbohidrat=values["carbs"], lemak=values["fat"])
        food.kandungan_alergen = [KandunganAlergen(id_makanan=food_id, id_alergen=ALLERGEN_IDS[token], status_verifikasi=item.get("allergen_status") or "Belum diverifikasi", bahan_penyebab=token) for token in tokens]
        foods.append(food); features_by_id[food_id] = (item, feature)
    class LocalCatalog:
        def get(self, model_class, key):
            targets = {1: "Rendah", 2: "Sedang", 3: "Tinggi"}
            priorities = {1: "Protein", 2: "Karbohidrat", 3: "Lemak", 4: "Seimbang"}
            maps = {TargetKalori: {i: TargetKalori(id_target=i, nama_kategori=name) for i, name in targets.items()},
                    PrioritasNutrisi: {i: PrioritasNutrisi(id_prioritas=i, nama_prioritas=name, jenis="seimbang" if name == "Seimbang" else "zat_gizi") for i, name in priorities.items()},
                    Alergen: {i: Alergen(id_alergen=i, nama_alergen=name, kata_kunci=str(name).lower()) for name, i in ALLERGEN_IDS.items()}}
            return maps[model_class].get(key)
    class Request:
        target_kalori_id = {"Rendah": 1, "Sedang": 2, "Tinggi": 3}[target]
        prioritas_id = {"Protein": 1, "Karbohidrat": 2, "Lemak": 3, "Seimbang": 4}[priority]
        status_alergi = allergy_status == "memiliki"
        alergen_ids = allergen_ids
    import app.services.makanan_service as shared_service
    original = shared_service.get_semua_makanan
    shared_service.get_semua_makanan = lambda _db: foods
    try:
        eligible = urutkan_katalog_kandidat(LocalCatalog(), Request())
    finally:
        shared_service.get_semua_makanan = original
    features = np.asarray([[features_by_id[item["makanan"].id_makanan][1][name] for name in FEATURES] for item in eligible], dtype=object)
    predictions = model.predict(features).astype(int) if eligible else np.asarray([], dtype=int)
    probabilities = class_probabilities(model, features) if eligible else np.empty((0, 4))
    results = []
    for candidate, pred, probs in zip(eligible, predictions, probabilities):
        food = candidate["makanan"]; source, feature = features_by_id[food.id_makanan]
        results.append({"id_makanan": food.id_makanan, "nama_makanan": food.nama_makanan, "porsi": food.deskripsi_porsi, "fitur_input": feature,
                        "prediksi_rating": int(pred), "probabilitas_kelas": {str(label): float(probs[label-1]) for label in LABELS}})
    return {"mode": "demo_model_eksploratif", "status": "ok" if results else "kosong", "model": model_name, "hash_katalog": catalog_hash,
            "peringatan": "Prediksi rating eksploratif bukan keputusan keamanan alergi dan tidak menggantikan filter alergi.", "rekomendasi_demo_model": results[:3], "makanan_dikeluarkan": excluded}


def infer(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids):
    return _infer_ml_only(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids)


def infer_hybrid(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids, alpha=0.5):
    return _infer_hybrid(model_dir, dataset, model_name, target, priority, allergy_status, allergen_ids, alpha)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--model", default="Random Forest", choices=("Dummy", "Decision Tree", "Random Forest", "KNN"))
    parser.add_argument("--target-kalori", required=True, choices=tuple(TARGETS))
    parser.add_argument("--prioritas", required=True, choices=tuple(PRIORITIES))
    parser.add_argument("--status-alergi", required=True, choices=("memiliki", "tidak"))
    parser.add_argument("--alergen-ids", type=int, nargs="*", default=[])
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--hybrid", action="store_true", help="Use exploratory CB+ML ranking (not production)")
    args = parser.parse_args(argv)
    try:
        if args.hybrid:
            result = infer_hybrid(args.model_dir, args.dataset, args.model, args.target_kalori, args.prioritas, args.status_alergi, args.alergen_ids, args.alpha)
        else:
            result = infer(args.model_dir, args.dataset, args.model, args.target_kalori, args.prioritas, args.status_alergi, args.alergen_ids)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
