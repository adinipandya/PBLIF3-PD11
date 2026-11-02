"""Versikan snapshot survei secara offline; UID adalah identitas kiriman, bukan orang."""
import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

ATURAN = "identitas-v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def teks(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return " ".join(str(value).split())


def baca_sumber(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Form Responses 1" not in wb.sheetnames:
            raise ValueError("Sheet Form Responses 1 tidak ditemukan")
        it = iter(wb["Form Responses 1"].values)
        headers = next(it, None)
        if not headers:
            raise ValueError("Header tidak tersedia")
        canonical = [" ".join(str(h or "").split()).casefold() for h in headers]
        if "timestamp" not in canonical or "" in canonical or len(canonical) != len(set(canonical)):
            raise ValueError("Header kosong, duplikat, atau Timestamp tidak tersedia")
        # ID sumber tidak tersedia pada instrumen ini; jangan diam-diam abaikan ID baru.
        if any(h in {"submission id", "response id", "response_id", "id tanggapan"} for h in canonical):
            raise ValueError("ID sumber terdeteksi: perlu implementasi pemetaan namespace ID sumber")
        result = []
        for n, values in enumerate(it, 2):
            if not any(v is not None and teks(v) for v in values):
                continue
            answers = {k: teks(v) for k, v in zip(canonical, values) if k != "timestamp"}
            timestamp = teks(values[canonical.index("timestamp")])
            if not timestamp:
                raise ValueError(f"Timestamp kosong pada baris {n}")
            fingerprint = sha(json.dumps(answers, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
            result.append({"response_id": f"R{n-1:03d}", "source_row": n,
                           "timestamp": timestamp, "fingerprint": fingerprint})
        return result
    finally:
        wb.close()


def rencanakan(rows, registry, namespace, form, mode, previous=None, decisions=None):
    entries = [e for e in registry.get("submissions", []) if e["source_namespace"] == namespace and e["form_version"] == form]
    if previous and (previous["source_namespace"] != namespace or previous["form_version"] != form):
        raise ValueError("Versi formulir atau namespace berbeda; pemetaan semantik belum tersedia")
    if mode == "incremental" and previous is None:
        raise ValueError("Incremental memerlukan --previous-version")
    decisions = decisions or {}
    known = {e["submission_uid"]: e for e in entries}
    by_key = defaultdict(list)
    by_time = defaultdict(list)
    for e in entries:
        by_key[(e["timestamp"], e["fingerprint"])].append(e["submission_uid"])
        by_time[e["timestamp"]].append(e["submission_uid"])
    counts = Counter((r["timestamp"], r["fingerprint"]) for r in rows)
    time_counts = Counter(r["timestamp"] for r in rows)
    assigned = set()
    output, review, new_entries = [], [], []
    stats = Counter()
    for r in rows:
        key = (r["timestamp"], r["fingerprint"])
        matches = list(dict.fromkeys(by_key[key]))
        same_time = list(dict.fromkeys(by_time[r["timestamp"]]))
        decision = decisions.get(str(r["source_row"]))
        status, uid = None, None
        if decision:
            if not isinstance(decision, dict) or not str(decision.get("alasan", "")).strip():
                raise ValueError(f"Keputusan baris {r['source_row']} wajib memiliki alasan")
            uid = decision.get("submission_uid")
            if uid == "baru":
                uid, status = str(uuid.uuid4()), "baru_manual"
            elif uid in known and uid in same_time:
                status = "cocok_manual"
            else:
                raise ValueError(f"Keputusan baris {r['source_row']} memakai UID tidak dikenal atau timestamp berbeda")
        elif counts[key] > 1 or len(matches) > 1 or time_counts[r["timestamp"]] > 1:
            status = "ambigu"
        elif len(matches) == 1:
            uid, status = matches[0], "cocok"
        elif same_time:
            status = "kemungkinan_berubah"
        else:
            uid, status = str(uuid.uuid4()), "baru"
        if uid and uid in assigned:
            raise ValueError(f"UID digunakan lebih dari sekali: {uid}")
        if uid:
            assigned.add(uid)
        if status in {"ambigu", "kemungkinan_berubah"}:
            review.append({**r, "status": status, "kandidat_uid": same_time})
        elif status in {"baru", "baru_manual"} or (status == "cocok_manual" and uid not in matches):
            new_entries.append({"submission_uid": uid, "source_namespace": namespace, "form_version": form,
                                "timestamp": r["timestamp"], "fingerprint": r["fingerprint"]})
        stats[status] += 1
        output.append({**r, "submission_uid": uid or "", "status": status,
                       "keputusan_manual": json.dumps(decision, ensure_ascii=False, sort_keys=True) if decision else ""})
    used_rows = {str(r["source_row"]) for r in rows}
    if set(decisions) - used_rows:
        raise ValueError("Keputusan memuat source_row yang tidak ada pada sumber")
    if previous:
        old = set(previous["submission_uids"])
        stats["tidak_muncul"] = len(old - assigned) if mode == "snapshot" else 0
    for key in ("cocok", "baru", "kemungkinan_berubah", "ambigu", "tidak_muncul", "cocok_manual", "baru_manual"):
        stats.setdefault(key, 0)
    return output, review, new_entries, dict(stats)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("file", "dataset-version", "form-version", "source-namespace", "versions-root", "registry"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--mode", choices=("snapshot", "incremental"), required=True)
    p.add_argument("--previous-version")
    p.add_argument("--decisions", help="JSON: source_row -> {submission_uid: UID atau 'baru', alasan: teks}")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", a.dataset_version) or a.dataset_version in {".", ".."}:
            raise ValueError("dataset-version tidak valid")
        if not a.form_version.strip() or not a.source_namespace.strip():
            raise ValueError("form-version dan namespace wajib diisi")
        root, registry_path = Path(a.versions_root), Path(a.registry)
        target = root / a.dataset_version
        source_data = Path(a.file).read_bytes()
        registry_bytes = registry_path.read_bytes() if registry_path.exists() else None
        registry = json.loads(registry_bytes) if registry_bytes is not None else {"submissions": [], "versions": {}}
        versions = registry["versions"]
        config = {"source_sha256": sha(source_data), "form_version": a.form_version,
                  "source_namespace": a.source_namespace, "mode": a.mode,
                  "previous_version": a.previous_version, "identity_rules": ATURAN,
                  "decisions_sha256": sha(Path(a.decisions).read_bytes()) if a.decisions else None}
        if target.exists() or a.dataset_version in versions:
            if target.exists() and a.dataset_version in versions and versions[a.dataset_version]["config"] == config:
                print("Versi sudah ada dengan konfigurasi sama; tidak ada perubahan.")
                return 0
            raise ValueError("Dataset version sudah ada atau publikasi sebelumnya belum direkonsiliasi")
        previous = versions.get(a.previous_version) if a.previous_version else None
        if a.previous_version and previous is None:
            raise ValueError("Versi sebelumnya tidak ditemukan dalam registry")
        if previous and previous["config"]["identity_rules"] != ATURAN:
            raise ValueError("Versi aturan identitas berbeda; perlu migrasi eksplisit")
        rows = baca_sumber(a.file)
        decisions = json.loads(Path(a.decisions).read_text()) if a.decisions else {}
        if not isinstance(decisions, dict):
            raise ValueError("Keputusan harus berupa objek JSON")
        mapping, review, new, stats = rencanakan(rows, registry, a.source_namespace, a.form_version, a.mode, previous, decisions)
        print(f"Kiriman: {len(rows)}; hasil: {stats}; review: {len(review)}")
        if review:
            print(json.dumps({"review": review}, ensure_ascii=False, indent=2))
            return 2
        if a.dry_run:
            print("DRY RUN: tidak menulis berkas atau registry")
            return 0
        # Staging berada di filesystem yang sama. Registry diperbarui setelah rename versi.
        root.mkdir(parents=True, exist_ok=True)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        lock = (registry_path.parent / (registry_path.name + ".lock")).open("a+")
        fcntl.flock(lock, fcntl.LOCK_EX)
        stage = None
        try:
            current_registry = registry_path.read_bytes() if registry_path.exists() else None
            if current_registry != registry_bytes:
                raise ValueError("Registry berubah selama proses; jalankan ulang")
            stage = Path(tempfile.mkdtemp(prefix=".survey-stage-", dir=root))
            (stage / "source.xlsx").write_bytes(source_data)
            fields = ["response_id", "source_row", "submission_uid", "timestamp", "fingerprint", "status", "keputusan_manual", "source_namespace", "form_version", "dataset_version"]
            with (stage / "submission_identity_map.csv").open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
                for item in mapping:
                    writer.writerow({**item, "source_namespace": a.source_namespace, "form_version": a.form_version, "dataset_version": a.dataset_version})
            current = {r["submission_uid"] for r in mapping}
            if a.mode == "incremental":
                current |= set(previous["submission_uids"])
            info = {"source_namespace": a.source_namespace, "form_version": a.form_version,
                    "submission_uids": sorted(current), "config": config}
            fingerprints = defaultdict(list)
            for item in mapping:
                fingerprints[item["fingerprint"]].append(item["response_id"])
            duplicates = [group for group in fingerprints.values() if len(group) > 1]
            (stage / "ingestion_report.json").write_text(json.dumps({"counts": stats, "review": review, "previous_version": a.previous_version, "kemungkinan_duplikat_jawaban": duplicates}, ensure_ascii=False, indent=2))
            hashes = {f.name: sha(f.read_bytes()) for f in stage.iterdir() if f.is_file()}
            manifest = {"dataset_version": a.dataset_version, **config, "jumlah": stats, "status": "selesai", "output_sha256": hashes,
                        "aturan_persiapan": "tidak dijalankan", "aturan_seleksi": "tidak dijalankan",
                        "catatan": "UID mengidentifikasi kiriman, bukan orang; timestamp bukan fitur ML."}
            (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            # Atomic create via rename; never replace an existing version.
            if target.exists():
                raise ValueError("Dataset version sudah ada")
            os.rename(stage, target)
            registry["submissions"].extend(new)
            versions[a.dataset_version] = info
            with tempfile.NamedTemporaryFile("w", dir=registry_path.parent, delete=False, encoding="utf-8") as f:
                temp_registry = Path(f.name)
                json.dump(registry, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp_registry, registry_path)
        finally:
            if stage is not None and stage.exists():
                shutil.rmtree(stage)
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        print(f"Versi: {target}; registry: {registry_path}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
