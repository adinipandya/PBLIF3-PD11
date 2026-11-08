"""Functional matrix tests for the exploratory hybrid demo; no fitting is performed."""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.demo_ml_exploratory import infer_hybrid
from scripts.train_ml_exploratory import sha

TARGETS = ("Rendah", "Sedang", "Tinggi")
PRIORITIES = ("Protein", "Karbohidrat", "Lemak", "Seimbang")
ALLERGIES = (("tidak", []), ("memiliki", [1]), ("memiliki", [1, 2]))
MODEL_DIR = Path("../data/experiments/survey-v001/ml-eval-exploratory-001")
DATASET = Path("../data/Dataset_makanan_revisi.xlsx")


def results_equivalent(left, right, tolerance=1e-12):
    """Compare deterministic rankings and allow only machine-roundoff score/probability drift."""
    if left.keys() != right.keys():
        return False
    numeric_keys = {"S_CB", "S_ML", "S_hybrid", "expected_rating", "skor_kalori", "skor_prioritas", "alpha", "1", "2", "3", "4"}
    def equivalent(a, b, key=None):
        if isinstance(a, dict) and isinstance(b, dict):
            return a.keys() == b.keys() and all(equivalent(a[k], b[k], k) for k in a)
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and key in numeric_keys:
            return abs(a - b) <= tolerance
        return a == b
    return equivalent(left, right)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError(f"Output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)

    scenarios = []
    repeats_match = True
    for target in TARGETS:
        for priority in PRIORITIES:
            for status, allergen_ids in ALLERGIES:
                result = infer_hybrid(MODEL_DIR, DATASET, "Random Forest", target, priority, status, allergen_ids, 0.5)
                repeated = infer_hybrid(MODEL_DIR, DATASET, "Random Forest", target, priority, status, allergen_ids, 0.5)
                if not results_equivalent(result, repeated):
                    repeats_match = False
                candidates = result.get("rekomendasi_demo", [])
                invalid_scores = []
                ids = [item["id_makanan"] for item in candidates]
                if len(ids) != len(set(ids)):
                    invalid_scores.append("duplikat makanan pada Top 3")
                if len(candidates) > 3:
                    invalid_scores.append("lebih dari 3 makanan ditampilkan")
                if result.get("jumlah_kandidat_setelah_filter_alergi", 0) < len(candidates):
                    invalid_scores.append("hasil lebih banyak daripada kandidat")
                if priority != "Seimbang" and result.get("status") == "ok":
                    if result.get("jumlah_kandidat_sama_untuk_semua_ranking") != result.get("jumlah_kandidat_setelah_filter_alergi"):
                        invalid_scores.append("jumlah kandidat ranking berbeda")
                    for key, expected_rank in (("top3_cb", "S_CB"), ("top3_ml", "S_ML"), ("top3_hybrid_all", "S_hybrid")):
                        ranked = result.get(key, [])
                        if len({r["id_makanan"] for r in ranked}) != len(ranked):
                            invalid_scores.append(f"duplikat pada ranking {key}")
                        if any(ranked[i][expected_rank] < ranked[i+1][expected_rank] for i in range(len(ranked)-1)):
                            invalid_scores.append(f"ranking {key} tidak menurun")
                    for item in candidates:
                        if not (0 <= item["S_CB"] <= 100 and 0 <= item["S_ML"] <= 100 and 0 <= item["S_hybrid"] <= 100):
                            invalid_scores.append("skor di luar 0-100")
                    if any(candidates[i]["S_hybrid"] < candidates[i+1]["S_hybrid"] for i in range(len(candidates)-1)):
                        invalid_scores.append("ranking hybrid tidak menurun")
                status_class = "berhasil_fungsional"
                if result.get("dukungan_cb_seimbang") is False:
                    status_class = "belum_didukung_cb_seimbang"
                elif result.get("status") == "kosong":
                    status_class = "kosong_sesuai_filter_alergi" if status == "memiliki" else "kosong_tidak_terduga"
                if invalid_scores:
                    status_class = "gagal_validasi"
                scenario = {
                    "input": {"target_kalori": target, "prioritas": priority, "status_alergi": status, "alergen_ids": allergen_ids, "alpha": 0.5, "model": "Random Forest"},
                    "mode_aktual": result.get("mode"), "status": result.get("status"), "klasifikasi_hasil": status_class,
                    "jumlah_kandidat_setelah_filter_alergi": result.get("jumlah_kandidat_setelah_filter_alergi", 0),
                    "hasil_top3": candidates,
                    "top3_CB": result.get("top3_cb", []), "top3_ML": result.get("top3_ml", []),
                    "top3_hybrid_all": result.get("top3_hybrid_all", []),
                    "alasan_kosong": result.get("alasan_kosong"), "catatan_CB": result.get("catatan_cb"),
                    "makanan_dikeluarkan_alergi": result.get("makanan_dikeluarkan_alergi", []),
                    "validasi_skor": invalid_scores, "input_sama_hasil_sama": result == repeated,
                }
                scenarios.append(scenario)

    lines = [
        "# Functional hybrid scenario matrix",
        "",
        "Functional checks on actual catalog and saved Random Forest pipeline; no training/splitting performed.",
        "Hybrid remains exploratory; functional pass is not evidence of improved recommendation quality.",
        "",
        "| Target | Prioritas | Alergi | Mode/status | Kandidat | Hasil maksimal 3 (skor) | Catatan |",
        "|---|---|---|---|---:|---|---|",
    ]
    for item in scenarios:
        inp = item["input"]
        allergy = "tidak" if inp["status_alergi"] == "tidak" else "+".join(map(str, inp["alergen_ids"]))
        picks = ", ".join(f"{food['nama_makanan']} (CB {food.get('S_CB')}, ML {food['S_ML']:.2f}, H {food.get('S_hybrid')})" for food in item["hasil_top3"])
        note = item["alasan_kosong"] or item["catatan_CB"] or item["klasifikasi_hasil"]
        lines.append(f"| {inp['target_kalori']} | {inp['prioritas']} | {allergy} | {item['mode_aktual']}/{item['status']} | {item['jumlah_kandidat_setelah_filter_alergi']} | {picks or '—'} | {note} |")
    (output / "scenario_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "scenario_results.json").write_text(json.dumps(scenarios, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = Counter(s["klasifikasi_hasil"] for s in scenarios)
    manifest = {
        "status": "functional_scenario_matrix_completed", "scenario_count": len(scenarios),
        "successful": counts["berhasil_fungsional"], "empty_allergy_expected": counts["kosong_sesuai_filter_alergi"],
        "unsupported_balanced": counts["belum_didukung_cb_seimbang"], "failed": counts["gagal_validasi"] + counts["kosong_tidak_terduga"],
        "all_repeats_match": repeats_match, "alpha": 0.5,
        "source_experiment_manifest_sha256": sha(MODEL_DIR / "manifest.json"), "catalog_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "notes": ["Lemak tidak ada di holdout eksperimen sebelumnya; generalisasi pada prioritas Lemak belum dievaluasi.", "Seimbang legacy survey tidak dipetakan ke CB 15/55/30.", "Alergi tetap filter wajib; data belum terverifikasi tidak diloloskan.", "Hasil fungsional bukan bukti kualitas meningkat."],
        "output_sha256": {name: sha(output / name) for name in ("scenario_matrix.md", "scenario_results.json")},
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if len(scenarios) == 36 and repeats_match and manifest["failed"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
