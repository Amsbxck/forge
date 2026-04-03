from datetime import date


def test_create_hrv(client):
    resp = client.post("/api/hrv", json={
        "measured_at": "2026-03-27",
        "rmssd": 88.5,
        "readiness_score": 72,
        "notes": "Gut geschlafen",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["rmssd"] == 88.5
    assert data["hrv_status"] == "green"


def test_create_hrv_yellow(client):
    resp = client.post("/api/hrv", json={
        "measured_at": "2026-03-26",
        "rmssd": 78.0,
    })
    assert resp.status_code == 200
    assert resp.json()["hrv_status"] == "yellow"


def test_create_hrv_red(client):
    resp = client.post("/api/hrv", json={
        "measured_at": "2026-03-25",
        "rmssd": 65.0,
    })
    assert resp.status_code == 200
    assert resp.json()["hrv_status"] == "red"


def test_list_hrv(client):
    resp = client.get("/api/hrv")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_latest_hrv(client):
    resp = client.get("/api/hrv/latest")
    assert resp.status_code == 200
    assert "rmssd" in resp.json()


def test_hrv_invalid_rmssd(client):
    resp = client.post("/api/hrv", json={"measured_at": "2026-03-27", "rmssd": -5})
    assert resp.status_code == 422
