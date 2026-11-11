from openpyxl import Workbook
from sqlalchemy import create_engine, text

from app.models import Base
from scripts.sync_allergen_verification import (
    apply_sync_plan,
    build_sync_plan,
)


DATASET_HEADERS = [
    "NO",
    "NAMA MAKANAN",
    "KALORI (kkal)",
    "KARBO (g)",
    "LEMAK (g)",
    "PROTEIN (g)",
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
]
EVIDENCE_HEADERS = [
    "ID MAKANAN",
    "NAMA MAKANAN",
    "ID ALERGEN",
    "NAMA ALERGEN",
    "BAHAN PENYEBAB",
    "STATUS VERIFIKASI",
    "SUMBER REFERENSI",
    "CATATAN VERIFIKASI",
]


def _workbook(path, *, evidence=None, legacy_status="Belum diverifikasi"):
    workbook = Workbook()
    dataset = workbook.active
    dataset.title = "Dataset"
    dataset.append(DATASET_HEADERS)
    dataset.append(
        [
            1, "Makanan Uji", 400, 40, 10, 20, "1 porsi", "Sedang",
            None, None, None, None, "telur", "sumber gizi",
            legacy_status, "catatan lama",
        ]
    )
    if evidence is not None:
        sheet = workbook.create_sheet("Verifikasi Alergen")
        sheet.append(EVIDENCE_HEADERS)
        for row in evidence:
            sheet.append(row)
    workbook.save(path)
    return path


def _database(*, legacy_schema=False):
    engine = create_engine("sqlite:///:memory:")
    if not legacy_schema:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO makanan "
                    "(id_makanan,nama_makanan,deskripsi_porsi,sumber_data,versi_dataset) "
                    "VALUES (1,'Makanan Uji','1 porsi','sumber gizi','uji')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO informasi_gizi "
                    "(id_makanan,kalori,karbohidrat,lemak,protein) "
                    "VALUES (1,400,40,10,20)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO alergen (id_alergen,nama_alergen,kata_kunci) "
                    "VALUES (1,'Telur','telur')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO kandungan_alergen "
                    "(id_makanan,id_alergen,status_verifikasi,bahan_penyebab,catatan_verifikasi) "
                    "VALUES (1,1,'Belum diverifikasi','telur','catatan awal')"
                )
            )
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE makanan (id_makanan INTEGER PRIMARY KEY, "
                    "nama_makanan TEXT)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE alergen "
                    "(id_alergen INTEGER PRIMARY KEY, nama_alergen TEXT)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE kandungan_alergen ("
                    "id_makanan INTEGER, id_alergen INTEGER, "
                    "status_verifikasi TEXT, bahan_penyebab TEXT, "
                    "catatan_verifikasi TEXT, PRIMARY KEY(id_makanan,id_alergen))"
                )
            )
            conn.execute(text("INSERT INTO makanan VALUES (1,'Makanan Uji')"))
            conn.execute(text("INSERT INTO alergen VALUES (1,'Telur')"))
            conn.execute(
                text(
                    "INSERT INTO kandungan_alergen VALUES "
                    "(1,1,'Belum diverifikasi','telur','catatan awal')"
                )
            )
    return engine


def _evidence(status="Terverifikasi", id_alergen=1):
    return [
        1,
        "Makanan Uji",
        id_alergen,
        "Telur",
        "telur",
        status,
        "https://evidence.example/resep",
        "resep ditinjau",
    ]


def test_legacy_status_without_evidence_sheet_is_never_synced(tmp_path):
    engine = _database()
    path = _workbook(
        tmp_path / "dataset.xlsx",
        legacy_status="Terverifikasi",
    )
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert plan.verification_sheet_present is False
            assert plan.expected_pair_count == 1
            assert plan.changes == []
            assert plan.missing_columns == set()
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT status_verifikasi FROM kandungan_alergen")
            ).scalar_one() == "Belum diverifikasi"
    finally:
        engine.dispose()


def test_dry_run_changes_nothing_and_apply_is_idempotent(tmp_path):
    engine = _database()
    path = _workbook(tmp_path / "dataset.xlsx", evidence=[_evidence()])
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert len(plan.changes) == 1
            assert plan.changes[0].action == "update"
            assert plan.missing_columns == set()
            assert conn.execute(
                text("SELECT status_verifikasi FROM kandungan_alergen")
            ).scalar_one() == "Belum diverifikasi"

        with engine.begin() as conn:
            assert apply_sync_plan(conn, build_sync_plan(conn, path)) == 1

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT status_verifikasi,sumber_bukti,waktu_verifikasi,id_pengelola "
                    "FROM kandungan_alergen"
                )
            ).one()
            assert row.status_verifikasi == "Terverifikasi"
            assert row.sumber_bukti == "https://evidence.example/resep"
            assert row.waktu_verifikasi is None
            assert row.id_pengelola is None
            assert conn.execute(
                text("SELECT kalori FROM informasi_gizi WHERE id_makanan=1")
            ).scalar_one() == 400
            plan = build_sync_plan(conn, path)
            assert plan.changes == []
            assert plan.unchanged_count == 1
    finally:
        engine.dispose()


def test_missing_audit_columns_block_database_write(tmp_path):
    engine = _database(legacy_schema=True)
    path = _workbook(tmp_path / "dataset.xlsx", evidence=[_evidence()])
    try:
        with engine.begin() as conn:
            plan = build_sync_plan(conn, path)
            assert plan.changes
            assert plan.missing_columns == {
                "sumber_bukti",
                "waktu_verifikasi",
                "id_pengelola",
            }
            try:
                apply_sync_plan(conn, plan)
            except ValueError as exc:
                assert "migrasikan dahulu" in str(exc)
            else:
                raise AssertionError("Expected missing audit fields to block sync.")
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT status_verifikasi FROM kandungan_alergen")
            ).scalar_one() == "Belum diverifikasi"
    finally:
        engine.dispose()


def test_pending_evidence_row_is_not_written(tmp_path):
    engine = _database()
    path = _workbook(
        tmp_path / "dataset.xlsx",
        evidence=[_evidence(status="Belum diverifikasi")],
    )
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert plan.ignored_pending_count == 1
            assert plan.changes == []
    finally:
        engine.dispose()


def test_pending_row_does_not_require_unverified_evidence_values(tmp_path):
    engine = _database()
    path = _workbook(
        tmp_path / "dataset.xlsx",
        evidence=[[1, "Makanan Uji", 1, "Telur", None, "Belum diverifikasi", None, None]],
    )
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert plan.errors == []
            assert plan.ignored_pending_count == 1
            assert plan.changes == []
    finally:
        engine.dispose()


def test_verified_row_requires_source_note_and_ingredient(tmp_path):
    engine = _database()
    path = _workbook(
        tmp_path / "dataset.xlsx",
        evidence=[[1, "Makanan Uji", 1, "Telur", "telur", "Terverifikasi", None, None]],
    )
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert any(
                "bahan penyebab, sumber referensi, dan catatan verifikasi"
                in error
                for error in plan.errors
            )
            assert plan.changes == []
    finally:
        engine.dispose()


def test_sheet_names_must_match_database_ids(tmp_path):
    engine = _database()
    evidence = _evidence()
    evidence[1] = "Makanan Lain"
    path = _workbook(tmp_path / "dataset.xlsx", evidence=[evidence])
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert any("nama makanan tidak cocok" in error for error in plan.errors)
            assert plan.changes == []
    finally:
        engine.dispose()


def test_sheet_must_include_every_dataset_pair(tmp_path):
    engine = _database()
    path = _workbook(tmp_path / "dataset.xlsx", evidence=[])
    try:
        with engine.connect() as conn:
            plan = build_sync_plan(conn, path)
            assert any("belum memiliki baris" in error for error in plan.errors)
            assert plan.changes == []
    finally:
        engine.dispose()


def test_non_dataset_pair_is_rejected(tmp_path):
    engine = _database()
    evidence = _evidence(id_alergen=2)
    evidence[3] = "Ayam"
    path = _workbook(
        tmp_path / "dataset.xlsx",
        evidence=[evidence],
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO alergen (id_alergen,nama_alergen,kata_kunci) VALUES (2,'Ayam','ayam')")
            )
            plan = build_sync_plan(conn, path)
            assert any("tidak ada pada sheet Dataset" in error for error in plan.errors)
            assert plan.changes == []
    finally:
        engine.dispose()
