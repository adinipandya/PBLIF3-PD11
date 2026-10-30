"""
tests/conftest.py
Konfigurasi pytest dan fixture bersama.

Menggunakan SQLite in-memory agar test bisa dijalankan tanpa MySQL.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.base import Base
from app.models import Makanan, InformasiGizi, Alergen, KandunganAlergen
from app.models import TargetKalori, PrioritasNutrisi
from app.db.session import get_db
from app.main import app

# ── Engine SQLite in-memory ───────────────────────────────────────────────────
SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine_test = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(bind=engine_test, autocommit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def buat_tabel():
    """Buat semua tabel sebelum test; hapus sesudahnya."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture()
def db_session() -> Session:
    """Fixture sesi database yang di-rollback setelah setiap test."""
    connection = engine_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """Fixture TestClient dengan override dependency database."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Data fixture ──────────────────────────────────────────────────────────────

@pytest.fixture()
def seed_referensi(db_session: Session):
    """Isi tabel referensi dengan data minimal untuk test."""
    # Target kalori
    db_session.add_all([
        TargetKalori(id_target=1, nama_kategori="Rendah", kalori_min=None, kalori_max=300,
                     keterangan="< 300 kkal"),
        TargetKalori(id_target=2, nama_kategori="Sedang", kalori_min=300, kalori_max=500,
                     keterangan="300–500 kkal"),
        TargetKalori(id_target=3, nama_kategori="Tinggi", kalori_min=500, kalori_max=None,
                     keterangan="> 500 kkal"),
    ])
    # Prioritas nutrisi
    db_session.add_all([
        PrioritasNutrisi(id_prioritas=1, nama_prioritas="Protein", jenis="zat_gizi",
                         keterangan="Prioritaskan protein"),
        PrioritasNutrisi(id_prioritas=2, nama_prioritas="Karbohidrat", jenis="zat_gizi"),
        PrioritasNutrisi(id_prioritas=3, nama_prioritas="Lemak", jenis="zat_gizi"),
        PrioritasNutrisi(id_prioritas=4, nama_prioritas="Seimbang", jenis="seimbang",
                         acuan_protein=0.15, acuan_karbo=0.55, acuan_lemak=0.30),
    ])
    # Alergen
    db_session.add_all([
        Alergen(id_alergen=1, nama_alergen="Telur", kata_kunci="telur"),
        Alergen(id_alergen=2, nama_alergen="Kedelai", kata_kunci="kedelai"),
        Alergen(id_alergen=3, nama_alergen="Ayam", kata_kunci="ayam"),
    ])
    db_session.flush()
    return db_session


@pytest.fixture()
def seed_makanan(seed_referensi: Session):
    """Isi tabel makanan dengan dua item untuk test."""
    db = seed_referensi
    # Makanan 1: Sup Tahu Telur (Rendah, mengandung telur + kedelai)
    db.add(Makanan(
        id_makanan=3, nama_makanan="Sup Tahu Telur",
        deskripsi_porsi="1 mangkuk sedang sup hangat",
        berat_porsi_gram=None,
        sumber_data="https://nutrinusa.id/kalori/sup-tahu-telur",
        kelompok_kalori="Rendah", label_prioritas="Protein; Lemak",
        versi_dataset="revisi-PD11-R1",
    ))
    db.add(InformasiGizi(
        id_makanan=3, kalori=150, karbohidrat=8, lemak=8, protein=10
    ))
    # Makanan 2: Soto Ayam Bening (Rendah, mengandung ayam)
    db.add(Makanan(
        id_makanan=5, nama_makanan="Soto Ayam Bening",
        deskripsi_porsi="1 porsi (400 g)",
        berat_porsi_gram=400,
        sumber_data="https://nutrinusa.id/kalori/soto-ayam-bening",
        kelompok_kalori="Rendah", label_prioritas="Protein",
        versi_dataset="revisi-PD11-R1",
    ))
    db.add(InformasiGizi(
        id_makanan=5, kalori=250, karbohidrat=15, lemak=12, protein=18
    ))
    db.flush()

    # Kandungan alergen
    db.add(KandunganAlergen(
        id_makanan=3, id_alergen=1,  # Telur
        status_verifikasi="Belum diverifikasi",
        bahan_penyebab="telur",
        catatan_verifikasi="Konfirmasi resep sebelum operasional.",
    ))
    db.add(KandunganAlergen(
        id_makanan=3, id_alergen=2,  # Kedelai
        status_verifikasi="Belum diverifikasi",
        bahan_penyebab="kedelai",
    ))
    db.add(KandunganAlergen(
        id_makanan=5, id_alergen=3,  # Ayam
        status_verifikasi="Belum diverifikasi",
        bahan_penyebab="ayam",
    ))
    db.flush()
    return db

