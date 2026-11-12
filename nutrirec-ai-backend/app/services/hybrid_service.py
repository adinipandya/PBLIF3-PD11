"""Local hybrid inference backed by the saved exploratory Random Forest artifact."""

from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.services.makanan_service import urutkan_katalog_kandidat
from app.models.referensi import PrioritasNutrisi, TargetKalori
from scripts.demo_ml_exploratory import (
    LABELS,
    _load_model_context,
    class_probabilities,
    input_features,
)
from scripts.prepare_ml_features import FEATURES

ALPHA = 0.5
MODEL_NAME = "Random Forest"
REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "data/experiments/survey-v001/ml-eval-exploratory-001"
EXPERIMENT_ID = "pd11-r2-cleanup-003"
EXPERIMENTAL_WARNING = (
    "Hybrid memakai artefak ML eksploratif, bukan model produksi; skor bukan "
    "probabilitas, saran medis, atau jaminan keamanan alergi."
)


class HybridModelUnavailableError(RuntimeError):
    """The saved exploratory pipeline or its metadata cannot be used."""


@lru_cache(maxsize=1)
def _load_saved_model():
    """Load and validate the saved pipeline once; inference never fits a model."""
    try:
        manifest, model_path, config, model = _load_model_context(MODEL_DIR, MODEL_NAME)
        if manifest.get("source_run_id") != EXPERIMENT_ID:
            raise ValueError("Artefak model bukan berasal dari eksperimen yang diharapkan.")
    except (OSError, ImportError, KeyError, ValueError) as exc:
        raise HybridModelUnavailableError("Artefak model hybrid lokal tidak valid atau tidak tersedia.") from exc
    return config, model


def rekomendasi_hybrid(db: Session, permintaan) -> dict:
    """Filter through the canonical CB/allergy service, blend scores, then rank."""
    kandidat_cb = urutkan_katalog_kandidat(db, permintaan)
    if not kandidat_cb:
        return {"versi_model": EXPERIMENT_ID, "jumlah_kandidat": 0, "kandidat": [], "pesan_kosong": "Tidak ada kandidat yang lolos filter alergi dan validasi gizi."}

    # The trained survey uses legacy Seimbang to mean no special preference.
    # The CB service's Seimbang is a 15/55/30 target, so blending them is invalid.
    prioritas = db.get(PrioritasNutrisi, permintaan.prioritas_id)
    if prioritas is None:
        raise ValueError("ID prioritas nutrisi tidak ditemukan.")
    if prioritas.nama_prioritas == "Seimbang":
        raise NotImplementedError("Hybrid belum mendukung prioritas Seimbang karena makna label survei berbeda dari skor Seimbang content-based.")

    config, model = _load_saved_model()
    target = db.get(TargetKalori, permintaan.target_kalori_id)
    if target is None:
        raise ValueError("ID target kalori tidak ditemukan.")
    alergen_ids = list(permintaan.alergen_ids)
    features = [
        input_features(
            target.nama_kategori,
            prioritas.nama_prioritas,
            "memiliki" if permintaan.status_alergi else "tidak",
            alergen_ids,
            float(row["makanan"].informasi_gizi.kalori),
            float(row["makanan"].informasi_gizi.protein),
            float(row["makanan"].informasi_gizi.karbohidrat),
            float(row["makanan"].informasi_gizi.lemak),
        )
        for row in kandidat_cb
    ]
    matrix = np.asarray([[item[name] for name in FEATURES] for item in features], dtype=object)
    try:
        predictions = model.predict(matrix).astype(int)
        probabilities = class_probabilities(model, matrix)
    except (ValueError, RuntimeError, AttributeError) as exc:
        raise HybridModelUnavailableError("Model hybrid tersimpan gagal menghasilkan prediksi.") from exc

    ranked = []
    for row, prediction, class_probs in zip(kandidat_cb, predictions, probabilities):
        if int(prediction) not in LABELS or not np.isclose(class_probs.sum(), 1.0, atol=1e-8):
            raise ValueError("Prediksi model tidak sesuai dengan kelas rating 1–4.")
        expected_rating = float(sum(label * class_probs[label - 1] for label in LABELS))
        score_ml = 100.0 * (expected_rating - 1.0) / 3.0
        score_hybrid = ALPHA * row["skor_content_based"] + (1.0 - ALPHA) * score_ml
        ranked.append((score_hybrid, row))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["makanan"].id_makanan))

    output = []
    for score_hybrid, row in ranked[:3]:
        food, nutrition = row["makanan"], row["makanan"].informasi_gizi
        output.append({
            "id_makanan": food.id_makanan,
            "nama_makanan": food.nama_makanan,
            "deskripsi_porsi": food.deskripsi_porsi,
            "berat_porsi_gram": food.berat_porsi_gram,
            "kalori": nutrition.kalori,
            "protein": nutrition.protein,
            "karbohidrat": nutrition.karbohidrat,
            "lemak": nutrition.lemak,
            "skor_hybrid": score_hybrid,
        })
    return {
        "versi_model": f"{MODEL_NAME}:{config['source_run_id']}",
        "jumlah_kandidat": len(output),
        "kandidat": output,
        "pesan_kosong": None,
    }
