import csv
import json
from copy import deepcopy

import pytest

from scripts import build_survey_candidate as bc
from scripts import prepare_survey as ps
from scripts import process_survey_version as pv


def sumber():
    def row(i, status="Tidak ada alergi", alergen="", prioritas="Protein tinggi"):
        return {"source_row": i, "Timestamp": "waktu", ps.REQUIRED_COLUMNS[1]: "Rendah (< 300 kkal)",
                ps.REQUIRED_COLUMNS[2]: prioritas, ps.REQUIRED_COLUMNS[3]: status, ps.REQUIRED_COLUMNS[4]: alergen,
                "1. Bihun Goreng Sayur": "3 = Sesuai (hampir sesuai target)",
                "20. Capcay Kuah (Ayam)": "3 = Sesuai (hampir sesuai target)"}
    rows = [row(2, prioritas="Seimbang (tidak ada prioritas khusus)"),
            row(3, status="Tidak ada alergi", alergen="Telur"),
            row(4, prioritas="Seimbang (tidak ada prioritas khusus)")]
    catalog = {
        name: {"id_sumber": i, "nama": name, "porsi": "1 porsi", "kalori": 300, "karbohidrat": 40, "lemak": 10, "protein": 10, "kategori_kalori_asli": "Sedang", "label_prioritas_asli": "", "alergen_asli": "", "status_alergen_asli": "Belum diverifikasi", "catatan": "", "audit_columns_available": True}
        for i, name in enumerate(ps.MAPELANGGAN_MAKANAN.values(), 1)
    }
    db_catalog = {i: {"id_makanan": i, "nama": name, "porsi": "1 porsi", "versi_dataset": "test-v1", "kalori": 300, "protein": 10, "karbohidrat": 40, "lemak": 10} for i, name in enumerate(ps.MAPELANGGAN_MAKANAN.values(), 1)}
    for index, record in enumerate(catalog.values(), 1):
        record["audit_columns_available"] = True
    responses, ratings, report = ps.siapkan_data(rows, {name: row["id_sumber"] for name, row in catalog.items()}, catalog_details=catalog, database_catalog=db_catalog, dataset_version="test-v1")
    for response in responses:
        response["versi_dataset_makanan"] = "test-v1"
    for rating in ratings:
        if "Capcay" not in rating["nama_makanan_survei"]:
            rating["status_pemetaan"] = "id_database_cocok_nama_porsi_perlu_review"
            rating["id_makanan"] = rating["id_makanan_katalog"] = rating["id_makanan_sumber"]
            rating["alergen_ids_normalisasi"] = rating["alergen_ids"]
            rating["alergen_normalisasi"] = ";".join(bc.ALLERGEN_CANONICAL[int(i)] for i in rating["alergen_ids_normalisasi"].split(";") if i)
            rating["pemetaan_makanan_terkonfirmasi"] = False
            rating["penanda"] = rating["penanda_penilaian"] = ""
        else:
            rating["id_makanan"] = rating["id_makanan_katalog"] = ""
        rating["status_pemeriksaan_gizi"] = "valid"
        rating["status_pemeriksaan_gizi"] = "valid"
        rating["pemetaan_makanan_terkonfirmasi"] = rating["status_pemetaan"] == "id_database_cocok_nama_porsi_perlu_review"
        if rating["status_pemetaan"] != "id_database_cocok_nama_porsi_perlu_review":
            rating["penanda"] = rating["penanda_penilaian"] = bc.PENANDA_PEMETAAN
    def convert(data):
        return [{key: "" if value is None else str(value) for key, value in r.items()} for r in data]
    return convert(responses), convert(ratings), report


def test_seleksi_rekonsiliasi_dan_penanda():
    responses, ratings, report = sumber()
    candidate, excluded, result = bc.buat_kandidat(responses, ratings, report, {})
    assert len(candidate) == 2 and len(excluded) == 4
    assert len(candidate) + len(excluded) == len(ratings)
    assert {(r["response_id"], r["nama_makanan_survei"]) for r in candidate}.isdisjoint(
        {(r["response_id"], r["nama_makanan_survei"]) for r in excluded})
    assert [r for r in candidate if r["status_eksploratif"] == "lolos_pemeriksaan_dasar"] == []
    assert all("timestamp" not in r for r in candidate)
    assert result["jumlah_pengecualian_unik"] == len(excluded)
    assert sum(v["penilaian"] for v in result["alasan_pengecualian"].values()) > len(excluded)
    assert all(r["id_makanan_katalog"] == "" for r in excluded if "Capcay" in r["nama_makanan_survei"])
    assert all(r["status_eksploratif"] == "perlu_tinjau" for r in candidate)
    assert result["jumlah_kandidat_eksploratif_perlu_tinjau"] == len(candidate)
    assert result["kelompok_jawaban_identik_dalam_kandidat"] == [["R001", "R003"]]
    assert result["rekonsiliasi_pasangan_rating"]["sama"]


def test_penahanan_rating_tidak_membuang_seluruh_kiriman():
    responses, ratings, report = sumber()
    ratings[0]["status"] = ratings[0]["status_pemeriksaan"] = "perlu_tinjau"
    ratings[0]["alasan_tahan"] = ratings[0]["alasan_penahanan"] = "tinjau_manual"
    report["status_penilaian"]["lolos_pemeriksaan_dasar"] -= 1
    report["status_penilaian"]["perlu_tinjau"] += 1
    candidate, excluded, _ = bc.buat_kandidat(responses, ratings, report, {})
    assert any(r["response_id"] == "R003" for r in candidate + excluded)
    assert any(r["response_id"] == "R001" and r["nama_makanan_survei"].startswith("1.") for r in candidate + excluded)


@pytest.mark.parametrize("error", ["kiriman", "duplikat", "profil", "laporan", "boolean"])
def test_sumber_tidak_konsisten_ditolak(error):
    responses, ratings, report = sumber()
    if error == "kiriman": ratings[0]["response_id"] = "R999"
    if error == "duplikat": ratings[1] = deepcopy(ratings[0])
    if error == "profil": ratings[0]["prioritas_id"] = "2"
    if error == "laporan": report["jumlah_penilaian"] += 1
    if error == "boolean": responses[0]["tahan_seluruh_kiriman"] = "bukan boolean"
    with pytest.raises(bc.SumberTidakValid):
        bc.buat_kandidat(responses, ratings, report, {})


def tulis(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_dry_run_dan_error_tidak_menimpa(tmp_path):
    responses, ratings, report = sumber()
    paths = [tmp_path / "responses.csv", tmp_path / "ratings.csv", tmp_path / "report.json"]
    tulis(paths[0], responses); tulis(paths[1], ratings)
    paths[2].write_text(json.dumps(report), encoding="utf-8")
    output = tmp_path / "output"; output.mkdir()
    (output / "survey_candidate.csv").write_text("hasil lama")
    args = ["--responses", str(paths[0]), "--ratings", str(paths[1]), "--validation-report", str(paths[2]), "--output-dir", str(output)]
    snapshot = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert bc.main(args + ["--dry-run"]) == 0
    assert snapshot == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report["jumlah_penilaian"] += 1
    paths[2].write_text(json.dumps(report), encoding="utf-8")
    assert bc.main(args) != 0
    assert (output / "survey_candidate.csv").read_text() == "hasil lama"


def ubah_status(ratings, report, item, status):
    lama = item["status"]
    report["status_penilaian"][lama] -= 1
    if not report["status_penilaian"][lama]:
        del report["status_penilaian"][lama]
    report["status_penilaian"][status] = report["status_penilaian"].get(status, 0) + 1
    item["status"] = item["status_pemeriksaan"] = status


@pytest.mark.parametrize("jenis", ["tanpa", "aktif", "tanpa_penanda", "penanda_saja"])
def test_konflik_kiriman_terdeteksi_dari_sumber(jenis):
    responses, ratings, report = sumber()
    r = responses[1]
    r["tahan_seluruh_kiriman"] = "False"
    if jenis == "aktif":
        r.update(status_alergi_asli="Ya, memiliki alergi", status_alergi_normalisasi="Ya, memiliki alergi", alergen_asli="", alergen_ids="", alergen_ids_normalisasi="", alergen_normalisasi="", penanda=bc.KONFLIK_DENGAN)
        report["distribusi_profil"][bc.PROFILE_NAMES["status_alergi_asli"]] = {"Tidak ada alergi": 2, "Ya, memiliki alergi": 1}
    if jenis == "aktif":
        for item in ratings:
            if item["response_id"] == "R002":
                item["status_alergi_normalisasi"] = r["status_alergi_normalisasi"]
    if jenis == "tanpa_penanda":
        r["penanda"] = ""
    elif jenis == "penanda_saja":
        r["alergen_asli"] = r["alergen_ids"] = ""
    for item in ratings:
        if item["response_id"] == "R002":
            item.update(status_alergi=r["status_alergi_normalisasi"], status_alergi_asli=r["status_alergi_asli"], status_alergi_normalisasi=r["status_alergi_normalisasi"], alergen_ids=r["alergen_ids"], alergen_asli=r["alergen_asli"], penanda_kiriman=r["penanda"])
            item["status_alergi_normalisasi"] = r["status_alergi_normalisasi"]
            ubah_status(ratings, report, item, "lolos_pemeriksaan_dasar")
            item["alasan_tahan"] = item["penanda"] = item["penanda_penilaian"] = ""
    with pytest.raises(bc.SumberTidakValid, match="response_id=R002, source_row=3.*konflik"):
        bc.buat_kandidat(responses, ratings, report, {})


def test_kiriman_ditahan_rating_lolos_ditolak():
    responses, ratings, report = sumber()
    item = next(r for r in ratings if r["response_id"] == "R002")
    ubah_status(ratings, report, item, "lolos_pemeriksaan_dasar")
    with pytest.raises(bc.SumberTidakValid, match="R002.*source_row=3.*makanan=.*tertahan"):
        bc.buat_kandidat(responses, ratings, report, {})


def rating_satu(responses, ratings, report):
    item = ratings[0]
    report["rating"][item["rating"]] -= 1
    if not report["rating"][item["rating"]]:
        del report["rating"][item["rating"]]
    report["rating"]["1"] = report["rating"].get("1", 0) + 1
    item["rating"] = "1"
    item["rating_asli"] = "1 = " + bc.LABEL["1"]
    ubah_status(ratings, report, item, "perlu_tinjau")
    item["penanda"] = item["penanda_penilaian"] = item["alasan_tahan"] = bc.RATING_SATU
    return item


@pytest.mark.parametrize("kerusakan", ["lolos", "penanda", "alasan"])
def test_rating_satu_tanpa_alergi_tidak_konsisten(kerusakan):
    responses, ratings, report = sumber()
    item = rating_satu(responses, ratings, report)
    if kerusakan == "lolos":
        ubah_status(ratings, report, item, "lolos_pemeriksaan_dasar")
        item["alasan_tahan"] = ""
    elif kerusakan == "penanda":
        item["penanda"] = item["penanda_penilaian"] = ""
    else:
        item["alasan_tahan"] = "alasan_lain"
    with pytest.raises(bc.SumberTidakValid, match="R001.*source_row=2.*makanan="):
        bc.buat_kandidat(responses, ratings, report, {})


def test_rating_satu_valid_hanya_menahan_penilaian_terkait():
    responses, ratings, report = sumber()
    item = rating_satu(responses, ratings, report)
    # Jadikan makanan kedua terkonfirmasi agar penilaian lain dapat dipilih.
    capcay_item = next(r for r in ratings if r["response_id"] == "R001" and "Capcay" in r["nama_makanan_survei"])
    capcay_item["id_makanan"] = capcay_item["id_makanan_katalog"] = ""
    capcay_item["status_pemetaan"] = "ditahan_varian_belum_jelas"
    capcay_item["pemetaan_makanan_terkonfirmasi"] = "False"
    capcay_item["penanda"] = capcay_item["penanda_penilaian"] = bc.PENANDA_PEMETAAN
    ratings[1]["penanda"] = ratings[1]["penanda_penilaian"] = ""
    candidate, excluded, _ = bc.buat_kandidat(responses, ratings, report, {})
    assert all(r["response_id"] != "R001" or r["rating"] != "1" for r in candidate)
    assert any(r["response_id"] == "R001" and r["rating"] == "1" for r in excluded)


@pytest.mark.parametrize("status,alasan", [("lolos_pemeriksaan_dasar", "sebab"), ("perlu_tinjau", "   ")])
def test_status_alasan_bertentangan(status, alasan):
    responses, ratings, report = sumber()
    item = ratings[0]
    if item["status"] != status:
        ubah_status(ratings, report, item, status)
    item["alasan_tahan"] = alasan
    with pytest.raises(bc.SumberTidakValid, match="R001.*source_row=2.*alasan_tahan"):
        bc.buat_kandidat(responses, ratings, report, {})


def test_penanda_informatif_tidak_menahan():
    responses, ratings, report = sumber()
    candidate, _, _ = bc.buat_kandidat(responses, ratings, report, {})
    assert any(r["response_id"] == "R001" and "rating_seragam" in r["penanda_kiriman"] for r in candidate)


def test_cli_konflik_tidak_menimpa(tmp_path):
    responses, ratings, report = sumber()
    responses[1]["tahan_seluruh_kiriman"] = "False"
    paths = [tmp_path / "responses.csv", tmp_path / "ratings.csv", tmp_path / "report.json"]
    tulis(paths[0], responses); tulis(paths[1], ratings)
    paths[2].write_text(json.dumps(report), encoding="utf-8")
    output = tmp_path / "output"; output.mkdir()
    existing = output / "survey_candidate.csv"; existing.write_text("hasil lama")
    args = ["--responses", str(paths[0]), "--ratings", str(paths[1]), "--validation-report", str(paths[2]), "--output-dir", str(output)]
    assert bc.main(args) != 0
    assert existing.read_text() == "hasil lama"
