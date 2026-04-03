from unittest.mock import AsyncMock, patch, MagicMock


def test_webhook_verify(client):
    resp = client.get("/webhook", params={
        "hub.verify_token": "test_token",
        "hub.challenge": "abc123",
    })
    assert resp.status_code == 200
    assert resp.json()["hub.challenge"] == "abc123"


def test_webhook_verify_wrong_token(client):
    resp = client.get("/webhook", params={
        "hub.verify_token": "wrong_token",
        "hub.challenge": "abc123",
    })
    assert resp.status_code == 403


def test_webhook_receive_activity(client):
    payload = {
        "object_type": "activity",
        "aspect_type": "create",
        "object_id": 999999,
        "owner_id": 12345,
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_receive_non_activity(client):
    payload = {
        "object_type": "athlete",
        "aspect_type": "update",
        "object_id": 12345,
        "owner_id": 12345,
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200


def test_strava_status_not_connected(client):
    resp = client.get("/api/strava/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] == False


def test_strava_auth_url(client):
    resp = client.get("/api/strava/auth")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "strava.com" in data["auth_url"]
