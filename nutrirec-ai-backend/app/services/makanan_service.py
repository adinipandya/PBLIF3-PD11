"""Layanan data makanan dan rekomendasi content-based."""

import logging
import math

from sqlalchemy.orm import Session

from app.core.recommendation_rules import (
    CALORIE_CATEGORIES,
    NUTRIENT_PRIORITIES,
    calorie_category,
    balanced_score,
    calorie_score,
    combined_score,
    min_max_scores,
)
from app.models.makanan import Makanan
from app.models.alergen import Alergen
from app.models.referensi import TargetKalori, PrioritasNutrisi
from app.repositories import makanan_repo

VERSI_ATURAN = "PD11-R2"
logger = logging.getLogger(__name__)

KONDISI_TIDAK_KOSONG_MSG = (
    "Belum ada makanan yang lolos penyaringan. "
    "Periksa pilihan atau status verifikasi data makanan."
)

ALASAN_DATA_GIZI_TIDAK_VALID = {
    "kosong": "Data informasi gizi tidak tersedia.",
    "non_numerik": "Nilai gizi harus numerik.",
    "negatif_atau_tidak_finite": "Nilai gizi harus finite dan tidak negatif.",
    "energi_tidak_valid": "Energi makro harus finite dan lebih dari nol.",
}


def get_semua_makanan(db: Session) -> list[Makanan]:
    return makanan_repo.get_all_makanan(db)


def get_makanan_detail(
    db: Session,
    id_makanan: int,
) -> Makanan | None:
    return makanan_repo.get_makanan_by_id(db, id_makanan)


def _baca_nutrisi(makanan):
    """Kembalikan kalori dan proporsi energi valid; None jika tidak valid."""
    gizi = makanan.informasi_gizi

    if gizi is None:
        logger.warning(
            "Makanan %s dikeluarkan: %s",
            makanan.id_makanan,
            ALASAN_DATA_GIZI_TIDAK_VALID["kosong"],
        )
        return None

    try:
        kalori, protein, karbo, lemak = (
            float(gizi.kalori),
            float(gizi.protein),
            float(gizi.karbohidrat),
            float(gizi.lemak),
        )
    except (TypeError, ValueError, OverflowError):
        logger.warning(
            "Makanan %s dikeluarkan: %s",
            makanan.id_makanan,
            ALASAN_DATA_GIZI_TIDAK_VALID["non_numerik"],
        )
        return None

    angka = (kalori, protein, karbo, lemak)

    if not all(math.isfinite(x) and x >= 0 for x in angka):
        logger.warning(
            "Makanan %s dikeluarkan: %s",
            makanan.id_makanan,
            ALASAN_DATA_GIZI_TIDAK_VALID["negatif_atau_tidak_finite"],
        )
        return None

    energi = 4 * protein + 4 * karbo + 9 * lemak

    if not math.isfinite(energi) or energi <= 0:
        logger.warning(
            "Makanan %s dikeluarkan: %s",
            makanan.id_makanan,
            ALASAN_DATA_GIZI_TIDAK_VALID["energi_tidak_valid"],
        )
        return None

    proporsi = {
        "Protein": 4 * protein / energi,
        "Karbohidrat": 4 * karbo / energi,
        "Lemak": 9 * lemak / energi,
    }
    if not all(math.isfinite(value) for value in proporsi.values()):
        logger.warning(
            "Makanan %s dikeluarkan: proporsi energi non-finite.",
            makanan.id_makanan,
        )
        return None

    return kalori, proporsi



def _lolos_alergi(makanan, alergen_pilihan: set[int]) -> bool:
    kandungan = makanan.kandungan_alergen

    # Model saat ini belum mencatat verifikasi menyeluruh makanan.
    # Daftar relasi kosong tidak boleh dianggap bebas alergen.
    if not kandungan:
        logger.info("Makanan %s dikeluarkan: relasi alergen kosong.", makanan.id_makanan)
        return False

    for item in kandungan:
        if item.id_alergen in alergen_pilihan:
            return False

        if item.status_verifikasi != "Terverifikasi":
            logger.info("Makanan %s dikeluarkan: alergen %s belum diverifikasi.", makanan.id_makanan, item.id_alergen)
            return False

    return True


def hitung_skor_katalog(menu_valid, target_kalori: str, nama_prioritas: str):
    """Score valid catalogue rows using the shared PD11-R2 rule functions."""
    proporsi_prioritas = (
        [item[2][nama_prioritas] for item in menu_valid]
        if nama_prioritas in NUTRIENT_PRIORITIES
        else []
    )
    normalized = min_max_scores(proporsi_prioritas)
    low, high = (min(proporsi_prioritas), max(proporsi_prioritas)) if proporsi_prioritas else (None, None)
    by_id = {
        item[0].id_makanan: score
        for item, score in zip(menu_valid, normalized)
    }
    details = {}
    for food, calories, proportions in menu_valid:
        priority_score = (
            balanced_score(proportions)
            if nama_prioritas == "Seimbang"
            else by_id[food.id_makanan]
        )
        calorie = calorie_score(calories, target_kalori)
        details[food.id_makanan] = {
            "proporsi_energi": proportions,
            "skor_kalori": calorie,
            "skor_prioritas": priority_score,
            "skor_content_based": combined_score(calorie, priority_score),
        }
    return details, low, high

def urutkan_katalog_kandidat(db: Session, permintaan) -> list:
    """Return all valid, allergy-eligible catalogue rows in canonical CB order."""
    target = db.get(TargetKalori, permintaan.target_kalori_id)
    prioritas = db.get(PrioritasNutrisi, permintaan.prioritas_id)

    if target is None:
        raise ValueError("ID target kalori tidak ditemukan.")

    if prioritas is None:
        raise ValueError("ID prioritas nutrisi tidak ditemukan.")

    if not isinstance(permintaan.status_alergi, bool):
        raise ValueError("Status alergi harus dipilih: memiliki atau tidak memiliki alergi.")

    alergen_ids = permintaan.alergen_ids
    if not isinstance(alergen_ids, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in alergen_ids
    ):
        raise ValueError("Daftar alergen harus berisi ID integer positif.")
    if len(set(alergen_ids)) != len(alergen_ids):
        raise ValueError("Setiap alergen hanya boleh dipilih satu kali.")
    pilihan = set(alergen_ids)

    if permintaan.status_alergi and not pilihan:
        raise ValueError("Pilih minimal satu alergen.")

    if not permintaan.status_alergi and pilihan:
        raise ValueError("Tanpa alergi, daftar alergen harus kosong.")

    for id_alergen in pilihan:
        if db.get(Alergen, id_alergen) is None:
            raise ValueError(
                f"ID alergen {id_alergen} tidak ditemukan."
            )

    nama_prioritas = prioritas.nama_prioritas

    if target.nama_kategori not in CALORIE_CATEGORIES:
        raise ValueError("Kategori kalori tidak dikenali.")
    if nama_prioritas not in (*NUTRIENT_PRIORITIES, "Seimbang"):
        raise ValueError("Prioritas nutrisi tidak dikenali.")

    menu_valid = []
    for makanan in get_semua_makanan(db):
        nutrisi = _baca_nutrisi(makanan)
        if nutrisi is not None:
            kalori, proporsi = nutrisi
            menu_valid.append((makanan, kalori, proporsi))

    # Score and normalize over the complete valid catalogue before allergy filtering.
    skor_by_id, _, _ = hitung_skor_katalog(
        menu_valid, target.nama_kategori, nama_prioritas
    )

    hasil = []
    for makanan, _, _ in menu_valid:
        if permintaan.status_alergi and not _lolos_alergi(makanan, pilihan):
            continue
        hasil.append({"makanan": makanan, **skor_by_id[makanan.id_makanan]})

    hasil.sort(
        key=lambda item: (
            -item["skor_content_based"],
            item["makanan"].id_makanan,
        )
    )

    return hasil

def filter_dan_rekomendasikan(db: Session, permintaan) -> list:
    """Filter/score via the shared engine, then return the application Top 3."""
    return urutkan_katalog_kandidat(db, permintaan)[:3]

def demo_terminal():
    """Demo lokal menggunakan snapshot Excel dan database sementara di memori."""
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.base import Base
    from app.models.makanan import InformasiGizi
    from app.models.alergen import KandunganAlergen
    from app.schemas.personalisasi import PermintaanPersonalisasi
    from scripts.import_dataset import baca_dataset, parse_alergen_tercatat

    path = Path(__file__).resolve().parents[3] / "data" / "Dataset_makanan_revisi.xlsx"
    targets = ["Rendah", "Sedang", "Tinggi"]
    priorities = ["Protein", "Karbohidrat", "Lemak", "Seimbang"]
    allergens = ["Telur", "Kedelai", "Jagung", "Kelapa", "Ayam", "Daging sapi", "Gandum", "Kacang-kacangan", "Udang/seafood", "Ikan", "Beras"]

    def pilih(judul, opsi):
        print(f"\n{judul}")
        for i, nama in enumerate(opsi, 1):
            print(f"{i}. {nama}")
        while True:
            jawaban = input("Masukkan nomor: ").strip()
            if jawaban.isdigit() and 1 <= int(jawaban) <= len(opsi):
                return int(jawaban)
            print("Pilihan tidak valid, silakan coba lagi.")

    print("=== DEMO CONTENT-BASED NUTRIREC ===")
    print("Data Excel; tanpa API dan tanpa mengubah database atau file sumber.")
    print("Hasil bukan probabilitas, saran medis, atau jaminan keamanan alergi.")
    try:
        records = baca_dataset(str(path))
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([TargetKalori(id_target=i, nama_kategori=nama) for i, nama in enumerate(targets, 1)])
            db.add_all([PrioritasNutrisi(id_prioritas=i, nama_prioritas=nama, jenis="seimbang" if nama == "Seimbang" else "zat_gizi") for i, nama in enumerate(priorities, 1)])
            db.add_all([Alergen(id_alergen=i, nama_alergen=nama, kata_kunci=nama.lower()) for i, nama in enumerate(allergens, 1)])
            db.flush()
            ids = {nama: i for i, nama in enumerate(allergens, 1)}
            for r in records:
                food = Makanan(id_makanan=int(r["A"]), nama_makanan=r["B"], deskripsi_porsi=r["G"] or "Tidak tersedia", sumber_data=r["N"] or "Tidak tersedia", versi_dataset="demo-excel")
                food.informasi_gizi = InformasiGizi(kalori=r["C"], karbohidrat=r["D"], lemak=r["E"], protein=r["F"])
                status = r["O"] if r["O"] in {"Terverifikasi", "Belum diverifikasi"} else "Belum diverifikasi"
                food.kandungan_alergen = [KandunganAlergen(id_alergen=ids[nama], status_verifikasi=status) for nama in parse_alergen_tercatat(r["M"])]
                db.add(food)
            db.flush()
            target_id = pilih("Pilih target kalori:", targets)
            prioritas_id = pilih("Pilih prioritas nutrisi:", priorities)
            status_id = pilih("Apakah Anda memiliki alergi?", ["Tidak", "Ya"])
            pilihan = []
            if status_id == 2:
                print("\nPilih satu atau lebih alergen, pisahkan nomor dengan koma:")
                for i, nama in enumerate(allergens, 1):
                    print(f"{i}. {nama}")
                while not pilihan:
                    teks = input("Nomor alergen: ").strip().split(",")
                    if all(x.strip().isdigit() and 1 <= int(x.strip()) <= len(allergens) for x in teks):
                        pilihan = list(dict.fromkeys(int(x.strip()) for x in teks))
                    else:
                        print("Pilihan tidak valid, silakan coba lagi.")
            request = PermintaanPersonalisasi(target_kalori_id=target_id, prioritas_id=prioritas_id, status_alergi=status_id == 2, alergen_ids=pilihan)
            hasil = filter_dan_rekomendasikan(db, request)
            print("\n=== HASIL REKOMENDASI ===")
            if not hasil:
                print(KONDISI_TIDAK_KOSONG_MSG)
            for i, item in enumerate(hasil, 1):
                makanan = item["makanan"]
                gizi = makanan.informasi_gizi
                print(f"\n{i}. {makanan.nama_makanan} ({makanan.deskripsi_porsi})")
                print(f"   Kalori: {gizi.kalori} kkal | Protein: {gizi.protein} g | Karbohidrat: {gizi.karbohidrat} g | Lemak: {gizi.lemak} g")
                print(f"   Skor kalori: {item['skor_kalori']:.3f} | Skor prioritas: {item['skor_prioritas']:.3f} | Skor CB: {item['skor_content_based']:.2f}/100")
            print("\nSkor adalah parameter awal prototipe, bukan probabilitas, saran medis, atau jaminan keamanan alergi.")
            print("NO Excel bukan ID database.")
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f"\nDemo berhenti: {exc}")
        return 1
    finally:
        if "engine" in locals():
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(demo_terminal())
