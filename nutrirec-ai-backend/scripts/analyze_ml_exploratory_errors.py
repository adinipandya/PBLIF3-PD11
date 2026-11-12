"""Summarize saved exploratory test errors without fitting or changing models."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Invalid CSV header: {path}")
        return list(reader)


def verify_experiment(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed_exploratory_holdout_evaluation" or manifest.get("production_model") is not False:
        raise ValueError("Input is not a completed exploratory model evaluation")
    for name, expected in manifest.get("output_sha256", {}).items():
        if sha(folder / name) != expected:
            raise ValueError(f"Experiment output hash mismatch: {name}")
    for name, metadata in manifest["models"].items():
        if sha(folder / metadata["file"]) != metadata["sha256"]:
            raise ValueError(f"Model artifact hash mismatch: {name}")
    return manifest


def analyze(experiment_dir):
    folder = Path(experiment_dir)
    manifest = verify_experiment(folder)
    predictions = read_csv(folder / "test_predictions.csv")
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    split_dir = Path(manifest["source_split"])
    if not split_dir.is_absolute():
        split_dir = folder / split_dir
    split_dir = split_dir.resolve()
    test_rows = read_csv(split_dir / "test.csv")
    profiles = {(row["submission_uid"], row["no_makanan_excel"]): row for row in test_rows}
    result = {
        "source_experiment": str(folder.resolve()),
        "source_split": str(split_dir.resolve()),
        "source_split_manifest_sha256": sha(split_dir / "manifest.json"),
        "source_manifest_sha256": sha(folder / "manifest.json"),
        "test_prediction_rows": len(predictions),
        "model_summaries": {},
        "random_forest_true_class_2": {},
        "error_patterns": [],
        "examples": [],
        "interpretation": "Descriptive patterns in this single fixed holdout only; these do not establish causes or justify changing configuration.",
        "limitations": [
            "Test contains zero rating-1 rows; class-1 recall is not measurable.",
            "Test has no Prioritas Lemak profiles.",
            "Anonymous UID is a submission identifier, not a verified person identifier.",
            "All candidate rows remain marked for review and mappings/servings are not final.",
        ],
    }
    for name, model_metrics in metrics.items():
        model_rows = [row for row in predictions if row["model"] == name]
        pred_counts = Counter(row["y_pred"] for row in model_rows)
        result["model_summaries"][name] = {
            "metrics": model_metrics,
            "prediction_counts": {str(label): pred_counts[str(label)] for label in (1, 2, 3, 4)},
            "wrong_predictions": sum(row["y_true"] != row["y_pred"] for row in model_rows),
        }
    rf_rows = [r for r in predictions if r["model"] == "Random Forest" and r["y_true"] == "2"]
    counts = Counter(r["y_pred"] for r in rf_rows)
    result["random_forest_true_class_2"] = {
        "rows": len(rf_rows), "predicted_as": {str(label): counts[str(label)] for label in (1, 2, 3, 4)},
        "fraction_predicted_as_3": counts["3"] / len(rf_rows) if rf_rows else None,
    }
    errors = [r for r in predictions if r["y_true"] != r["y_pred"]]
    by_pattern = defaultdict(Counter)
    for row in errors:
        by_pattern[row["model"]][(row["y_true"], row["y_pred"])] += 1
    for model_name, transitions in sorted(by_pattern.items()):
        result["error_patterns"].append({"model": model_name, "transitions": [{"rating_asli": actual, "diprediksi": predicted, "jumlah": count} for (actual, predicted), count in sorted(transitions.items())]})
    rf_errors = [r for r in errors if r["model"] == "Random Forest"]
    # Show a stable, bounded selection of error examples rather than an inferred causal sample.
    examples = []
    for row in rf_errors[:12]:
        source = profiles.get((row["submission_uid"], row["no_makanan_excel"]), {})
        examples.append({**{k: row.get(k, "") for k in ("model", "response_id", "submission_uid", "evaluation_group_id", "nama_makanan_survei", "nama_makanan_dataset", "y_true", "y_pred", "prob_1", "prob_2", "prob_3", "prob_4", "status_pemetaan", "status_alergen_katalog", "definisi_prioritas")}, "profil_input": {"target_kalori": source.get("target_kalori", ""), "prioritas": source.get("prioritas", ""), "status_alergi": source.get("status_alergi", ""), **{f"alergen_{i}": source.get(f"alergen_{i}", "") for i in range(1, 12)}}, "fitur_gizi": {key: source.get(key, "") for key in ("kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g")}})
    result["examples"] = examples
    result["observed_only"] = [
        "Random Forest underpredicts the observed rating-2 class in this holdout; inspect its transition counts rather than attributing cause to respondents.",
        "Predicted-class counts show whether models collapse toward common classes.",
        "Profiles and food ratings are repeated within submission UID; row-level errors are correlated and not independent observations.",
    ]
    return manifest, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, report = analyze(args.experiment_dir)
        out = Path(args.output_dir)
        if out.exists():
            raise ValueError(f"Output exists: {out}")
        if args.dry_run:
            print(json.dumps({"models": {k: v["prediction_counts"] for k, v in report["model_summaries"].items()}, "class2_RF": report["random_forest_true_class_2"]}, indent=2))
            print("DRY RUN: no output written")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".error-analysis-stage-", dir=out.parent))
        try:
            (stage / "error_analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            fields = list(report["examples"][0]) if report["examples"] else []
            with (stage / "error_examples.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(report["examples"])
            result = {"status": "descriptive_exploratory_error_analysis", "source_experiment": Path(args.experiment_dir).name, "source_manifest_sha256": sha(Path(args.experiment_dir) / "manifest.json"), "input_sha256": {"predictions": sha(Path(args.experiment_dir) / "test_predictions.csv"), "metrics": sha(Path(args.experiment_dir) / "metrics.json")}, "output_sha256": {p.name: sha(p) for p in stage.iterdir()}}
            (stage / "manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            if out.exists(): raise ValueError(f"Output exists: {out}")
            os.rename(stage, out)
        finally:
            if stage.exists(): shutil.rmtree(stage)
        print(f"Analysis: {out}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
