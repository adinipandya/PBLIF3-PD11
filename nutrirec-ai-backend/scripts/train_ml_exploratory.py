"""Train and evaluate exploratory ML candidates on a supplied fixed holdout."""

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import scipy
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_absolute_error, precision_recall_fscore_support
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.prepare_ml_features import FEATURES
from scripts.prepare_ml_exploratory_split import VERSION as SOURCE_VERSION, SEED as SOURCE_SEED

LABELS = [1, 2, 3, 4]
CATEGORICAL = ["target_kalori", "prioritas"]
CONTINUOUS = ["kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g"]
BINARY = ["status_alergi"] + [f"alergen_{i}" for i in range(1, 12)]
MODEL_CONFIG = {
    "Dummy": {"strategy": "most_frequent"},
    "Decision Tree": {"max_depth": 5, "min_samples_leaf": 5, "random_state": 42, "class_weight": None},
    "Random Forest": {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5, "random_state": 42, "n_jobs": 2, "class_weight": None},
    "KNN": {"n_neighbors": 5, "weights": "uniform", "metric": "minkowski", "p": 2},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Header missing/duplicate: {path}")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError(f"Malformed row in {path}")
        return reader.fieldnames, rows


def validate_split(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "exploratory_features_and_holdout_created":
        raise ValueError("Input manifest is not an exploratory feature/split artifact")
    if manifest.get("ready_for_training") is not False or manifest.get("ready_for_PD11_R2_evaluation") is not False:
        raise ValueError("Source readiness flags must remain false")
    if manifest.get("source_run_training_flag") is not False or manifest.get("source_run_id") != "pd11-r2-cleanup-003":
        raise ValueError("Exploratory run must explicitly reference cleanup-003 and preserve its false readiness flag")
    if manifest.get("seed") != SOURCE_SEED:
        raise ValueError("Unexpected fixed split seed")
    input_dir = folder
    for name, expected in manifest.get("output_sha256", {}).items():
        if sha(input_dir / name) != expected:
            raise ValueError(f"Input artifact hash mismatch: {name}")
    schema = json.loads((folder / "feature_schema.json").read_text(encoding="utf-8"))
    if schema.get("fitur_diizinkan") != FEATURES:
        raise ValueError("Feature allowlist order differs from expected schema")
    expected_feature_cols = set(FEATURES + ["y"])
    _, train = read_csv(folder / "train.csv")
    _, test = read_csv(folder / "test.csv")
    train_headers, _ = read_csv(folder / "train.csv")
    test_headers, _ = read_csv(folder / "test.csv")
    if train_headers != test_headers or not expected_feature_cols.issubset(train_headers):
        raise ValueError("Train/test feature columns mismatch")
    forbidden_metadata = {"response_id", "submission_uid", "evaluation_group_id", "source_row", "timestamp", "rating_asli", "penanda_kiriman", "penanda_penilaian", "status_eksploratif", "alasan_tinjau_eksploratif"}
    if forbidden_metadata & set(FEATURES):
        raise ValueError("Metadata or audit fields are declared as model features")
    for row in train + test:
        if int(row["y"]) not in LABELS or row["rating_asli"].split(" = ", 1)[0] != row["y"]:
            raise ValueError("Target label differs from original rating")
        if row["status_eksploratif"] != "perlu_tinjau":
            raise ValueError("Exploratory review marker was lost")
    split_report = json.loads((folder / "split_report.json").read_text(encoding="utf-8"))
    train_uids = {r["submission_uid"] for r in train}
    test_uids = {r["submission_uid"] for r in test}
    train_groups = {r["evaluation_group_id"] for r in train}
    test_groups = {r["evaluation_group_id"] for r in test}
    if train_uids & test_uids or train_groups & test_groups:
        raise ValueError("UID/group leakage across fixed split")
    if len(train) != manifest["jumlah_train"] or len(test) != manifest["jumlah_test"]:
        raise ValueError("Manifest row counts do not match input split")
    if len(train) != 828 or len(test) != 222:
        raise ValueError("Expected supplied fixed split to contain 828 train and 222 test rows")
    if split_report["train"]["jumlah_kelompok"] != 43 or split_report["test"]["jumlah_kelompok"] != 11:
        raise ValueError("Supplied fixed split group counts do not match expected values")
    return manifest, schema, train, test, split_report


def make_pipeline(name):
    categorical_indices = [FEATURES.index(c) for c in CATEGORICAL]
    numeric_indices = [FEATURES.index(c) for c in CONTINUOUS]
    binary_indices = [FEATURES.index(c) for c in BINARY]
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])
    continuous_steps = [("imputer", SimpleImputer(strategy="median"))]
    if name == "KNN":
        continuous_steps.append(("scaler", StandardScaler()))
    continuous = Pipeline(continuous_steps)
    binary = Pipeline([("imputer", SimpleImputer(strategy="most_frequent"))])
    preprocessor = ColumnTransformer([
        ("categorical", categorical, categorical_indices),
        ("continuous", continuous, numeric_indices),
        ("binary", binary, binary_indices),
    ])
    if name == "Dummy":
        model = DummyClassifier(**MODEL_CONFIG[name])
    elif name == "Decision Tree":
        model = DecisionTreeClassifier(**MODEL_CONFIG[name])
    elif name == "Random Forest":
        model = RandomForestClassifier(**MODEL_CONFIG[name])
    elif name == "KNN":
        model = KNeighborsClassifier(**MODEL_CONFIG[name])
    else:
        raise ValueError(f"Unknown model: {name}")
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def xy(rows):
    X = np.asarray([
        [row[feature] if feature in CATEGORICAL else (1 if row[feature] == "True" else 0 if row[feature] == "False" else float(row[feature])) for feature in FEATURES]
        for row in rows
    ], dtype=object)
    y = np.asarray([int(row["y"]) for row in rows], dtype=int)
    return X, y


def class_probabilities(pipeline, X):
    probabilities = pipeline.predict_proba(X)
    classes = pipeline.named_steps["model"].classes_
    aligned = np.zeros((len(X), len(LABELS)), dtype=float)
    for col, label in enumerate(LABELS):
        if label in classes:
            aligned[:, col] = probabilities[:, list(classes).index(label)]
    return aligned


def evaluate(y_true, y_pred):
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1_four_fixed_labels": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "macro_f1_present_test_classes_only": float(f1_score(y_true, y_pred, labels=sorted(set(y_true)), average="macro", zero_division=0)),
        "mae_rating": float(mean_absolute_error(y_true, y_pred)),
        "per_class": {str(label): {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]), "support": int(support[i]), "recall_measurable": bool(support[i]), "precision_measurable": bool(np.sum(y_pred == label))} for i, label in enumerate(LABELS)},
        "confusion_matrix_labels_1_to_4": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
        "prediction_counts": {str(label): int(np.sum(y_pred == label)) for label in LABELS},
        "test_counts": {str(label): int(np.sum(y_true == label)) for label in LABELS},
        "zero_division": 0,
    }


def verify_loaded_pipeline(model, X_test, original_predictions):
    with tempfile.TemporaryDirectory(prefix="nutrirec-model-check-") as temp_dir:
        path = Path(temp_dir) / "candidate.joblib"
        joblib.dump(model, path)
        loaded = joblib.load(path)
        loaded_predictions = loaded.predict(X_test)
        loaded_probabilities = class_probabilities(loaded, X_test)
        if not np.array_equal(original_predictions, loaded_predictions):
            raise ValueError("Reloaded pipeline predictions differ")
        if not np.allclose(class_probabilities(model, X_test), loaded_probabilities):
            raise ValueError("Reloaded pipeline class probabilities differ")
        return sha(path)


def train_and_evaluate(split_dir, output_dir, dry_run=False):
    input_manifest, schema, train_rows, test_rows, split_report = validate_split(split_dir)
    X_train, y_train = xy(train_rows)
    X_test, y_test = xy(test_rows)
    output = Path(output_dir)
    if output.exists():
        raise ValueError(f"Output directory already exists: {output}")
    if dry_run:
        return input_manifest, train_rows, test_rows, split_report
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ml-train-stage-", dir=output.parent))
    try:
        predictions, metrics, models, comparisons = [], {}, {}, {}
        for name in MODEL_CONFIG:
            model = make_pipeline(name)
            model.fit(X_train, y_train)
            pred = model.predict(X_test).astype(int)
            probs = class_probabilities(model, X_test)
            metrics[name] = evaluate(y_test, pred)
            model_hash = verify_loaded_pipeline(model, X_test, pred)
            model_file = f"{name.lower().replace(' ', '-')}-exploratory.joblib"
            joblib.dump(model, stage / model_file)
            models[name] = {"file": model_file, "sha256": sha(stage / model_file), "roundtrip_temp_sha256": model_hash, "label": "exploratory candidate; not for runtime deployment"}
            comparisons[name] = {
                "accuracy_vs_dummy": metrics[name]["accuracy"] - metrics["Dummy"]["accuracy"] if "Dummy" in metrics else None,
                "macro_f1_vs_dummy": metrics[name]["macro_f1_four_fixed_labels"] - metrics["Dummy"]["macro_f1_four_fixed_labels"] if "Dummy" in metrics else None,
                "mae_vs_dummy": metrics["Dummy"]["mae_rating"] - metrics[name]["mae_rating"] if "Dummy" in metrics else None,
            }
            for index, row in enumerate(test_rows):
                entry = {k: row[k] for k in ("response_id", "submission_uid", "evaluation_group_id", "nama_makanan_survei", "nama_makanan_dataset", "no_makanan_excel", "rating_asli", "penanda_kiriman", "penanda_penilaian", "status_eksploratif", "alasan_tinjau_eksploratif", "status_pemetaan", "status_alergen_katalog", "definisi_prioritas")}
                entry.update(model=name, y_true=int(y_test[index]), y_pred=int(pred[index]))
                entry.update({f"prob_{label}": float(probs[index, label - 1]) for label in LABELS})
                predictions.append(entry)
        comparison = {
            name: {"accuracy_better_than_dummy": values["accuracy_vs_dummy"] > 0,
                   "macro_f1_better_than_dummy": values["macro_f1_vs_dummy"] > 0,
                   "mae_better_than_dummy": values["mae_vs_dummy"] > 0}
            for name, values in comparisons.items() if name != "Dummy"
        }
        report = {
            "title": "Exploratory ML evaluation on fixed grouped holdout",
            "warning": "Not final training approval, production validation, independent confirmation, or PD11-R2 evaluation.",
            "split_source": str(Path(split_dir).resolve()), "source_run": input_manifest["source_run_id"],
            "fit_scope": "Every imputer, encoder and scaler is fitted only through each pipeline on train.csv; test.csv is transform-only.",
            "test_group_counts": split_report["test"]["jumlah_kelompok"],
            "test_rows": split_report["test"]["jumlah_baris"],
            "test_missing_rating_classes": split_report["test"]["kelas_rating_tidak_ada"],
            "test_missing_priority_categories": sorted(set(schema["kategori"]["prioritas"]) - set(split_report["test"]["distribusi_prioritas"])),
            "rating_one": "Test has zero support for class 1; its recall cannot be evaluated. zero_division=0 gives a computational convention for undefined class metrics, not measured performance.",
            "fat_priority": "No test rows have prioritas Lemak; this subgroup cannot be evaluated.",
            "balanced_semantics": "Legacy survey Seimbang means no special priority; not the prototype 15/55/30 ratio.",
            "independence": "submission_uid denotes an anonymous submission, not a verified unique person; identical-answer groups are kept together but do not prove same person.",
            "catalog_scope": "Holdout assesses unseen submission/groups for known catalog foods, not unseen foods.",
            "models_better_than_dummy": comparison,
            "selection": "No tuning, model selection, seed search, alpha search, hybrid, or deployment performed.",
        }
        config = {
            "mode": "exploratory_only", "source_split_version": input_manifest["versi"], "source_run_id": input_manifest["source_run_id"],
            "split_seed": input_manifest["seed"], "test_fraction_target": 0.20,
            "feature_order": FEATURES, "target": "y (rating 1-4)", "labels": LABELS,
            "models": MODEL_CONFIG,
            "preprocessing": "Categorical most-frequent imputation + one-hot handle_unknown=ignore; numeric median imputation; KNN StandardScaler; all fitted on train only.",

            "library_versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__, "scipy": scipy.__version__, "joblib": joblib.__version__},
            "zero_division": 0,
        }
        (stage / "experiment_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        (stage / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        (stage / "comparison_vs_dummy.json").write_text(json.dumps(comparisons, indent=2, ensure_ascii=False), encoding="utf-8")
        (stage / "evaluation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        fields = list(predictions[0]) if predictions else []
        with (stage / "test_predictions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(predictions)
        output_hashes = {p.name: sha(p) for p in stage.iterdir() if p.is_file()}
        result_manifest = {
            "status": "completed_exploratory_holdout_evaluation", "production_model": False,
            "source_ready_for_training": input_manifest["source_run_training_flag"],
            "source_split_manifest_sha256": sha(Path(split_dir) / "manifest.json"),
            "source_split": str(Path(split_dir).resolve()), "source_run_id": input_manifest["source_run_id"],
            "input_sha256": {"train": sha(Path(split_dir) / "train.csv"), "test": sha(Path(split_dir) / "test.csv"), "schema": sha(Path(split_dir) / "feature_schema.json")},
            "models": models, "output_sha256": output_hashes,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        (stage / "manifest.json").write_text(json.dumps(result_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if output.exists():
            raise ValueError("Output directory already exists")
        os.rename(stage, output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return metrics, comparisons, output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            manifest, schema, train, test, split_report = validate_split(args.split_dir)
            print(f"DRY RUN exploratory-only: train={len(train)} test={len(test)} seed={manifest['seed']}")
            return 0
        metrics, comparisons, output = train_and_evaluate(args.split_dir, args.output_dir)
        print(f"Eksperimen eksploratif selesai: {output}")
        for name, result in metrics.items():
            print(name, json.dumps({k: result[k] for k in ("accuracy", "macro_f1_four_fixed_labels", "mae_rating")}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
