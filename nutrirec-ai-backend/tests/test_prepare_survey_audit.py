from openpyxl import Workbook
import pytest

from scripts import prepare_survey as ps


def row(**changes):
    data = {"source_row": 2, ps.REQUIRED_COLUMNS[0]: "waktu",
            ps.REQUIRED_COLUMNS[1]: "Rendah (< 300 kkal)",
            ps.REQUIRED_COLUMNS[2]: "Protein tinggi",
            ps.REQUIRED_COLUMNS[3]: "Tidak ada alergi",
            ps.REQUIRED_COLUMNS[4]: "",
            "1. Bihun Goreng Sayur": "3 = Sesuai (hampir sesuai target)"}
    data.update(changes)
    return data


@pytest.mark.parametrize("value", ["", "tidak dikenal"])
def test_profil_invalid_ditahan(value):
    r = row(**{ps.REQUIRED_COLUMNS[1]: value})
    responses, ratings, report = ps.siapkan_data([r], {"Bihun Goreng Sayur": 1})
    assert responses[0]["tahan_seluruh_kiriman"]
    assert ratings[0]["status"] == "perlu_tinjau"
    assert report["kesalahan"][0]["source_row"] == 2


def test_alergen_tidak_dikenal_dilaporkan():
    r = row(**{ps.REQUIRED_COLUMNS[4]: "Bahan misterius"})
    _, ratings, report = ps.siapkan_data([r], {"Bihun Goreng Sayur": 1})
    assert "alergen_tidak_dikenal" in ratings[0]["penanda_kiriman"]
    assert report["kesalahan"][0]["token"] == "Bahan misterius"
    assert ps.parse_alergen("Telur, Kacang-kacangan (tauge, kacang tanah, buncis)")[0] == [1, 8]


def test_mapping_tidak_ditemukan_dan_capcay():
    r = row(**{"20. Capcay Kuah (Ayam)": "3 = Sesuai (hampir sesuai target)"})
    _, ratings, report = ps.siapkan_data([r], {})
    assert all(not x["id_makanan"] and not x["pemetaan_makanan_terkonfirmasi"] for x in ratings)
    assert len(report["pemetaan_makanan_belum_dikonfirmasi"]) == 2
    assert report["jumlah_kiriman_terdampak_unik"] == 1


def dataset(path, rows, headers=None):
    wb = Workbook(); ws = wb.active; ws.title = "Dataset"
    if headers is None:
        headers = complete_dataset_headers()
    ws.append(headers)
    for item in rows:
        ws.append(item)
    wb.save(path)

def complete_dataset_headers():
    return ["NAMA MAKANAN", "NO", "KALORI (kkal)", "KARBO (g)", "LEMAK (g)", "PROTEIN (g)", "PORSI", "KELOMPOK KALORI", "% ENERGI PROTEIN", "% ENERGI KARBO", "% ENERGI LEMAK", "PRIORITAS NUTRISI", "ALERGEN TERCATAT", "SUMBER DATA", "STATUS ALERGEN", "CATATAN VERIFIKASI"]


def test_dataset_header_berpindah_dan_duplikat(tmp_path):
    path = tmp_path / "foods.xlsx"
    headers = complete_dataset_headers()
    def full(name, food_id):
        return [name, food_id, 300, 10, 5, 10, "1 porsi", "Sedang", "", "", "", "", "", "sumber", "Belum diverifikasi", ""]
    dataset(path, [full("A", 7), full("a", 7), full("B", None)], headers)
    mapping, errors = ps.baca_dataset_detail(str(path))
    assert mapping["A"]["id_sumber"] == 7
    assert len(errors) >= 2


@pytest.mark.parametrize("kind", ["missing", "extra", "duplicate", "ambiguous"])
def test_struktur_survei_ditolak(tmp_path, kind):
    wb = Workbook(); ws = wb.active; ws.title = ps.SHEET_SURVEI
    names = [f"{i}. {n}" for i, n in enumerate(ps.MAPELANGGAN_MAKANAN, 1)]
    if kind == "missing": names.pop()
    if kind == "extra": names.append("21. Makanan asing")
    if kind == "duplicate": names.append(names[0])
    if kind == "ambiguous": names.append("99. BIHUN GORENG SAYUR")
    ws.append(ps.REQUIRED_COLUMNS + names)
    path = tmp_path / "survey.xlsx"; wb.save(path)
    assert ps.baca_survei(str(path))[1]


def test_struktur_error_dan_dry_run_tidak_menimpa(tmp_path):
    wb = Workbook(); wb.active.title = ps.SHEET_SURVEI; wb.active.append(["Timestamp"])
    survey = tmp_path / "survey.xlsx"; wb.save(survey)
    foods = tmp_path / "foods.xlsx"; dataset(foods, [["A", 1]])
    out = tmp_path / "out"; out.mkdir()
    existing = out / "survey_responses.csv"; existing.write_text("jangan diubah")
    args = ["--file", str(survey), "--foods", str(foods), "--output-dir", str(out)]
    assert ps.main(args) != 0
    assert ps.main(args + ["--dry-run"]) != 0
    assert existing.read_text() == "jangan diubah"


def buat_survei_valid(path, header_fn=lambda i, name: f"{i}. {name}"):
    wb = Workbook()
    ws = wb.active
    ws.title = ps.SHEET_SURVEI
    names = list(ps.MAPELANGGAN_MAKANAN)
    ws.append(ps.REQUIRED_COLUMNS + [header_fn(i, n) for i, n in enumerate(names, 1)])
    # Rating kosong tetap merupakan satu penilaian.
    ws.append(["waktu", "Rendah (< 300 kkal)", "Protein tinggi", "Tidak ada alergi", None]
              + [None] + ["3 = Sesuai (hampir sesuai target)"] * 19)
    wb.save(path)


def test_header_bernomor_tanpa_nomor_dan_normalisasi(tmp_path):
    paths = [tmp_path / f"{i}.xlsx" for i in range(3)]
    buat_survei_valid(paths[0])
    buat_survei_valid(paths[1], lambda i, name: name)
    buat_survei_valid(paths[2], lambda i, name: "  " + "  ".join(name.upper().split()) + "  ")
    dataset_ids = {name: i for i, name in enumerate(ps.MAPELANGGAN_MAKANAN.values(), 1)}
    hasil = []
    for path in paths:
        rows, errors = ps.baca_survei(str(path))
        assert not errors
        _, ratings, report = ps.siapkan_data(rows, dataset_ids)
        assert len(ratings) == 20
        assert sum(r["status"] == "kosong" for r in ratings) == 1
        by_id = {ps.kunci_header_makanan(r["nama_makanan_survei"]): (r["id_makanan"], r["rating"]) for r in ratings}
        assert by_id["capcay kuah (ayam)"][0] == ""
        assert ratings[0]["nama_makanan_survei"] in rows[0]
        assert "status_pemetaan" in ratings[0]
        hasil.append(by_id)
    assert hasil[0] == hasil[1] == hasil[2]


def test_header_nama_dan_nomor_duplikat(tmp_path):
    path = tmp_path / "survey.xlsx"
    buat_survei_valid(path)
    from openpyxl import load_workbook
    wb = load_workbook(path)
    wb.active.cell(1, wb.active.max_column + 1, "BIHUN  GORENG SAYUR")
    wb.save(path)
    assert any("duplikat" in e for e in ps.baca_survei(str(path))[1])


@pytest.mark.parametrize("column", ps.REQUIRED_COLUMNS[1:4])
@pytest.mark.parametrize("value", ["", "nilai asing"])
def test_semua_profil_wajib_ditahan(column, value):
    response, ratings, report = ps.siapkan_data([row(**{column: value})], {"Bihun Goreng Sayur": 1})
    assert response[0]["tahan_seluruh_kiriman"]
    assert all(r["status"] == "perlu_tinjau" for r in ratings)
    assert any(e["kolom"] == column and e["jenis"] == ("kosong" if not value else "tidak_dikenal") for e in report["kesalahan"])


def test_alasan_dinamis_dan_tahap_persiapan():
    _, _, clean = ps.siapkan_data([row()], {"Bihun Goreng Sayur": 1})
    assert clean["siap_ml"] is False
    assert any("persiapan" in a for a in clean["alasan_belum_siap_ml"])
    assert not any(any(k in a.lower() for k in ("capcay", "seimbang", "konflik")) for a in clean["alasan_belum_siap_ml"])
    _, _, conflict = ps.siapkan_data([row(**{ps.REQUIRED_COLUMNS[4]: "Telur"})], {"Bihun Goreng Sayur": 1})
    assert any("Konflik" in a for a in conflict["alasan_belum_siap_ml"])
    _, _, balanced = ps.siapkan_data([row(**{ps.REQUIRED_COLUMNS[2]: "Seimbang (tidak ada prioritas khusus)"})], {"Bihun Goreng Sayur": 1})
    assert any("Seimbang" in a for a in balanced["alasan_belum_siap_ml"])


def test_dry_run_workbook_valid_tidak_mengubah_file(tmp_path):
    survey = tmp_path / "survey.xlsx"
    foods = tmp_path / "foods.xlsx"
    buat_survei_valid(survey)
    dataset(foods, [[n, i, 300, 10, 5, 10, "1 porsi", "Sedang", "", "", "", "", "", "sumber", "Belum diverifikasi", ""] for i, n in enumerate(ps.MAPELANGGAN_MAKANAN.values(), 1)], complete_dataset_headers())
    out = tmp_path / "output"
    out.mkdir()
    (out / "survey_responses.csv").write_bytes(b"hasil lama")
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert ps.main(["--file", str(survey), "--foods", str(foods), "--output-dir", str(out), "--dry-run"]) == 0
    after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("invalid_id", [-1, 1.5, "abc", 1])
def test_dataset_id_invalid_atau_duplikat(tmp_path, invalid_id):
    path = tmp_path / "foods.xlsx"
    dataset(path, [["A", 1], ["B", invalid_id]])
    assert any("ID" in e and "baris 3" in e for e in ps.baca_dataset(str(path))[1])


def test_dataset_nama_duplikat_id_berbeda(tmp_path):
    path = tmp_path / "foods.xlsx"
    dataset(path, [["A", 1], [" a ", 2]])
    assert any("nama" in e and "baris 3" in e for e in ps.baca_dataset(str(path))[1])
