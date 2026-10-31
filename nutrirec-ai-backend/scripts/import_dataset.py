"""
scripts/import_dataset.py
Skrip impor dataset makanan dari file Excel ke database MySQL.

Cara pakai:
  python scripts/import_dataset.py --file path/ke/Dataset_makanan_revisi.xlsx

Fitur:
  - Membaca sheet "Dataset" dari Excel
  - Mempertahankan ID, angka gizi, porsi, sumber, dan alergen tercatat
  - Status verifikasi alergen = "Belum diverifikasi" (sesuai dataset)
  - Impor dalam satu transaksi; aman dijalankan ulang (idempotent via UPSERT)
  - Melaporkan error jelas untuk nilai wajib yang tidak tersedia
  - Tidak membuat data sintetis

Pemetaan kolom Excel → database:
  Kolom A (NO)          → id_makanan (dipakai sebagai ID stabil)
  Kolom B (NAMA)        → nama_makanan
  Kolom C (KALORI)      → informasi_gizi.kalori
  Kolom D (KARBO)       → informasi_gizi.karbohidrat
  Kolom E (LEMAK)       → informasi_gizi.lemak
  Kolom F (PROTEIN)     → informasi_gizi.protein
  Kolom G (PORSI)       → deskripsi_porsi
  Kolom H (KEL.KALORI)  → kelompok_kalori (nilai formula yang tersedia)
  Kolom L (PRIORITAS)   → label_prioritas
  Kolom M (ALERGEN)     → kandungan_alergen (daftar tercatat)
  Kolom N (SUMBER DATA) → sumber_data
  Kolom O (STATUS AL.)  → status_verifikasi di kandungan_alergen
  Kolom P (CATATAN)     → catatan_verifikasi di kandungan_alergen

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

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
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


# ─── Pembaca Excel manual (tanpa openpyxl) ───────────────────────────────────

def baca_shared_strings(z: zipfile.ZipFile) -> list[str]:
    """Baca tabel shared strings dari file xlsx."""
    with z.open("xl/sharedStrings.xml") as f:
        content = f.read().decode("utf-8")
    sis = re.findall(r"<x:si>(.*?)</x:si>", content, re.DOTALL)
    result = []
    for si in sis:
        texts = re.findall(r"<x:t[^/]*>([^<]*)</x:t>", si)
        result.append("".join(texts))
    return result


def ambil_nilai_sel(cell_xml: str, shared_strings: list[str]) -> str | None:
    """Ambil nilai teks dari XML satu sel."""
    t_attr = re.search(r't="([^"]+)"', cell_xml)
    v = re.search(r"<x:v>([^<]*)</x:v>", cell_xml)
    if not v:
        return None
    val = v.group(1)
    if t_attr and t_attr.group(1) == "s":
        idx = int(val)
        return shared_strings[idx] if idx < len(shared_strings) else None
    return val


def baca_dataset(xlsx_path: str) -> list[dict]:
    """
    Baca sheet Dataset dari file xlsx.
    Kembalikan list of dict dengan kunci: A, B, C, D, E, F, G, H, L, M, N, O, P.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        shared_strings = baca_shared_strings(z)
        # sheet1.xml = sheet pertama = Dataset
        with z.open("xl/worksheets/sheet1.xml") as f:
            content = f.read().decode("utf-8")

    rows_xml = re.findall(r'<x:row r="(\d+)"[^>]*>(.*?)</x:row>', content, re.DOTALL)
    records = []
    for row_num_str, row_content in rows_xml:
        row_num = int(row_num_str)
        if row_num == 1:  # baris header, lewati
            continue

        cells_xml = re.findall(
            r'<x:c r="([A-Z]+)\d+"[^>]*>(.*?)</x:c>', row_content, re.DOTALL
        )
        row_data: dict[str, str | None] = {}
        for col, cell_content in cells_xml:
            row_data[col] = ambil_nilai_sel(cell_content, shared_strings)

        if row_data.get("A") and row_data.get("B"):
            records.append(row_data)

    return records


# ─── Utilitas ─────────────────────────────────────────────────────────────────

def parse_decimal(nilai: str | None, nama_kolom: str, baris: int) -> Decimal:
    """Konversi string ke Decimal; raise ValueError jika gagal."""
    if nilai is None or str(nilai).strip() == "":
        raise ValueError(
            f"Baris {baris}: kolom '{nama_kolom}' wajib diisi tetapi kosong."
        )
    try:
        return Decimal(str(nilai).strip())
    except InvalidOperation:
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
    """
    Urai teks alergen tercatat menjadi list nama_alergen yang cocok.
    Contoh: "telur; kedelai; jagung" → ["Telur", "Kedelai", "Jagung"]
    """
    if not teks or not teks.strip():
        return []
    bagian = [b.strip().lower() for b in re.split(r"[;,]", teks)]
    hasil = []
    for b in bagian:
        if b in PETA_ALERGEN:
            hasil.append(PETA_ALERGEN[b])
        else:
            # Coba cocokkan sebagian
            cocok = None
            for kunci, nama in PETA_ALERGEN.items():
                if kunci in b or b in kunci:
                    cocok = nama
                    break
            if cocok:
                hasil.append(cocok)
            elif b:
                print(
                    f"  [PERINGATAN] Alergen tidak dikenali: '{b}'. Dilewati."
                )
    # Hilangkan duplikasi sambil mempertahankan urutan
    seen = set()
    return [x for x in hasil if not (x in seen or seen.add(x))]


def tentukan_kelompok_kalori(kalori: Decimal) -> str:
    """
    Tentukan kelompok kalori sesuai spesifikasi:
      Rendah < 300 kkal
      Sedang 300–500 kkal inklusif
      Tinggi > 500 kkal
    """
    if kalori < 300:
        return "Rendah"
    elif kalori <= 500:
        return "Sedang"
    else:
        return "Tinggi"


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

            if kalori < 0 or karbo < 0 or lemak < 0 or protein < 0:
                raise ValueError(
                    f"{baris_str}: nilai nutrisi tidak boleh negatif."
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
                    f"vs hitung='{kelompok_hitung}'. Pakai hasil hitung."
                )
            kelompok_kalori = kelompok_hitung

            # Label prioritas (kolom L)
            label_prioritas = rec.get("L", "").strip() if rec.get("L") else None

            # Alergen (kolom M)
            alergen_teks = rec.get("M", "")
            alergen_list = parse_alergen_tercatat(alergen_teks)

            # Status verifikasi (kolom O)
            status_ver = rec.get("O", "Belum diverifikasi") or "Belum diverifikasi"
            status_ver = status_ver.strip()

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
                "status_verifikasi": status_ver,
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
        # Ambil peta alergen dari DB
        alergen_db: dict[str, Alergen] = {
            a.nama_alergen: a
            for a in db.scalars(select(Alergen)).all()
        }

        n_baru = 0
        n_update = 0

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
                n_update += 1

            # Hapus kandungan_alergen lama untuk makanan ini, lalu isi ulang
            db.execute(
                text(
                    "DELETE FROM kandungan_alergen WHERE id_makanan = :id"
                ),
                {"id": d["id_makanan"]},
            )
            db.flush()

            for nama_al in d["alergen_list"]:
                al_obj = alergen_db.get(nama_al)
                if al_obj is None:
                    print(
                        f"  [PERINGATAN] Alergen '{nama_al}' tidak ditemukan "
                        f"di database. Lewati."
                    )
                    continue
                ka = KandunganAlergen(
                    id_makanan=d["id_makanan"],
                    id_alergen=al_obj.id_alergen,
                    status_verifikasi=d["status_verifikasi"],
                    bahan_penyebab=nama_al.lower(),
                    catatan_verifikasi=d["catatan_verifikasi"],
                )
                db.add(ka)

        db.commit()
        print(f"\nImpor selesai: {n_baru} baris baru, {n_update} baris diperbarui.")

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
        help="Path ke file Excel (Dataset_makanan_revisi.xlsx)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parsing dan validasi saja; tidak menulis ke database.",
    )
    args = parser.parse_args()

    jalankan_impor(args.file, dry_run=args.dry_run)

