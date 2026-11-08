"""Terminal interaktif untuk rekomendasi PD11-R2 dan hybrid eksploratif."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.demo_content_based import ALERGEN_IDS, run as run_content_based  # noqa: E402
from scripts.demo_ml_exploratory import infer as infer_ml, infer_hybrid  # noqa: E402

DATASET = REPO_DIR / "data" / "Dataset_makanan_revisi.xlsx"
MODEL_DIR = REPO_DIR / "data" / "experiments" / "survey-v001" / "ml-eval-exploratory-001"
MODEL_NAME = "Random Forest"
ALPHA = 0.5
TARGETS = ("Rendah", "Sedang", "Tinggi")
PRIORITIES = ("Protein", "Karbohidrat", "Lemak", "Seimbang")


def _choose(prompt: str, choices: tuple[str, ...]) -> str:
    while True:
        answer = input(f"{prompt} ({'/'.join(choices)}): ").strip()
        if answer in choices:
            return answer
        print(f"Pilihan tidak valid. Masukkan salah satu: {', '.join(choices)}.")


def _allergen_names() -> dict[int, str]:
    return {1: "Telur", 2: "Kedelai", 3: "Jagung", 4: "Kelapa", 5: "Ayam",
            6: "Daging sapi", 7: "Gandum", 8: "Kacang-kacangan",
            9: "Udang/seafood", 10: "Ikan", 11: "Beras"}


def _choose_allergens() -> list[int]:
    names = _allergen_names()
    print("Daftar alergen (ID — nama), dari referensi demo proyek:")
    for identifier, name in sorted(names.items()):
        print(f"  {identifier} — {name}")
    valid_ids = set(names)
    while True:
        raw = input("Masukkan satu atau beberapa ID dipisahkan koma: ").strip()
        try:
            ids = [int(value.strip()) for value in raw.split(",") if value.strip()]
        except ValueError:
            print("Format tidak valid. Gunakan ID numerik dipisahkan koma.")
            continue
        if not ids or any(identifier not in valid_ids for identifier in ids):
            print("Pilih minimal satu ID yang tercantum.")
            continue
        if len(ids) != len(set(ids)):
            print("ID alergen duplikat tidak diperbolehkan.")
            continue
        return ids


def _show_result(result: dict, mode: str) -> None:
    print(f"\nMode: {result.get('mode', mode)} | Status: {result.get('status')}")
    if result.get("catatan_cb"):
        print(f"Catatan: {result['catatan_cb']}")
    recommendations = result.get("rekomendasi", result.get("rekomendasi_demo", []))
    if not recommendations:
        print("Tidak ada makanan yang lolos; filter alergi wajib tidak dilonggarkan.")
        if result.get("alasan_kosong"):
            print(f"Alasan: {result['alasan_kosong']}")
        return
    for index, item in enumerate(recommendations[:3], 1):
        print(f"\n{index}. {item.get('nama_makanan', item.get('nama', 'Tanpa nama'))} (ID {item.get('id_makanan', '?')})")
        print("   Gizi: " + " | ".join(
            f"{label} {item.get(key, '—')} {unit}" for label, key, unit in (
                ("Kalori", "kalori_kkal", "kkal"), ("Protein", "protein_g", "g"),
                ("Karbohidrat", "karbohidrat_g", "g"), ("Lemak", "lemak_g", "g"))))
        if "S_CB" in item:
            print(f"   Skor CB: {item.get('S_CB') if item.get('S_CB') is not None else 'tidak tersedia'}")
            print(f"   Skor ML: {item.get('S_ML', '—')} | Skor hybrid: {item.get('S_hybrid') if item.get('S_hybrid') is not None else 'tidak tersedia'}")
        else:
            print(f"   Skor CB: {item.get('skor_content_based', '—')}")


def _run_once() -> None:
    target = _choose("Target kalori", TARGETS)
    priority = _choose("Prioritas", PRIORITIES)
    has_allergy = _choose("Memiliki alergi?", ("Ya", "Tidak"))
    allergen_ids = _choose_allergens() if has_allergy == "Ya" else []
    mode = _choose("Mode rekomendasi", ("Content-based", "Hybrid eksploratif"))

    if mode == "Hybrid eksploratif" and priority == "Seimbang":
        print("Hybrid belum mendukung Seimbang: label survei legacy berarti tanpa prioritas khusus, "
              "bukan definisi CB 15/55/30.")
        mode = _choose("Pilih Content-based atau ML eksploratif legacy", ("Content-based", "ML eksploratif legacy"))

    allergy = "memiliki" if has_allergy == "Ya" else "tidak"
    if mode == "Content-based":
        result = run_content_based(DATASET, target, priority, allergy, allergen_ids)
    elif mode == "ML eksploratif legacy":
        result = infer_ml(MODEL_DIR, DATASET, MODEL_NAME, target, priority, allergy, allergen_ids)
    else:
        result = infer_hybrid(MODEL_DIR, DATASET, MODEL_NAME, target, priority, allergy, allergen_ids, ALPHA)
    _show_result(result, mode)


def main() -> int:
    print("NutriRec AI — demo rekomendasi offline (hasil eksperimen bukan model produksi).")
    while True:
        try:
            _run_once()
            again = _choose("Coba lagi?", ("Ya", "Tidak"))
            if again == "Tidak":
                return 0
        except (ValueError, OSError, KeyError, TypeError) as exc:
            print(f"Tidak dapat menjalankan rekomendasi: {exc}")
            again = _choose("Coba lagi?", ("Ya", "Tidak"))
            if again == "Tidak":
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nDemo dibatalkan. Tidak ada input atau hasil yang disimpan.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
