"""Eksperimen awal grouped CV offline; bukan pelatihan model produksi."""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_absolute_error, precision_recall_fscore_support
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.prepare_ml_features import FEATURES, METADATA

LABELS = [1, 2, 3, 4]
CONTINUOUS = ["kalori_kkal", "protein_g", "karbohidrat_g", "lemak_g"]
REQUIRED_OUTPUTS = {"evaluation_feasibility_report.json", "ml_feature_table.csv", "experiment_plan.md", "evaluation_groups.csv", "feature_schema.json"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Header duplikat atau kosong: {path}")
        rows = list(reader)
        if any(None in r or None in r.values() for r in rows): raise ValueError(f"Kolom tidak lengkap: {path}")
        return reader.fieldnames, rows


def parse_bool(value):
    if value == "True": return 1
    if value == "False": return 0
    raise ValueError(f"Boolean tidak valid: {value!r}")


def load_source(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("status") != "fitur_eksperimen" or manifest.get("siap_training") is not False: raise ValueError("Status sumber tidak sesuai")
    hashes = manifest.get("output_sha256", {})
    if set(hashes) != REQUIRED_OUTPUTS: raise ValueError("Daftar hash keluaran fitur tidak lengkap")
    for name in REQUIRED_OUTPUTS:
        if sha(folder / name) != hashes[name]: raise ValueError(f"Hash tidak cocok: {name}")
    schema = json.loads((folder / "feature_schema.json").read_text())
    if schema.get("fitur_diizinkan") != FEATURES or set(FEATURES) & (set(METADATA) | {"y"}): raise ValueError("Allowlist fitur tidak aman atau berubah")
    if set(schema.get("metadata_bukan_fitur", [])) != set(METADATA) or set(schema.get("target", {})) != {"y"}: raise ValueError("Skema target/metadata tidak sesuai")
    columns, rows = read_csv(folder / "ml_feature_table.csv")
    if set(columns) != set(FEATURES + ["y"] + METADATA) or len(rows) != manifest.get("jumlah_baris") or not rows: raise ValueError("Kolom atau jumlah baris tidak cocok")
    _, groups = read_csv(folder / "evaluation_groups.csv")
    group_map = {}
    for g in groups:
        uid = g.get("submission_uid", ""); gid = g.get("evaluation_group_id", "")
        if not uid or not gid or uid in group_map: raise ValueError("Pemetaan kelompok kosong atau UID duplikat")
        group_map[uid] = gid
    seen = set()
    for r in rows:
        uid, gid = r["submission_uid"], r["evaluation_group_id"]
        if not uid or group_map.get(uid) != gid or not r["response_id"] or not r["no_makanan_excel"].isdigit() or int(r["no_makanan_excel"]) <= 0: raise ValueError("Identitas atau kelompok tidak valid")
        pair = (uid, int(r["no_makanan_excel"]))
        if pair in seen: raise ValueError("Pasangan UID–makanan duplikat")
        seen.add(pair)
        if any(r[k] != manifest[k] for k in ("dataset_version",)): raise ValueError("Dataset tidak konsisten")
        if r["y"] not in {str(x) for x in LABELS}: raise ValueError("Target tidak valid")
        if r["rating_asli"] != f"{r['y']} = " + {"1": "Sangat tidak sesuai (karena mengandung bahan yang membuat saya alergi)", "2": "Tidak sesuai (agak jauh dari target)", "3": "Sesuai (hampir sesuai target)", "4": "Sangat sesuai (sesuai target)"}[r["y"]]: raise ValueError("Label rating tidak sesuai target")
        for col in ("target_kalori", "prioritas"):
            if r[col] not in schema["kategori"][col]: raise ValueError(f"Kategori tidak dikenal: {col}")
        parse_bool(r["status_alergi"])
        for col in FEATURES[3:14]:
            if r[col] not in {"0", "1"}: raise ValueError(f"Indikator tidak valid: {col}")
        for col in CONTINUOUS:
            value = float(r[col])
            if not math.isfinite(value) or value < 0: raise ValueError(f"Nutrisi tidak valid: {col}")
    if set(group_map) != {r["submission_uid"] for r in rows}: raise ValueError("Kelompok dan tabel fitur tidak cocok")
    rows.sort(key=lambda r: (r["evaluation_group_id"], r["submission_uid"], int(r["no_makanan_excel"])))
    return manifest, schema, rows


def folds_for(rows):
    groups = np.array([r["evaluation_group_id"] for r in rows])
    uids = np.array([r["submission_uid"] for r in rows])
    y = np.array([int(r["y"]) for r in rows])
    splits = list(GroupKFold(n_splits=5).split(np.zeros(len(rows)), y, groups))
    diagnostics = []
    for i, (train, test) in enumerate(splits, 1):
        if set(groups[train]) & set(groups[test]) or set(uids[train]) & set(uids[test]): raise ValueError("Kebocoran kelompok atau UID")
        def stats(indices):
            counts = Counter(y[indices]); return {"baris": len(indices), "uid": len(set(uids[indices])), "kelompok": len(set(groups[indices])), "kelas": {str(k): counts[k] for k in LABELS}, "kelas_tidak_tersedia": [k for k in LABELS if not counts[k]]}
        diagnostics.append({"fold": i, "train": stats(train), "test": stats(test)})
    if len(set(np.concatenate([test for _, test in splits]))) != len(rows): raise ValueError("Partisi OOF tidak lengkap")
    return splits, diagnostics


def pipeline(name, seed):
    categorical = [FEATURES.index(x) for x in ("target_kalori", "prioritas")]
    numeric = [FEATURES.index(x) for x in CONTINUOUS]
    binary = [FEATURES.index(x) for x in FEATURES if x == "status_alergi" or x.startswith("alergen_")]
    pre = ColumnTransformer([("kategori", OneHotEncoder(handle_unknown="ignore"), categorical), ("kontinu", StandardScaler() if name == "KNN" else "passthrough", numeric), ("biner", "passthrough", binary)])
    model = {"Dummy": lambda: DummyClassifier(strategy="most_frequent"), "Decision Tree": lambda: DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=seed, class_weight=None), "Random Forest": lambda: RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=5, random_state=seed, n_jobs=2, class_weight=None), "KNN": lambda: KNeighborsClassifier(n_neighbors=5, weights="uniform", metric="minkowski", p=2)}[name]()
    return Pipeline([("preprocess", pre), ("model", model)])


def probabilities(model, X):
    raw = model.predict_proba(X)
    classes = model.named_steps["model"].classes_
    return np.column_stack([raw[:, list(classes).index(k)] if k in classes else np.zeros(len(X)) for k in LABELS])


def metrics(y, pred, uids):
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=LABELS, zero_division=0)
    individual = []
    for uid in sorted(set(uids)):
        mask = uids == uid
        individual.append((accuracy_score(y[mask], pred[mask]), mean_absolute_error(y[mask], pred[mask])))
    return {"accuracy": float(accuracy_score(y, pred)), "macro_f1": float(f1_score(y, pred, labels=LABELS, average="macro", zero_division=0)), "mae": float(mean_absolute_error(y, pred)), "uid_accuracy_mean": float(np.mean([x[0] for x in individual])), "uid_mae_mean": float(np.mean([x[1] for x in individual])), "per_kelas": {str(k): {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i]), "dapat_dievaluasi": bool(s[i])} for i, k in enumerate(LABELS)}, "confusion_matrix": confusion_matrix(y, pred, labels=LABELS).tolist()}


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", required=True); parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42); parser.add_argument("--dry-run", action="store_true")
    a = parser.parse_args(argv)
    try:
        out = Path(a.output_dir)
        if out.exists(): raise ValueError("Direktori keluaran sudah ada")
        manifest, schema, rows = load_source(a.features_dir)
        splits, diagnostics = folds_for(rows)
        print(f"Baris={len(rows)}; UID={len({r['submission_uid'] for r in rows})}; kelompok={len({r['evaluation_group_id'] for r in rows})}")
        for d in diagnostics: print(f"Fold {d['fold']}: test={d['test']['kelas']}; kelas tidak tersedia={d['test']['kelas_tidak_tersedia']}")
        if a.dry_run:
            print("DRY RUN: tanpa fitting dan tanpa menulis berkas")
            return 0
        X = np.array([[r[c] if c in FEATURES[:2] else parse_bool(r[c]) if c == "status_alergi" else float(r[c]) for c in FEATURES] for r in rows], dtype=object)
        y = np.array([int(r["y"]) for r in rows]); uids = np.array([r["submission_uid"] for r in rows])
        config = {"seed": a.seed, "splitter": "GroupKFold(n_splits=5), urutan baris stabil; seed tidak memengaruhi splitter", "fitur": FEATURES, "label": LABELS, "model": {"Dummy": "most_frequent", "Decision Tree": "max_depth=5,min_samples_leaf=5,class_weight=None", "Random Forest": "n_estimators=200,max_depth=8,min_samples_leaf=5,n_jobs=2,class_weight=None", "KNN": "n_neighbors=5,weights=uniform,metric=minkowski,p=2"}}
        predictions, fold_metrics, summary = [], [], {}
        for name in config["model"]:
            oof = np.zeros(len(rows), dtype=int); per_fold = []
            for fold, (train, test) in enumerate(splits, 1):
                if name == "KNN" and len(train) < 5: raise ValueError("KNN membutuhkan minimal 5 baris train")
                model = pipeline(name, a.seed); model.fit(X[train], y[train]); pred = model.predict(X[test]); prob = probabilities(model, X[test]); oof[test] = pred
                score = metrics(y[test], pred, uids[test]); per_fold.append(score)
                fold_metrics.append({"model": name, "fold": fold, **{k: v for k, v in score.items() if k not in ("per_kelas", "confusion_matrix")}, "per_kelas": json.dumps(score["per_kelas"]), "confusion_matrix": json.dumps(score["confusion_matrix"])})
                for j, idx in enumerate(test):
                    r = rows[idx]
                    predictions.append({"model": name, "fold": fold, **{k: r[k] for k in ("submission_uid", "response_id", "evaluation_group_id", "no_makanan_excel")}, "y_true": int(y[idx]), "y_pred": int(pred[j]), **{f"prob_{k}": float(prob[j, k-1]) for k in LABELS}, "kelas_tidak_ada_train": ";".join(map(str, diagnostics[fold-1]["train"]["kelas_tidak_tersedia"]))})
            summary[name] = {"oof": metrics(y, oof, uids), "fold_deskriptif": {key: {"mean": float(np.mean([x[key] for x in per_fold])), "std": float(np.std([x[key] for x in per_fold]))} for key in ("accuracy", "macro_f1", "mae", "uid_accuracy_mean", "uid_mae_mean")}}
        out.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".experiment-", dir=out.parent))
        try:
            (stage / "experiment_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False))
            (stage / "fold_diagnostics.json").write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False))
            assignments = [{"fold": i, **{k: rows[idx][k] for k in ("submission_uid", "response_id", "evaluation_group_id", "no_makanan_excel")}} for i, (_, test) in enumerate(splits, 1) for idx in test]
            write_csv(stage / "fold_assignments.csv", assignments, list(assignments[0]))
            write_csv(stage / "out_of_fold_predictions.csv", predictions, list(predictions[0]))
            write_csv(stage / "metrics_by_fold.csv", fold_metrics, list(fold_metrics[0]))
            (stage / "metrics_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
            report = "# Eksperimen awal\n\nGrouped 5-fold pada kiriman baru untuk katalog dikenal; bukan validasi produksi. Macro-F1 menggunakan seluruh empat label dan zero_division=0; kelas tanpa support tidak dapat dievaluasi pada fold itu. Rata-rata/std fold hanya deskriptif. Probabilitas belum terkalibrasi. Hasil tidak menjamin keamanan alergi; filter backend tetap terpisah. Rating 1 dan prioritas Lemak terlalu langka untuk klaim generalisasi. Tidak ada tuning, split final, ranking Top 3, atau model final.\n"
            (stage / "experiment_report.md").write_text(report)
            result = {"eksperimen_awal": True, "siap_produksi": False, "versi_aturan": "groupcv-awal-v1", "dataset_version": manifest["dataset_version"], "run_id": manifest["run_id"], "feature_version": manifest["versi_aturan_fitur"], "seed": a.seed, "python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__, "scipy": scipy.__version__, "config": config, "masukan_sha256": {name: sha(Path(a.features_dir) / name) for name in sorted(REQUIRED_OUTPUTS | {"manifest.json"})}, "output_sha256": {p.name: sha(p) for p in stage.iterdir()}}
            (stage / "manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
            if out.exists(): raise ValueError("Direktori keluaran sudah ada")
            os.rename(stage, out)
        finally:
            if stage.exists(): shutil.rmtree(stage)
        print(f"Hasil: {out}"); return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
