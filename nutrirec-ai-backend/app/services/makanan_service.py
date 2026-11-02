"""Layanan data makanan dan rekomendasi content-based."""

import math

from sqlalchemy.orm import Session

from app.models.makanan import Makanan
from app.models.alergen import Alergen
from app.models.referensi import TargetKalori, PrioritasNutrisi
from app.repositories import makanan_repo


VERSI_ATURAN = "PD11-R1"

KONDISI_TIDAK_KOSONG_MSG = (
    "Belum ada makanan yang lolos penyaringan. "
    "Periksa pilihan atau status verifikasi data makanan."
)

# Bobot prototipe yang akan ditinjau ulang setelah validasi dengan pengguna.
BOBOT_KALORI = 0.5
BOBOT_PRIORITAS = 1.0 - BOBOT_KALORI


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
        return None

    try:
        kalori, protein, karbo, lemak = (
            float(gizi.kalori),
            float(gizi.protein),
            float(gizi.karbohidrat),
            float(gizi.lemak),
        )
    except (TypeError, ValueError, OverflowError):
        return None

    angka = (kalori, protein, karbo, lemak)

    if not all(math.isfinite(x) and x >= 0 for x in angka):
        return None

    energi = 4 * protein + 4 * karbo + 9 * lemak

    if energi <= 0:
        return None

    proporsi = {
        "Protein": 4 * protein / energi,
        "Karbohidrat": 4 * karbo / energi,
        "Lemak": 9 * lemak / energi,
    }

    return kalori, proporsi


def _skor_kalori(kalori: float, target: TargetKalori) -> float:
    """Skor kedekatan terhadap rentang kalori yang dipilih (0–1)."""
    if target.kalori_min is None and target.kalori_max is None:
        raise ValueError("Rentang target kalori tidak valid.")

    if target.kalori_min is not None and kalori < target.kalori_min:
        jarak = target.kalori_min - kalori
    elif target.kalori_max is not None and kalori > target.kalori_max:
        jarak = kalori - target.kalori_max
    else:
        return 1.0

    rentang = (
        target.kalori_max - target.kalori_min
        if target.kalori_min is not None and target.kalori_max is not None
        else target.kalori_max or target.kalori_min
    )
    return max(0.0, 1.0 - jarak / float(rentang))


def _lolos_alergi(makanan, alergen_pilihan: set[int]) -> bool:
    kandungan = makanan.kandungan_alergen

    # Model saat ini belum mencatat verifikasi menyeluruh makanan.
    # Daftar relasi kosong tidak boleh dianggap bebas alergen.
    if not kandungan:
        return False

    for item in kandungan:
        if item.id_alergen in alergen_pilihan:
            return False

        if item.status_verifikasi != "Terverifikasi":
            return False

    return True


def filter_dan_rekomendasikan(db: Session, permintaan) -> list:
    target = db.get(TargetKalori, permintaan.target_kalori_id)
    prioritas = db.get(PrioritasNutrisi, permintaan.prioritas_id)

    if target is None:
        raise ValueError("ID target kalori tidak ditemukan.")

    if prioritas is None:
        raise ValueError("ID prioritas nutrisi tidak ditemukan.")

    pilihan = set(permintaan.alergen_ids)

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

    if target.nama_kategori not in {"Rendah", "Sedang", "Tinggi"}:
        raise ValueError("Kategori kalori tidak dikenali.")
    if (
        target.kalori_min is not None
        and target.kalori_max is not None
        and target.kalori_min >= target.kalori_max
    ):
        raise ValueError("Rentang target kalori tidak valid.")
    if target.kalori_min is None and target.kalori_max is None:
        raise ValueError("Rentang target kalori tidak valid.")

    if nama_prioritas not in {
        "Protein", "Karbohidrat", "Lemak", "Seimbang"
    }:
        raise ValueError("Prioritas nutrisi tidak dikenali.")

    if nama_prioritas == "Seimbang":
        try:
            acuan_seimbang = {
                "Protein": float(prioritas.acuan_protein),
                "Karbohidrat": float(prioritas.acuan_karbo),
                "Lemak": float(prioritas.acuan_lemak),
            }
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Acuan nutrisi seimbang tidak valid.") from None
        if (
            not all(math.isfinite(value) and 0 <= value <= 1 for value in acuan_seimbang.values())
            or not math.isclose(sum(acuan_seimbang.values()), 1.0, abs_tol=0.01)
        ):
            raise ValueError("Acuan nutrisi seimbang tidak valid.")
    else:
        try:
            ambang_prioritas = float(prioritas.min_persen_energi)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Ambang prioritas nutrisi tidak valid.") from None
        if not math.isfinite(ambang_prioritas) or not 0 < ambang_prioritas <= 1:
            raise ValueError("Ambang prioritas nutrisi tidak valid.")

    menu_valid = []

    for makanan in get_semua_makanan(db):
        nutrisi = _baca_nutrisi(makanan)

        if nutrisi is not None:
            kalori, proporsi = nutrisi
            menu_valid.append((makanan, kalori, proporsi))

    if not menu_valid:
        return []

    hasil = []

    for makanan, kalori, proporsi in menu_valid:
        if permintaan.status_alergi:
            if not _lolos_alergi(makanan, pilihan):
                continue

        skor_kalori = _skor_kalori(kalori, target)

        if nama_prioritas == "Seimbang":
            selisih = sum(
                abs(proporsi[zat] - nilai)
                for zat, nilai in acuan_seimbang.items()
            )
            skor_prioritas = max(0.0, 1.0 - selisih / 2)
        else:
            skor_prioritas = min(
                1.0,
                proporsi[nama_prioritas] / ambang_prioritas,
            )

        skor = 100 * (
            BOBOT_KALORI * skor_kalori
            + BOBOT_PRIORITAS * skor_prioritas
        )

        hasil.append({
            "makanan": makanan,
            "skor_kalori": skor_kalori,
            "skor_prioritas": skor_prioritas,
            "skor_content_based": skor,
        })

    hasil.sort(
        key=lambda item: (
            -item["skor_content_based"],
            item["makanan"].id_makanan,
        )
    )

    return hasil[:3]


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
    print("Hasil bukan jaminan keamanan alergi atau saran medis.")
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
                print(f"   Skor kalori: {item['skor_kalori']:.3f} | Skor prioritas: {item['skor_prioritas']:.3f} | Skor content-based: {item['skor_content_based']:.2f}")
            print("\nSkor bukan probabilitas atau jaminan keamanan alergi. NO Excel bukan ID database.")
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f"\nDemo berhenti: {exc}")
        return 1
    finally:
        if "engine" in locals():
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(demo_terminal())
