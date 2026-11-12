"""
scripts/import_dataset.py
Skrip impor dataset makanan dari file Excel ke database MySQL.

Cara pakai:
  python scripts/import_dataset.py --file ../data/Dataset_makanan_fix.xlsx

Fitur:
  - Membaca sheet "Dataset" dari Excel
  - Mempertahankan ID, angka gizi, porsi, sumber, dan alergen tercatat
  - Status verifikasi alergen = "Belum diverifikasi" (sesuai dataset)
  - Impor dalam satu transaksi; aman dijalankan ulang (idempotent via UPSERT)
  - Melaporkan error jelas untuk nilai wajib yang tidak tersedia
  - Tidak membuat data sintetis
  - Tidak mengubah angka gizi sumber; label kalori turunan dihitung ulang

Pemetaan kolom Excel → database:
  Kolom A (NO)          → id_makanan (dipakai sebagai ID stabil)
  Kolom B (NAMA)        → nama_makanan
  Kolom C (KALORI)      → informasi_gizi.kalori
  Kolom D (KARBO)       → informasi_gizi.karbohidrat
  Kolom E (LEMAK)       → informasi_gizi.lemak
  Kolom F (PROTEIN)     → informasi_gizi.protein
  Kolom G (PORSI)       → deskripsi_porsi
  Kolom H (KEL.KALORI)  → sumber pembanding; kelompok_kalori dihitung ulang
                            dari kolom C menggunakan aturan kanonis
  Kolom L (PRIORITAS)   → label_prioritas
  Kolom M (ALERGEN)     → kandungan_alergen (daftar tercatat)
  Kolom N (SUMBER DATA) → sumber_data
  Kolom P (CATATAN)     → catatan awal pada relasi alergen yang baru dibuat

Kolom O (STATUS ALERGEN) tidak digunakan untuk mengubah status relasi.
Status terverifikasi hanya dapat disinkronkan melalui
scripts/sync_allergen_verification.py dengan bukti per pasangan ID.

BERAT PORSI:
  Tidak ada kolom berat terpisah di Excel. Berat diambil dari deskripsi
  porsi jika terdapat angka eksplisit (mis. "1 porsi (200 g)").
  Jika tidak ditemukan, berat_porsi_gram diisi NULL.
"""

import argparse
import os
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Tambahkan root proyek ke sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Muat .env jika ada
env_file = project_root / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.recommendation_rules import calorie_category
from app.db.session import SessionLocal
from app.models.makanan import Makanan, InformasiGizi
from app.models.alergen import Alergen, KandunganAlergen
from app.core.config import get_settings

settings = get_settings()


# ─── Pemetaan alergen ─────────────────────────────────────────────────────────
# Kata kunci di kolom M dataset → nama_alergen di tabel alergen
# Urutan diproses dari yang paling spesifik ke yang lebih umum.
PETA_ALERGEN: dict[str, str] = {
    "daging sapi": "Daging sapi",
    "kacang-kacangan": "Kacang-kacangan",
    "udang/seafood": "Udang/seafood",
    "kedelai": "Kedelai",
    "jagung": "Jagung",
    "kelapa": "Kelapa",
    "gandum": "Gandum",
    "telur": "Telur",
    "ayam": "Ayam",
    "ikan": "Ikan",
    "beras": "Beras",
}


# ─── Pembaca Excel menggunakan openpyxl ────────────────────

def baca_dataset(xlsx_path: str) -> list[dict]:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    workbook = load_workbook(
        filename=xlsx_path,
        read_only=True,
        data_only=True,
    )

    try:
        if "Dataset" not in workbook.sheetnames:
            raise ValueError(
                "Sheet 'Dataset' tidak ditemukan dalam file Excel."
            )

        sheet = workbook["Dataset"]
        records = []

        for nomor_baris, values in enumerate(
            sheet.iter_rows(
                min_row=2,
                max_col=16,
                values_only=True,
            ),
            start=2,
        ):
            # Lewati baris yang seluruh selnya kosong.
            if all(
                value is None or str(value).strip() == ""
                for value in values
            ):
                continue

            record = {}

            for nomor_kolom, value in enumerate(values, start=1):
                kolom = get_column_letter(nomor_kolom)
                record[kolom] = (
                    None if value is None else str(value).strip()
                )

            if not record.get("A") or not record.get("B"):
                raise ValueError(
                    f"Baris Excel {nomor_baris}: "
                    "NO dan NAMA MAKANAN wajib diisi."
                )

            records.append(record)

        if not records:
            raise ValueError(
                "Tidak ada data makanan yang terbaca."
            )

        return records

    finally:
        workbook.close()

# ─── Utilitas ─────────────────────────────────────────────────────────────────

def parse_decimal(nilai: str | None, nama_kolom: str, baris: int) -> Decimal:
    """Konversi string ke Decimal; raise ValueError jika gagal."""
    if nilai is None or str(nilai).strip() == "":
        raise ValueError(
            f"Baris {baris}: kolom '{nama_kolom}' wajib diisi tetapi kosong."
        )
    try:
        return Decimal(str(nilai).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(
            f"Baris {baris}: kolom '{nama_kolom}' = '{nilai}' bukan angka valid."
        )


def parse_berat_dari_porsi(deskripsi_porsi: str) -> Decimal | None:
    """
    Coba ekstrak berat gram dari string porsi.
    Contoh: "1 porsi (200 g)" → Decimal("200")
            "1 mangkuk sedang" → None
    """
    match = re.search(r'\([\s±]*(\d+(?:[.,]\d+)?)\s*g\)', deskripsi_porsi, re.IGNORECASE)
    if match:
        try:
            return Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
            pass
    return None


def parse_alergen_tercatat(teks: str | None) -> list[str]:
    if not teks or not teks.strip():
        return []

    hasil = []

    for bagian in re.split(r"[;,]", teks):
        bahan = bagian.strip().lower()

        if not bahan:
            continue

        if bahan not in PETA_ALERGEN:
            raise ValueError(
                f"Alergen tidak dikenali: '{bahan}'. "
                "Periksa kolom M sebelum melakukan impor."
            )

        nama = PETA_ALERGEN[bahan]

        if nama not in hasil:
            hasil.append(nama)

    return hasil

def tentukan_kelompok_kalori(kalori: Decimal) -> str:
    """Label kategori per porsi melalui sumber aturan bersama."""
    return calorie_category(kalori)


def tambahkan_relasi_alergen_baru(
    db: Session,
    id_makanan: int,
    alergen_list: list[str],
    alergen_db: dict[str, Alergen],
    catatan_verifikasi: str | None,
) -> int:
    """Insert only new pairs; never replace existing verification data."""
    ditambahkan = 0
    for nama_alergen in alergen_list:
        alergen = alergen_db[nama_alergen]
        if db.get(KandunganAlergen, (id_makanan, alergen.id_alergen)) is not None:
            continue
        db.add(
            KandunganAlergen(
                id_makanan=id_makanan,
                id_alergen=alergen.id_alergen,
                status_verifikasi="Belum diverifikasi",
                bahan_penyebab=nama_alergen.lower(),
                catatan_verifikasi=catatan_verifikasi,
            )
        )
        ditambahkan += 1
    return ditambahkan


# ─── Impor utama ──────────────────────────────────────────────────────────────

def jalankan_impor(xlsx_path: str, dry_run: bool = False) -> None:
    """
    Jalankan impor dataset dari Excel ke database.

    Args:
        xlsx_path: Path ke file Excel dataset.
        dry_run: Jika True, parsing dilakukan tetapi tidak ada data yang ditulis.
    """
    print(f"\n{'='*60}")
    print("  NutriRec AI — Impor Dataset Makanan")
    print(f"  File   : {xlsx_path}")
    print(f"  Versi  : {settings.DATASET_VERSION}")
    print(f"  Mode   : {'DRY RUN (tidak menulis ke DB)' if dry_run else 'IMPOR KE DATABASE'}")
    print(f"{'='*60}\n")

    # ── 1. Baca Excel ─────────────────────────────────────────────────────
    print("Membaca file Excel...")
    try:
        records = baca_dataset(xlsx_path)
    except FileNotFoundError:
        print(f"ERROR: File tidak ditemukan: {xlsx_path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR saat membaca Excel: {e}")
        sys.exit(1)

    print(f"Ditemukan {len(records)} baris data.\n")

    if not records:
        print("Tidak ada data untuk diimpor.")
        return

    # ── 2. Parsing dan validasi ───────────────────────────────────────────
    print("Memvalidasi data...")
    data_valid = []
    ada_error = False

    for i, rec in enumerate(records, start=2):  # baris 2 = data pertama
        baris_str = f"Baris {i}"
        try:
            # ID makanan (stabil dari kolom A)
            id_makan_raw = rec.get("A")
            if not id_makan_raw:
                raise ValueError(f"{baris_str}: kolom A (NO) kosong.")
            id_makanan = int(str(id_makan_raw).strip())

            # Nama makanan (kolom B)
            nama = rec.get("B", "").strip() if rec.get("B") else ""
            if not nama:
                raise ValueError(f"{baris_str}: kolom B (NAMA MAKANAN) kosong.")

            # Nutrisi (kolom C-F)
            kalori = parse_decimal(rec.get("C"), "KALORI", i)
            karbo  = parse_decimal(rec.get("D"), "KARBO",  i)
            lemak  = parse_decimal(rec.get("E"), "LEMAK",  i)
            protein = parse_decimal(rec.get("F"), "PROTEIN", i)

            if not all(value.is_finite() for value in (kalori, karbo, lemak, protein)):
                raise ValueError(f"{baris_str}: nilai nutrisi harus finite.")
            if kalori < 0 or karbo < 0 or lemak < 0 or protein < 0:
                raise ValueError(
                    f"{baris_str}: nilai nutrisi tidak boleh negatif."
                )
            try:
                energi_makro = Decimal(4) * protein + Decimal(4) * karbo + Decimal(9) * lemak
            except ArithmeticError:
                raise ValueError(f"{baris_str}: energi makro di luar rentang numerik.") from None
            if not energi_makro.is_finite() or energi_makro <= 0:
                raise ValueError(
                    f"{baris_str}: energi makro harus finite dan lebih dari nol."
                )

            # Porsi dan sumber
            porsi = rec.get("G", "").strip() if rec.get("G") else ""
            if not porsi:
                raise ValueError(f"{baris_str}: kolom G (PORSI) kosong.")

            sumber = rec.get("N", "").strip() if rec.get("N") else ""
            if not sumber:
                raise ValueError(f"{baris_str}: kolom N (SUMBER DATA) kosong.")

            # Kelompok kalori dari formula Excel (kolom H), fallback hitung ulang
            kelompok_excel = rec.get("H", "").strip() if rec.get("H") else ""
            kelompok_hitung = tentukan_kelompok_kalori(kalori)
            if kelompok_excel and kelompok_excel != kelompok_hitung:
                print(
                    f"  [INFO] {baris_str}: kelompok Excel='{kelompok_excel}' "
                    f"vs hitung='{kelompok_hitung}'. Nilai sumber dipertahankan; "
                    "hasil kategori tersimpan hanya pada kolom turunan."
                )
            kelompok_kalori = kelompok_hitung

            # Label prioritas (kolom L)
            label_prioritas = rec.get("L", "").strip() if rec.get("L") else None

            # Alergen (kolom M)
            alergen_teks = rec.get("M", "")
            alergen_list = parse_alergen_tercatat(alergen_teks)

            # Catatan verifikasi (kolom P)
            catatan_ver = rec.get("P", "").strip() if rec.get("P") else None

            # Berat porsi — ekstrak dari deskripsi, atau NULL
            berat = parse_berat_dari_porsi(porsi)

            data_valid.append({
                "id_makanan": id_makanan,
                "nama_makanan": nama,
                "kalori": kalori,
                "karbohidrat": karbo,
                "lemak": lemak,
                "protein": protein,
                "deskripsi_porsi": porsi,
                "berat_porsi_gram": berat,
                "sumber_data": sumber,
                "kelompok_kalori": kelompok_kalori,
                "label_prioritas": label_prioritas,
                "alergen_list": alergen_list,
                "catatan_verifikasi": catatan_ver,
                "versi_dataset": settings.DATASET_VERSION,
            })

        except ValueError as e:
            print(f"  [ERROR] {e}")
            ada_error = True

    print(f"\nValidasi selesai: {len(data_valid)} valid, "
          f"{len(records) - len(data_valid)} error.\n")

    if ada_error:
        print("Terdapat error validasi. Impor dihentikan. Perbaiki data dan coba lagi.")
        sys.exit(1)

    if dry_run:
        print("DRY RUN: data valid, tidak ada yang ditulis ke database.")
        for d in data_valid:
            print(
                f"  [{d['id_makanan']:2d}] {d['nama_makanan']:<40} "
                f"{d['kelompok_kalori']:<8} alergen={d['alergen_list']}"
            )
        return

    # ── 3. Tulis ke database (satu transaksi) ─────────────────────────────
    print("Menulis ke database...")

    db: Session = SessionLocal()
    try:
        # Fail before writing if the reference data cannot represent source allergens.
        alergen_db: dict[str, Alergen] = {
            a.nama_alergen: a
            for a in db.scalars(select(Alergen)).all()
        }
        alergen_diperlukan = {
            nama
            for record in data_valid
            for nama in record["alergen_list"]
        }
        alergen_hilang = alergen_diperlukan - alergen_db.keys()
        if alergen_hilang:
            raise ValueError(
                "Alergen belum tersedia di tabel referensi: "
                + ", ".join(sorted(alergen_hilang))
            )

        n_baru = 0
        n_update = 0
        n_relasi_baru = 0

        for d in data_valid:
            # Cek apakah sudah ada
            makan_ada = db.get(Makanan, d["id_makanan"])

            if makan_ada is None:
                # INSERT baru
                makanan = Makanan(
                    id_makanan=d["id_makanan"],
                    nama_makanan=d["nama_makanan"],
                    deskripsi_porsi=d["deskripsi_porsi"],
                    berat_porsi_gram=d["berat_porsi_gram"],
                    sumber_data=d["sumber_data"],
                    kelompok_kalori=d["kelompok_kalori"],
                    label_prioritas=d["label_prioritas"],
                    versi_dataset=d["versi_dataset"],
                )
                db.add(makanan)
                db.flush()  # dapatkan id agar relasi dapat dibuat

                gizi = InformasiGizi(
                    id_makanan=d["id_makanan"],
                    kalori=d["kalori"],
                    karbohidrat=d["karbohidrat"],
                    lemak=d["lemak"],
                    protein=d["protein"],
                )
                db.add(gizi)
                n_baru += 1
            else:
                # UPDATE data yang ada
                makan_ada.nama_makanan = d["nama_makanan"]
                makan_ada.deskripsi_porsi = d["deskripsi_porsi"]
                makan_ada.berat_porsi_gram = d["berat_porsi_gram"]
                makan_ada.sumber_data = d["sumber_data"]
                makan_ada.kelompok_kalori = d["kelompok_kalori"]
                makan_ada.label_prioritas = d["label_prioritas"]
                makan_ada.versi_dataset = d["versi_dataset"]

                gizi_ada = db.get(InformasiGizi, d["id_makanan"])
                if gizi_ada:
                    gizi_ada.kalori = d["kalori"]
                    gizi_ada.karbohidrat = d["karbohidrat"]
                    gizi_ada.lemak = d["lemak"]
                    gizi_ada.protein = d["protein"]
                else:
                    db.add(InformasiGizi(
                        id_makanan=d["id_makanan"],
                        kalori=d["kalori"],
                        karbohidrat=d["karbohidrat"],
                        lemak=d["lemak"],
                        protein=d["protein"],
                    ))
                n_update += 1

            n_relasi_baru += tambahkan_relasi_alergen_baru(
                db,
                d["id_makanan"],
                d["alergen_list"],
                alergen_db,
                d["catatan_verifikasi"],
            )

        db.commit()
        print(
            f"\nImpor selesai: {n_baru} makanan baru, {n_update} makanan "
            f"diperbarui, {n_relasi_baru} relasi alergen baru ditambahkan."
        )

    except Exception as e:
        db.rollback()
        print(f"\nERROR saat menulis ke database: {e}")
        print("Seluruh perubahan dibatalkan (rollback).")
        raise
    finally:
        db.close()

    print("\nRingkasan data yang diimpor:")
    for d in data_valid:
        berat_str = f"{d['berat_porsi_gram']} g" if d["berat_porsi_gram"] else "NULL"
        print(
            f"  [{d['id_makanan']:2d}] {d['nama_makanan']:<42} "
            f"Kalori={d['kalori']:>5} {d['kelompok_kalori']:<8} "
            f"Berat={berat_str:<10} "
            f"Alergen={d['alergen_list']}"
        )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Impor dataset makanan NutriRec AI dari Excel ke MySQL."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path ke file Excel katalog aktif (Dataset_makanan_fix.xlsx)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parsing dan validasi saja; tidak menulis ke database.",
    )
    args = parser.parse_args()

    jalankan_impor(args.file, dry_run=args.dry_run)
