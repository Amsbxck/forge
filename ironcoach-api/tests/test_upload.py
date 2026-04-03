import io
import os
import struct
import pytest


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_invalid_extension(client):
    resp = client.post(
        "/api/upload",
        files={"file": ("workout.txt", b"not a fit file", "text/plain")},
    )
    assert resp.status_code == 400
    assert "fit" in resp.json()["detail"].lower() or "gpx" in resp.json()["detail"].lower()


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "0")
    from core import config
    config.settings.MAX_UPLOAD_SIZE_MB = 0
    resp = client.post(
        "/api/upload",
        files={"file": ("workout.fit", b"x" * 10, "application/octet-stream")},
    )
    assert resp.status_code in (413, 422)
    config.settings.MAX_UPLOAD_SIZE_MB = 50


def test_metrics_week(client):
    resp = client.get("/api/metrics/week")
    assert resp.status_code == 200
    data = resp.json()
    assert "week_number" in data
    assert "total_tss" in data


def test_metrics_trends(client):
    resp = client.get("/api/metrics/trends")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_profile(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ftp_watts"] == 238
    assert data["max_hr"] == 212
