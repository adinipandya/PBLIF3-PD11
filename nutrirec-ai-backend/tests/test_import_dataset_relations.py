from app.models.alergen import Alergen, KandunganAlergen
from scripts.import_dataset import tambahkan_relasi_alergen_baru


def test_importer_preserves_existing_verification_and_only_adds_missing_pair(
    seed_makanan,
):
    db = seed_makanan
    existing = db.get(KandunganAlergen, (3, 1))
    existing.status_verifikasi = "Terverifikasi"
    existing.sumber_bukti = "bukti yang sudah ada"
    existing.id_pengelola = "pengelola-sebelumnya"
    old_note = existing.catatan_verifikasi
    db.flush()

    allergens = {
        item.nama_alergen: item
        for item in db.query(Alergen).all()
    }
    added = tambahkan_relasi_alergen_baru(
        db,
        3,
        ["Telur", "Ayam"],
        allergens,
        "catatan dari dataset",
    )
    db.flush()

    assert added == 1
    assert existing.status_verifikasi == "Terverifikasi"
    assert existing.sumber_bukti == "bukti yang sudah ada"
    assert existing.id_pengelola == "pengelola-sebelumnya"
    assert existing.catatan_verifikasi == old_note
    new_relation = db.get(KandunganAlergen, (3, allergens["Ayam"].id_alergen))
    assert new_relation.status_verifikasi == "Belum diverifikasi"
    assert db.query(KandunganAlergen).filter_by(id_makanan=3).count() == 3
