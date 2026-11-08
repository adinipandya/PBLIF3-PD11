"""Pengujian riwayat rekomendasi anonim berbasis sesi kiosk."""
from fastapi.testclient import TestClient

from app.models.makanan import Makanan, InformasiGizi

SESSION_A = "11111111-1111-4111-8111-111111111111"
SESSION_B = "22222222-2222-4222-8222-222222222222"


def seed_food(db_session):
    db_session.add(
        Makanan(
            id_makanan=901,
            nama_makanan="Menu Uji Riwayat",
            deskripsi_porsi="1 porsi",
            sumber_data="sumber pengujian",
            kelompok_kalori="Sedang",
            versi_dataset="test",
        )
    )
    db_session.add(
        InformasiGizi(
            id_makanan=901,
            kalori=400,
            protein=20,
            karbohidrat=40,
            lemak=10,
        )
    )
    db_session.flush()


def request_recommendation(client: TestClient, session_id: str):
    return client.post(
        "/api/v1/recommendations/content-based",
        headers={"X-Session-ID": session_id},
        json={
            "target_kalori_id": 2,
            "prioritas_id": 1,
            "status_alergi": False,
            "alergen_ids": [],
        },
    )


def test_recommendation_saved_to_anonymous_session(client, db_session, seed_referensi):
    seed_food(db_session)
    response = request_recommendation(client, SESSION_A)
    assert response.status_code == 200

    history = client.get(
        "/api/v1/recommendation-history",
        params={"session_id": SESSION_A},
    )
    assert history.status_code == 200
    data = history.json()
    assert data["session_id"] == SESSION_A
    assert data["total"] == 1
    assert data["items"][0]["permintaan"]["target_kalori_id"] == 2
    assert data["items"][0]["hasil"]["jumlah_kandidat"] == 1


def test_history_is_isolated_between_sessions(client, db_session, seed_referensi):
    seed_food(db_session)
    assert request_recommendation(client, SESSION_A).status_code == 200

    response = client.get(
        "/api/v1/recommendation-history",
        params={"session_id": SESSION_B},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_history_can_be_cleared_for_current_session(client, db_session, seed_referensi):
    seed_food(db_session)
    assert request_recommendation(client, SESSION_A).status_code == 200

    deleted = client.delete(
        "/api/v1/recommendation-history",
        params={"session_id": SESSION_A},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1

    history = client.get(
        "/api/v1/recommendation-history",
        params={"session_id": SESSION_A},
    )
    assert history.json()["total"] == 0


def test_history_limit_is_bounded(client):
    response = client.get(
        "/api/v1/recommendation-history",
        params={"session_id": SESSION_A, "limit": 1000},
    )
    assert response.status_code == 422


def test_recommendation_without_session_header_still_works(client, db_session, seed_referensi):
    seed_food(db_session)
    response = client.post(
        "/api/v1/recommendations/content-based",
        json={
            "target_kalori_id": 2,
            "prioritas_id": 1,
            "status_alergi": False,
            "alergen_ids": [],
        },
    )
    assert response.status_code == 200
