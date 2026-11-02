"""Analisis deskriptif kesalahan prediksi OOF; tidak melatih model."""
import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Header kosong atau duplikat: {path}")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError(f"Kolom tidak lengkap: {path}")
        return rows


def load(experiment, features):
    experiment, features = Path(experiment), Path(features)
    em = json.loads((experiment / "manifest.json").read_text())
    fm = json.loads((features / "manifest.json").read_text())
    if em.get("eksperimen_awal") is not True or em.get("siap_produksi") is not False:
        raise ValueError("Status eksperimen tidak valid")
    if em.get("dataset_version") != fm.get("dataset_version") or em.get("run_id") != fm.get("run_id") or em.get("feature_version") != fm.get("versi_aturan_fitur"):
        raise ValueError("Metadata eksperimen dan fitur tidak cocok")
    for name in em.get("output_sha256", {}):
        if em.get("output_sha256", {}).get(name) != digest(experiment / name):
            raise ValueError(f"Hash eksperimen tidak cocok: {name}")
    for name in em.get("masukan_sha256", {}):
        if em.get("masukan_sha256", {}).get(name) != digest(features / name):
            raise ValueError(f"Hash masukan fitur tidak cocok: {name}")
        if name != "manifest.json" and fm.get("output_sha256", {}).get(name) != digest(features / name):
            raise ValueError(f"Hash manifest fitur tidak cocok: {name}")
    for name, expected in fm.get("output_sha256", {}).items():
        if digest(features / name) != expected:
            raise ValueError(f"Hash fitur tidak cocok: {name}")
    records = read_csv(features / "ml_feature_table.csv")
    predictions = read_csv(experiment / "out_of_fold_predictions.csv")
    assignments = read_csv(experiment / "fold_assignments.csv")
    diagnostics = json.loads((experiment / "fold_diagnostics.json").read_text())
    if len(records) != fm.get("jumlah_baris"):
        raise ValueError("Jumlah baris fitur tidak cocok")
    key = lambda r: (r["submission_uid"], r["no_makanan_excel"])
    index = {}
    for r in records:
        k = key(r)
        if not all(k) or k in index or r["y"] not in {"1", "2", "3", "4"}:
            raise ValueError("Identitas fitur duplikat/kosong atau target tidak valid")
        index[k] = r
    folds = {}
    for r in assignments:
        k = key(r)
        if k not in index or k in folds:
            raise ValueError("Partisi fold tidak cocok atau duplikat")
        base = index[k]
        if any(r[c] != base[c] for c in ("response_id", "evaluation_group_id")):
            raise ValueError("Identitas fold bertentangan")
        folds[k] = r["fold"]
    if set(folds) != set(index): raise ValueError("Partisi fold tidak lengkap")
    group_fold, uid_fold = {}, {}
    for k, fold in folds.items():
        r = index[k]
        for mapping, value in ((group_fold, r["evaluation_group_id"]), (uid_fold, r["submission_uid"])):
            if value in mapping and mapping[value] != fold: raise ValueError("Kelompok atau UID terpecah antar fold")
            mapping[value] = fold
    actual_diagnostics = {}
    for fold in set(folds.values()):
        parts = {}
        for label, selected in (("test", lambda f: f == fold), ("train", lambda f: f != fold)):
            subset = [index[k] for k, f in folds.items() if selected(f)]
            counts = Counter(r["y"] for r in subset)
            parts[label] = {"baris": len(subset), "uid": len({r["submission_uid"] for r in subset}), "kelompok": len({r["evaluation_group_id"] for r in subset}), "kelas": {str(i): counts[str(i)] for i in range(1, 5)}, "kelas_tidak_tersedia": [i for i in range(1, 5) if not counts[str(i)]]}
        actual_diagnostics[fold] = parts
    if {str(d["fold"]): {k: d[k] for k in ("train", "test")} for d in diagnostics} != actual_diagnostics:
        raise ValueError("Distribusi kelas atau diagnostik fold tidak cocok")
    models = set(em["config"]["model"])
    seen, result = set(), []
    for p in predictions:
        k = key(p); model = p["model"]
        if model not in models or k not in index or (model, k) in seen:
            raise ValueError("Prediksi OOF duplikat atau tidak dikenal")
        seen.add((model, k)); r = index[k]
        if p["fold"] != folds[k] or p["y_true"] != r["y"] or p["y_pred"] not in {"1", "2", "3", "4"} or any(p[c] != r[c] for c in ("response_id", "evaluation_group_id")):
            raise ValueError("Prediksi OOF tidak cocok dengan fitur/fold")
        missing = ";".join(map(str, actual_diagnostics[p["fold"]]["train"]["kelas_tidak_tersedia"]))
        if p["kelas_tidak_ada_train"] != missing:
            raise ValueError("Kelas tidak ada pada train tidak cocok dengan fold")
        probs = [float(p[f"prob_{i}"]) for i in range(1, 5)]
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in probs) or not math.isclose(sum(probs), 1, abs_tol=1e-6):
            raise ValueError("Probabilitas OOF tidak valid")
        result.append({**p, **{c: r[c] for c in ("target_kalori", "prioritas", "status_alergi", "nama_makanan_survei", "nama_makanan_dataset", "rating_asli")}, "selisih": int(p["y_pred"]) - int(p["y_true"]), "error_absolut": abs(int(p["y_pred"]) - int(p["y_true"]))})
    if len(seen) != len(index) * len(models): raise ValueError("Prediksi OOF tidak lengkap untuk semua model")
    saved = json.loads((experiment / "metrics_summary.json").read_text())
    for model in models:
        actual = metrik([r for r in result if r["model"] == model])
        expected = saved[model]["oof"]
        for a, b in (("accuracy", "accuracy"), ("macro_f1", "macro_f1"), ("mae", "mae"), ("uid_accuracy", "uid_accuracy_mean"), ("uid_mae", "uid_mae_mean")):
            if not math.isclose(actual[a], expected[b], rel_tol=0, abs_tol=1e-10):
                raise ValueError(f"Metrik sumber tidak cocok: {model} {a}")
        if actual["matrix"] != expected["confusion_matrix"]:
            raise ValueError(f"Confusion matrix sumber tidak cocok: {model}")
        for label in range(1, 5):
            for field in ("precision", "recall", "f1", "support"):
                if not math.isclose(actual["kelas"][str(label)][field], expected["per_kelas"][str(label)][field], rel_tol=0, abs_tol=1e-10):
                    raise ValueError(f"Metrik kelas sumber tidak cocok: {model} {label} {field}")
    return em, fm, result, diagnostics


def metrik(rows):
    n = len(rows)
    matrix = [[sum(r["y_true"] == str(i) and r["y_pred"] == str(j) for r in rows) for j in range(1, 5)] for i in range(1, 5)]
    kelas, normalized = {}, []
    for i in range(4):
        support = sum(matrix[i]); predicted = sum(row[i] for row in matrix); tp = matrix[i][i]
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        kelas[str(i + 1)] = {"precision": precision, "recall": recall, "f1": f1, "support": support, "dapat_dievaluasi": bool(support)}
        normalized.append([x / support if support else None for x in matrix[i]])
    by_uid = defaultdict(list)
    for r in rows: by_uid[r["submission_uid"]].append(r)
    errors = [abs(int(r["y_pred"]) - int(r["y_true"])) for r in rows]
    return {"penilaian": n, "uid": len(by_uid), "kelompok": len({r["evaluation_group_id"] for r in rows}), "fold": len({r["fold"] for r in rows}),
            "accuracy": sum(e == 0 for e in errors) / n, "mae": sum(errors) / n,
            "macro_f1": sum(k["f1"] for k in kelas.values()) / 4, "kelas": kelas,
            "uid_accuracy": sum(sum(r["y_true"] == r["y_pred"] for r in a) / len(a) for a in by_uid.values()) / len(by_uid),
            "uid_mae": sum(sum(abs(int(r["y_pred"]) - int(r["y_true"])) for r in a) / len(a) for a in by_uid.values()) / len(by_uid),
            "matrix": matrix, "normalisasi": normalized,
            "aktual": {str(i + 1): sum(matrix[i]) for i in range(4)}, "prediksi": {str(i + 1): sum(x[i] for x in matrix) for i in range(4)},
            "benar": sum(e == 0 for e in errors), "salah_satu": sum(e == 1 for e in errors), "salah_dua_atau_lebih": sum(e >= 2 for e in errors),
            "terlalu_tinggi": sum(int(r["y_pred"]) > int(r["y_true"]) for r in rows), "terlalu_rendah": sum(int(r["y_pred"]) < int(r["y_true"]) for r in rows),
            "kelas_tidak_tersedia": [i + 1 for i in range(4) if not sum(matrix[i])], "dukungan_sangat_terbatas": len({r["evaluation_group_id"] for r in rows}) < 5}


def paired(rows, dummy):
    pairs = [(r, dummy[(r["submission_uid"], r["no_makanan_excel"])]) for r in rows]
    values = Counter(); per_uid = defaultdict(list)
    for a, b in pairs:
        ca, cb = a["y_pred"] == a["y_true"], b["y_pred"] == b["y_true"]
        values["keduanya_benar" if ca and cb else "hanya_model_benar" if ca else "hanya_dummy_benar" if cb else "keduanya_salah"] += 1
        per_uid[a["submission_uid"]].append((int(ca) - int(cb), abs(int(a["y_pred"]) - int(a["y_true"])) - abs(int(b["y_pred"]) - int(b["y_true"]))))
    n = len(rows); delta = (values["hanya_model_benar"] - values["hanya_dummy_benar"]) / n
    assert sum(values.values()) == n
    return {**{k: values[k] for k in ("keduanya_benar", "hanya_model_benar", "hanya_dummy_benar", "keduanya_salah")}, "penilaian": n, "uid": len(per_uid), "kelompok": len({r["evaluation_group_id"] for r in rows}), "accuracy_delta": delta, "mae_delta": sum(v[1] for a in per_uid.values() for v in a) / n, "uid_accuracy_delta": sum(sum(v[0] for v in a) / len(a) for a in per_uid.values()) / len(per_uid), "uid_mae_delta": sum(sum(v[1] for v in a) / len(a) for a in per_uid.values()) / len(per_uid), "dukungan_sangat_terbatas": len({r["evaluation_group_id"] for r in rows}) < 5}


def summarize(rows, diagnostics):
    result = {}
    for model in sorted({r["model"] for r in rows}):
        subset = [r for r in rows if r["model"] == model]
        mistakes = [r for r in subset if r["error_absolut"]]
        confusion = {str(i): {str(j): sum(r["y_true"] == str(i) and r["y_pred"] == str(j) for r in subset) for j in range(1, 5)} for i in range(1, 5)}
        subgroups = {}
        for field in ("target_kalori", "prioritas", "status_alergi", "nama_makanan_dataset", "fold"):
            groups = defaultdict(list)
            for row in subset: groups[row[field]].append(row)
            subgroups[field] = {name: {"penilaian": len(items), "uid": len({x["submission_uid"] for x in items}), "kesalahan": sum(x["error_absolut"] > 0 for x in items), "mae": sum(x["error_absolut"] for x in items) / len(items)} for name, items in sorted(groups.items())}
        result[model] = {"penilaian": len(subset), "kesalahan": len(mistakes), "akurasi": 1 - len(mistakes) / len(subset), "mae": sum(r["error_absolut"] for r in subset) / len(subset), "confusion_matrix": confusion, "arah_kesalahan": {"prediksi_lebih_rendah": sum(r["selisih"] < 0 for r in mistakes), "prediksi_lebih_tinggi": sum(r["selisih"] > 0 for r in mistakes)}, "per_profil_dan_makanan": subgroups, "rating_1": {"jumlah": sum(r["y_true"] == "1" for r in subset), "benar": sum(r["y_true"] == "1" and r["y_pred"] == "1" for r in subset), "uid": len({r["submission_uid"] for r in subset if r["y_true"] == "1"})}}
    return {"model": result, "fold_diagnostics": diagnostics, "catatan": ["Analisis deskriptif OOF; bukan evaluasi produksi atau uji signifikansi.", "Subkelompok kecil tidak mendukung klaim generalisasi.", "Probabilitas belum terkalibrasi; tidak mengukur keamanan alergi.", "Fold tanpa kelas pada train tidak dapat memprediksi kelas tersebut.", "Tidak ada pelatihan ulang atau pemilihan model otomatis."]}


def detail(rows):
    models = sorted({r["model"] for r in rows})
    if "Dummy" not in models: raise ValueError("Dummy tidak ditemukan untuk perbandingan")
    baseline = {(r["submission_uid"], r["no_makanan_excel"]): r for r in rows if r["model"] == "Dummy"}
    overall, confusion, subs, comparisons, examples = {}, {}, [], [], {}
    for model in models:
        selected = [r for r in rows if r["model"] == model]
        score = metrik(selected)
        one = [r for r in selected if r["y_true"] == "1"]
        score["rating_1"] = {"penilaian": len(one), "uid": len({r["submission_uid"] for r in one}), "kelompok": len({r["evaluation_group_id"] for r in one}), "fold": sorted({r["fold"] for r in one}), "train_tersedia": {"penilaian": sum("1" not in r["kelas_tidak_ada_train"].split(";") for r in one), "benar": sum("1" not in r["kelas_tidak_ada_train"].split(";") and r["y_pred"] == "1" for r in one)}, "train_tidak_tersedia": {"penilaian": sum("1" in r["kelas_tidak_ada_train"].split(";") for r in one), "benar": sum("1" in r["kelas_tidak_ada_train"].split(";") and r["y_pred"] == "1" for r in one)}}
        overall[model] = score
        confusion[model] = {"label": [1, 2, 3, 4], "jumlah": score["matrix"], "normalisasi_baris": score["normalisasi"]}
        examples[model] = sorted((r for r in selected if r["error_absolut"]), key=lambda r: (-r["error_absolut"], r["submission_uid"], int(r["no_makanan_excel"])))[:10]
        if model != "Dummy": comparisons.append({"model": model, "variabel": "keseluruhan", "nilai": "semua", **paired(selected, baseline)})
        for field in ("target_kalori", "prioritas", "status_alergi", "nama_makanan_dataset"):
            for value in sorted({r[field] for r in selected}):
                part = [r for r in selected if r[field] == value]
                subs.append({"model": model, "variabel": field, "nilai": value, **metrik(part)})
                if model != "Dummy": comparisons.append({"model": model, "variabel": field, "nilai": value, **paired(part, baseline)})
    return overall, confusion, subs, comparisons, examples


def markdown(overall, comparisons, examples, subgroups):
    names = sorted(overall)
    text = ["# Analisis kesalahan OOF", "", "## A. Teramati", "", f"Sumber experiment-001; {sum(v['penilaian'] for v in overall.values())} prediksi pada {overall[names[0]]['penilaian']} penilaian per model. Tidak ada training ulang.", "", "| Model | N | UID | Kelompok | Accuracy | Macro-F1 | MAE | Benar | Salah 1 | Salah ≥2 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n in names:
        s = overall[n]; text.append(f"| {n} | {s['penilaian']} | {s['uid']} | {s['kelompok']} | {s['accuracy']:.4f} | {s['macro_f1']:.4f} | {s['mae']:.4f} | {s['benar']} | {s['salah_satu']} | {s['salah_dua_atau_lebih']} |")
    text += ["", "### F1 dan support per kelas", "", "| Model | Kelas | F1 | Support |", "|---|---:|---:|---:|"]
    for n in names:
        for label, value in overall[n]["kelas"].items(): text.append(f"| {n} | {label} | {value['f1']:.4f} | {value['support']} |")
    text += ["", "Macro-F1 memakai empat label dan zero_division=0; kelas dengan support nol tidak dapat dievaluasi. Normalisasi baris dengan support nol adalah null.", "", "### Confusion matrix: baris aktual, kolom prediksi (1–4)"]
    for n in names:
        text += ["", f"**{n}**", "", "| Aktual | 1 | 2 | 3 | 4 |", "|---|---:|---:|---:|---:|"]
        for i, row in enumerate(overall[n]["matrix"], 1): text.append(f"| {i} | " + " | ".join(map(str, row)) + " |")
    text += ["", "### Perbandingan berpasangan terhadap Dummy", "", "| Model | Keduanya benar | Hanya model | Hanya Dummy | Keduanya salah | Δ accuracy | Δ MAE |", "|---|---:|---:|---:|---:|---:|---:|"]
    for p in comparisons:
        if p["variabel"] == "keseluruhan": text.append(f"| {p['model']} | {p['keduanya_benar']} | {p['hanya_model_benar']} | {p['hanya_dummy_benar']} | {p['keduanya_salah']} | {p['accuracy_delta']:.4f} | {p['mae_delta']:.4f} |")
    text += ["", "### Subkelompok: selisih accuracy terbesar terhadap Dummy", "", "| Model | Variabel | Nilai | Penilaian | UID | Kelompok | Δ accuracy | Dukungan terbatas |", "|---|---|---|---:|---:|---:|---:|---|"]
    ranked = sorted((p for p in comparisons if p["variabel"] != "keseluruhan"), key=lambda p: (-abs(p["accuracy_delta"]), p["model"], p["variabel"], p["nilai"]))[:10]
    for p in ranked: text.append(f"| {p['model']} | {p['variabel']} | {p['nilai']} | {p['penilaian']} | {p['uid']} | {p['kelompok']} | {p['accuracy_delta']:.4f} | {p['dukungan_sangat_terbatas']} |")
    text += ["", "Kurang dari 5 kelompok ditandai dukungan sangat terbatas; ambang ini deskriptif, bukan jaminan kecukupan statistik.", "", "### Rating 1 dan contoh kesalahan besar", "", "Contoh maksimal 10 per model, diurutkan error absolut menurun, UID lalu NO makanan numerik."]
    for n in names:
        one = overall[n]["rating_1"]; text += ["", f"**{n}:** {one['penilaian']} penilaian, {one['uid']} UID, {one['kelompok']} kelompok, fold {one['fold']}; train tidak memiliki kelas 1: {one['train_tidak_tersedia']['penilaian']}, benar {one['train_tidak_tersedia']['benar']}."]
        for r in examples[n]: text.append(f"- {r['response_id']} / NO {r['no_makanan_excel']}: aktual {r['y_true']}, prediksi {r['y_pred']}, error {r['error_absolut']}.")
    lemak = next((s for s in subgroups if s["variabel"] == "prioritas" and s["nilai"] == "Lemak"), None)
    lemak_text = f"Prioritas Lemak memiliki {lemak['uid']} kiriman dan {lemak['kelompok']} kelompok." if lemak else "Prioritas Lemak tidak ditemukan pada data kandidat."
    text += ["", "## B. Perlu diuji", "", "Perbedaan subkelompok adalah hipotesis, bukan bukti penyebab atau kesalahan responden. Rating 1 yang hanya diuji ketika train tidak memiliki kelas itu tidak membuktikan kemampuan umum model.", "", "## C. Saran berikutnya", "", "1. Kumpulkan lebih banyak kiriman independen untuk kelas langka dan prioritas Lemak.", "2. Tinjau definisi target dan kualitas jawaban tanpa mengganti rating.", "3. Rancang evaluasi kelompok independen sebelum eksperimen konfirmasi.", "", f"Hasil berlaku untuk kiriman baru pada katalog makanan dikenal; bukan keamanan alergi. {lemak_text} Perubahan berdasarkan OOF menjadikan eksperimen berikutnya adaptif/eksploratif, bukan konfirmasi independen. Tidak ada pemilihan model produksi atau uji signifikansi. Probabilitas belum terkalibrasi."]
    return "\n".join(text) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment-dir", required=True)
    p.add_argument("--features-dir", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    try:
        output = Path(args.output_dir)
        if output.exists(): raise ValueError("Direktori keluaran sudah ada; tidak ditimpa")
        em, fm, rows, diagnostics = load(args.experiment_dir, args.features_dir)
        report = summarize(rows, diagnostics)
        overall, confusion, subgroups, comparisons, examples = detail(rows)
        print(f"Prediksi OOF: {len(rows)}; model: {len(report['model'])}; baris fitur: {fm['jumlah_baris']}")
        for name, scores in report["model"].items():
            print(f"{name}: salah={scores['kesalahan']}, MAE={scores['mae']:.4f}, rating 1 benar={scores['rating_1']['benar']}/{scores['rating_1']['jumlah']}")
        if args.dry_run:
            print("DRY RUN: tidak menulis berkas")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".error-analysis-", dir=output.parent))
        try:
            errors = [r for r in rows if r["error_absolut"]]
            fields = list(rows[0])
            with (stage / "oof_errors.csv").open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(errors)
            (stage / "error_analysis_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            (stage / "overall_metrics.json").write_text(json.dumps(overall, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            (stage / "confusion_matrices.json").write_text(json.dumps(confusion, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            def csv_output(name, data):
                with (stage / name).open("w", encoding="utf-8-sig", newline="") as f:
                    fields = list(data[0]) if data else ["model"]
                    writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
                    for row in data:
                        writer.writerow({k: json.dumps(v, ensure_ascii=False, allow_nan=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
            csv_output("subgroup_metrics.csv", subgroups)
            csv_output("paired_vs_dummy.csv", comparisons)
            all_predictions = [{**r, "signed_error": r["selisih"], "absolute_error": r["error_absolut"], "correct": r["error_absolut"] == 0} for r in rows]
            csv_output("prediction_errors.csv", all_predictions)
            (stage / "error_analysis_report.md").write_text(markdown(overall, comparisons, examples, subgroups), encoding="utf-8")
            inputs = {f"experiment/{name}": digest(Path(args.experiment_dir) / name) for name in em["output_sha256"]}
            inputs.update({f"features/{name}": digest(Path(args.features_dir) / name) for name in em["masukan_sha256"]})
            inputs["experiment/manifest.json"] = digest(Path(args.experiment_dir) / "manifest.json")
            manifest = {"status": "analisis_eksploratif", "siap_produksi": False, "versi_aturan": "analisis-oof-v2", "dataset_version": em["dataset_version"], "run_id": em["run_id"], "experiment": Path(args.experiment_dir).name, "masukan_sha256": inputs, "output_sha256": {p.name: digest(p) for p in stage.iterdir()}}
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            if output.exists(): raise ValueError("Direktori keluaran sudah ada")
            os.rename(stage, output)
        finally:
            if stage.exists(): shutil.rmtree(stage)
        print(f"Hasil: {output}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
