"""Dry-run-first synchronization of evidence-backed allergen verification."""

import argparse
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.core.config import get_settings
from scripts.import_dataset import baca_dataset, parse_alergen_tercatat


DEFAULT_FILE = project_root.parent / "data" / "Dataset_makanan_fix.xlsx"
VERIFICATION_SHEET = "Verifikasi Alergen"
EVIDENCE_COLUMNS = {
    "sumber_bukti",
    "waktu_verifikasi",
    "id_pengelola",
}
REQUIRED_EVIDENCE_HEADERS = (
    "ID MAKANAN",
    "NAMA MAKANAN",
    "ID ALERGEN",
    "NAMA ALERGEN",
    "BAHAN PENYEBAB",
    "STATUS VERIFIKASI",
    "SUMBER REFERENSI",
    "CATATAN VERIFIKASI",
)
DATASET_HEADERS = (
    "NO",
    "NAMA MAKANAN",
    "KALORI (KKAL)",
    "KARBO (G)",
    "LEMAK (G)",
    "PROTEIN (G)",
    "PORSI",
    "KELOMPOK KALORI",
    "% ENERGI PROTEIN",
    "% ENERGI KARBO",
    "% ENERGI LEMAK",
    "PRIORITAS NUTRISI",
    "ALERGEN TERCATAT",
    "SUMBER DATA",
    "STATUS ALERGEN",
    "CATATAN VERIFIKASI",
)


@dataclass(frozen=True)
class EvidenceRow:
    row_number: int
    id_makanan: int
    nama_makanan: str
    id_alergen: int
    nama_alergen: str
    status_verifikasi: str
    bahan_penyebab: str | None
    catatan_verifikasi: str | None
    sumber_bukti: str | None
    waktu_verifikasi: datetime | None
    id_pengelola: str | None

    def values(self) -> dict[str, Any]:
        return {
            "status_verifikasi": self.status_verifikasi,
            "bahan_penyebab": self.bahan_penyebab,
            "catatan_verifikasi": self.catatan_verifikasi,
            "sumber_bukti": self.sumber_bukti,
            "waktu_verifikasi": self.waktu_verifikasi,
            "id_pengelola": self.id_pengelola,
        }


@dataclass(frozen=True)
class PlannedChange:
    action: str
    evidence: EvidenceRow
    previous: dict[str, Any] | None


@dataclass
class SyncPlan:
    food_count: int
    expected_pair_count: int
    existing_pair_count: int
    verification_sheet_present: bool
    evidence_row_count: int
    verified_count: int
    ignored_pending_count: int
    changes: list[PlannedChange]
    unchanged_count: int
    missing_columns: set[str]
    errors: list[str]


def _positive_id(value: Any, label: str, row_number: int) -> int:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"baris {row_number}: {label} bukan ID numerik.") from exc
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"baris {row_number}: {label} harus berupa bilangan bulat.")
    result = int(decimal_value)
    if result <= 0:
        raise ValueError(f"baris {row_number}: {label} harus lebih besar dari nol.")
    return result


def _required_text(value: Any, label: str, row_number: int) -> str:
    result = "" if value is None else str(value).strip()
    if not result:
        raise ValueError(f"baris {row_number}: {label} wajib diisi.")
    return result


def _validate_dataset_headers(path: Path) -> None:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Dataset" not in workbook.sheetnames:
            raise ValueError("Sheet 'Dataset' tidak ditemukan.")
        values = next(
            workbook["Dataset"].iter_rows(
                min_row=1,
                max_row=1,
                max_col=len(DATASET_HEADERS),
                values_only=True,
            ),
            None,
        )
        actual = tuple(
            str(value).strip().upper() if value is not None else ""
            for value in (values or ())
        )
        if actual != DATASET_HEADERS:
            raise ValueError(
                "Urutan header Dataset tidak cocok dengan format kolom "
                "yang digunakan untuk ID makanan dan daftar alergen."
            )
    finally:
        workbook.close()


def _parse_datetime(value: Any, row_number: int) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).strip())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"baris {row_number}: WAKTU VERIFIKASI harus berupa tanggal-waktu ISO."
            ) from exc
    if result.tzinfo is not None:
        raise ValueError(
            f"baris {row_number}: WAKTU VERIFIKASI harus tanpa zona waktu "
            "karena kolom MySQL bertipe DATETIME."
        )
    return result


def _read_evidence_rows(path: Path) -> tuple[bool, list[EvidenceRow], list[str]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if VERIFICATION_SHEET not in workbook.sheetnames:
            return False, [], []
        sheet = workbook[VERIFICATION_SHEET]
        rows = sheet.iter_rows(values_only=True)
        raw_headers = next(rows, None)
        headers = {
            str(value).strip().upper(): index
            for index, value in enumerate(raw_headers or ())
            if value is not None and str(value).strip()
        }
        normalized_headers = [
            str(value).strip().upper()
            for value in (raw_headers or ())
            if value is not None and str(value).strip()
        ]
        duplicates = sorted(
            {header for header in normalized_headers if normalized_headers.count(header) > 1}
        )
        if duplicates:
            return True, [], [
                f"Header duplikat pada sheet '{VERIFICATION_SHEET}': "
                + ", ".join(duplicates)
                + "."
            ]
        missing_headers = [
            header for header in REQUIRED_EVIDENCE_HEADERS if header not in headers
        ]
        if missing_headers:
            return True, [], [
                "Kolom wajib tidak ditemukan pada sheet "
                f"'{VERIFICATION_SHEET}': {', '.join(missing_headers)}."
            ]

        evidence_rows = []
        errors = []
        for row_number, values in enumerate(rows, start=2):
            if not any(value is not None and str(value).strip() for value in values):
                continue
            cell = lambda name: values[headers[name]]
            try:
                status = _required_text(
                    cell("STATUS VERIFIKASI"), "STATUS VERIFIKASI", row_number
                )
                if status not in {"Belum diverifikasi", "Terverifikasi"}:
                    raise ValueError(
                        f"baris {row_number}: STATUS VERIFIKASI tidak dikenal."
                    )
                evidence_rows.append(
                    EvidenceRow(
                        row_number=row_number,
                        nama_makanan=_required_text(
                            cell("NAMA MAKANAN"), "NAMA MAKANAN", row_number
                        ),
                        nama_alergen=_required_text(
                            cell("NAMA ALERGEN"), "NAMA ALERGEN", row_number
                        ),
                        id_makanan=_positive_id(
                            cell("ID MAKANAN"), "ID MAKANAN", row_number
                        ),
                        id_alergen=_positive_id(
                            cell("ID ALERGEN"), "ID ALERGEN", row_number
                        ),
                        status_verifikasi=status,
                        bahan_penyebab=(
                            str(cell("BAHAN PENYEBAB")).strip()
                            if cell("BAHAN PENYEBAB") is not None
                            and str(cell("BAHAN PENYEBAB")).strip()
                            else None
                        ),
                        catatan_verifikasi=(
                            str(cell("CATATAN VERIFIKASI")).strip()
                            if cell("CATATAN VERIFIKASI") is not None
                            and str(cell("CATATAN VERIFIKASI")).strip()
                            else None
                        ),
                        sumber_bukti=(
                            str(cell("SUMBER REFERENSI")).strip()
                            if cell("SUMBER REFERENSI") is not None
                            and str(cell("SUMBER REFERENSI")).strip()
                            else None
                        ),
                        waktu_verifikasi=(
                            _parse_datetime(cell("WAKTU VERIFIKASI"), row_number)
                            if "WAKTU VERIFIKASI" in headers
                            and cell("WAKTU VERIFIKASI") is not None
                            and str(cell("WAKTU VERIFIKASI")).strip()
                            else None
                        ),
                        id_pengelola=(
                            str(cell("ID PENGELOLA")).strip()
                            if "ID PENGELOLA" in headers
                            and cell("ID PENGELOLA") is not None
                            and str(cell("ID PENGELOLA")).strip()
                            else None
                        ),
                    )
                )
                evidence = evidence_rows[-1]
                if evidence.bahan_penyebab and len(evidence.bahan_penyebab) > 300:
                    raise ValueError(
                        f"baris {row_number}: BAHAN PENYEBAB melebihi 300 karakter."
                    )
                if evidence.id_pengelola and len(evidence.id_pengelola) > 100:
                    raise ValueError(
                        f"baris {row_number}: ID PENGELOLA melebihi 100 karakter."
                    )
                if status == "Terverifikasi" and not all(
                    (
                        evidence.bahan_penyebab,
                        evidence.sumber_bukti,
                        evidence.catatan_verifikasi,
                    )
                ):
                    evidence_rows.pop()
                    raise ValueError(
                        f"baris {row_number}: status Terverifikasi memerlukan "
                        "bahan penyebab, sumber referensi, dan catatan verifikasi."
                    )
            except ValueError as exc:
                errors.append(str(exc))
        return True, evidence_rows, errors
    finally:
        workbook.close()


def build_sync_plan(conn: Connection, workbook_path: Path) -> SyncPlan:
    _validate_dataset_headers(workbook_path)
    dataset_rows = baca_dataset(str(workbook_path))
    allergens_by_name = {
        row["nama_alergen"]: row["id_alergen"]
        for row in conn.execute(
            text("SELECT id_alergen, nama_alergen FROM alergen")
        ).mappings()
    }
    foods_by_id = {
        row["id_makanan"]: row["nama_makanan"]
        for row in conn.execute(
            text("SELECT id_makanan, nama_makanan FROM makanan")
        ).mappings()
    }
    allergens_by_id = {
        id_alergen: nama_alergen
        for nama_alergen, id_alergen in allergens_by_name.items()
    }
    expected_pairs = set()
    errors: list[str] = []
    dataset_food_ids = set()
    dataset_food_names = {}
    for row_number, dataset_row in enumerate(dataset_rows, start=2):
        id_makanan = _positive_id(dataset_row.get("A"), "NO", row_number)
        if id_makanan in dataset_food_ids:
            errors.append(f"Dataset: ID makanan {id_makanan} tercatat lebih dari sekali.")
        dataset_food_ids.add(id_makanan)
        dataset_food_names[id_makanan] = str(dataset_row.get("B") or "").strip()
        if (
            id_makanan in foods_by_id
            and dataset_food_names[id_makanan] != foods_by_id[id_makanan]
        ):
            errors.append(
                f"Dataset: nama makanan untuk ID {id_makanan} tidak cocok "
                "dengan database."
            )
        for name in parse_alergen_tercatat(dataset_row.get("M")):
            if name not in allergens_by_name:
                errors.append(
                    f"Dataset: alergen {name!r} untuk makanan {id_makanan} "
                    "tidak ditemukan pada tabel referensi."
                )
                continue
            expected_pairs.add((id_makanan, allergens_by_name[name]))

    sheet_present, evidence_rows, sheet_errors = _read_evidence_rows(workbook_path)
    errors.extend(sheet_errors)
    for id_makanan in sorted(dataset_food_ids - set(foods_by_id)):
        errors.append(f"Dataset: id_makanan {id_makanan} tidak ditemukan di database.")

    columns = {
        column["name"] for column in inspect(conn).get_columns("kandungan_alergen")
    }
    missing_columns = EVIDENCE_COLUMNS - columns
    select_columns = [
        "id_makanan",
        "id_alergen",
        "status_verifikasi",
        "bahan_penyebab",
        "catatan_verifikasi",
    ]
    select_columns.extend(sorted(EVIDENCE_COLUMNS & columns))
    existing = {}
    statement = "SELECT " + ", ".join(select_columns) + " FROM kandungan_alergen"
    for row in conn.execute(text(statement)).mappings():
        current = dict(row)
        verified_at = current.get("waktu_verifikasi")
        if isinstance(verified_at, str):
            current["waktu_verifikasi"] = datetime.fromisoformat(verified_at)
        existing[(row["id_makanan"], row["id_alergen"])] = current

    changes: list[PlannedChange] = []
    unchanged_count = 0
    ignored_pending_count = 0
    seen_pairs = set()
    for evidence in evidence_rows:
        pair = (evidence.id_makanan, evidence.id_alergen)
        if pair in seen_pairs:
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"pasangan ID {pair} duplikat."
            )
            continue
        seen_pairs.add(pair)
        names_match = True
        if (
            evidence.id_makanan in foods_by_id
            and evidence.nama_makanan != foods_by_id[evidence.id_makanan]
        ):
            names_match = False
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"nama makanan tidak cocok dengan ID {evidence.id_makanan}."
            )
        if (
            evidence.id_alergen in allergens_by_id
            and evidence.nama_alergen != allergens_by_id[evidence.id_alergen]
        ):
            names_match = False
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"nama alergen tidak cocok dengan ID {evidence.id_alergen}."
            )
        if not names_match:
            continue
        if pair not in expected_pairs:
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"pasangan ID {pair} tidak ada pada sheet Dataset."
            )
            continue
        if evidence.id_makanan not in foods_by_id:
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"id_makanan {evidence.id_makanan} tidak ada di database."
            )
            continue
        if evidence.id_alergen not in allergens_by_id:
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}' baris {evidence.row_number}: "
                f"id_alergen {evidence.id_alergen} tidak ada di database."
            )
            continue
        if evidence.status_verifikasi == "Belum diverifikasi":
            ignored_pending_count += 1
            continue
        previous = existing.get(pair)
        if previous is not None and all(
            previous.get(column) == value
            for column, value in evidence.values().items()
        ):
            unchanged_count += 1
            continue
        changes.append(
            PlannedChange(
                action="insert" if previous is None else "update",
                evidence=evidence,
                previous=previous,
            )
        )

    if sheet_present:
        for pair in sorted(expected_pairs - seen_pairs):
            errors.append(
                f"Sheet '{VERIFICATION_SHEET}': pasangan ID {pair} dari Dataset "
                "belum memiliki baris."
            )

    return SyncPlan(
        food_count=len(dataset_rows),
        expected_pair_count=len(expected_pairs),
        existing_pair_count=len(existing),
        verification_sheet_present=sheet_present,
        evidence_row_count=len(evidence_rows),
        verified_count=sum(
            evidence.status_verifikasi == "Terverifikasi"
            for evidence in evidence_rows
        ),
        ignored_pending_count=ignored_pending_count,
        changes=changes,
        unchanged_count=unchanged_count,
        missing_columns=missing_columns,
        errors=errors,
    )


def apply_sync_plan(conn: Connection, plan: SyncPlan) -> int:
    if plan.errors:
        raise ValueError("Sinkronisasi dibatalkan karena ada kesalahan validasi.")
    if plan.changes and plan.missing_columns:
        raise ValueError(
            "Sinkronisasi diblokir; migrasikan dahulu kolom: "
            + ", ".join(sorted(plan.missing_columns))
        )
    for change in plan.changes:
        evidence = change.evidence
        values = evidence.values()
        values.update(
            id_makanan=evidence.id_makanan,
            id_alergen=evidence.id_alergen,
        )
        if change.action == "insert":
            conn.execute(
                text(
                    "INSERT INTO kandungan_alergen "
                    "(id_makanan, id_alergen, status_verifikasi, bahan_penyebab, "
                    "catatan_verifikasi, sumber_bukti, waktu_verifikasi, id_pengelola) "
                    "VALUES (:id_makanan, :id_alergen, :status_verifikasi, "
                    ":bahan_penyebab, :catatan_verifikasi, :sumber_bukti, "
                    ":waktu_verifikasi, :id_pengelola)"
                ),
                values,
            )
        else:
            result = conn.execute(
                text(
                    "UPDATE kandungan_alergen SET status_verifikasi=:status_verifikasi, "
                    "bahan_penyebab=:bahan_penyebab, "
                    "catatan_verifikasi=:catatan_verifikasi, "
                    "sumber_bukti=:sumber_bukti, waktu_verifikasi=:waktu_verifikasi, "
                    "id_pengelola=:id_pengelola "
                    "WHERE id_makanan=:id_makanan AND id_alergen=:id_alergen"
                ),
                values,
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    f"Pasangan ID {(evidence.id_makanan, evidence.id_alergen)} "
                    "berubah saat sinkronisasi; transaksi harus diulang."
                )
    return len(plan.changes)


def print_plan(plan: SyncPlan, dry_run: bool) -> None:
    mode = "DRY-RUN (tidak ada perubahan database)" if dry_run else "APPLY"
    print(f"Mode: {mode}")
    print("Penghapusan makanan, nutrisi, atau relasi: 0 (tidak didukung oleh sinkronisasi)")
    print(f"Makanan dalam Dataset: {plan.food_count}")
    print(f"Pasangan makanan-alergen pada Dataset: {plan.expected_pair_count}")
    print(f"Pasangan yang ada di database: {plan.existing_pair_count}")
    print(
        f"Sheet bukti: {'tersedia' if plan.verification_sheet_present else 'tidak ada'}; "
        f"baris bukti terbaca: {plan.evidence_row_count}"
    )
    print(
        f"Status pada sheet: Terverifikasi={plan.verified_count}, "
        f"Belum diverifikasi={plan.evidence_row_count - plan.verified_count}"
    )
    print(f"Baris pending yang dilewati: {plan.ignored_pending_count}")
    print(
        f"Perubahan terencana: {len(plan.changes)} "
        f"(update={sum(change.action == 'update' for change in plan.changes)}, "
        f"insert={sum(change.action == 'insert' for change in plan.changes)}); "
        f"sudah sama={plan.unchanged_count}"
    )
    if not plan.verification_sheet_present:
        print(
            f"Blokir: tambahkan sheet '{VERIFICATION_SHEET}' dengan kolom ID "
            "dan bukti per pasangan; sheet Dataset lama tidak cukup untuk "
            "memverifikasi relasi."
        )
    if plan.missing_columns:
        print(
            "Blokir skema database: kolom belum tersedia: "
            + ", ".join(sorted(plan.missing_columns))
        )
    for error in plan.errors:
        print(f"ERROR: {error}")
    if plan.changes and not plan.errors and not plan.missing_columns:
        for change in plan.changes:
            evidence = change.evidence
            print(
                f"  {change.action}: ID makanan {evidence.id_makanan}, "
                f"ID alergen {evidence.id_alergen}, "
                f"status={evidence.status_verifikasi}"
            )
        print("Siap ditinjau; tidak ada perubahan dijalankan oleh mode dry-run.")
    elif not plan.changes:
        print("Tidak ada perubahan database yang akan dijalankan.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run-first sync verifikasi alergen berdasarkan pasangan ID dan "
            "bukti eksplisit."
        )
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_FILE,
        help=f"Workbook dataset (default: {DEFAULT_FILE})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Tampilkan rencana saja tanpa menulis ke database (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Tulis perubahan setelah dry-run ditinjau dan migrasi tersedia.",
    )
    args = parser.parse_args(argv)
    if not args.file.is_file():
        print(f"ERROR: File dataset tidak ditemukan: {args.file}")
        return 2

    engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        if args.apply:
            with engine.begin() as conn:
                plan = build_sync_plan(conn, args.file)
                print_plan(plan, dry_run=False)
                if plan.errors:
                    return 2
                if plan.changes and plan.missing_columns:
                    return 2
                updated = apply_sync_plan(conn, plan)
                print(f"Transaksi selesai; pasangan berubah: {updated}.")
        else:
            with engine.connect() as conn:
                plan = build_sync_plan(conn, args.file)
                print_plan(plan, dry_run=True)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
