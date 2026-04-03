from unittest.mock import AsyncMock, patch


MOCK_PLAN = {
    "week": 15,
    "phase": "Base 2",
    "coaching_comment": "Gute Woche, weiter so!",
    "adjustments": ["HRV grün – volle Intensität"],
    "days": [
        {"day": "Montag", "date": "2026-03-30", "session_type": "rest", "duration_min": 0, "details": {}, "notes": "Ruhetag"},
        {"day": "Dienstag", "date": "2026-03-31", "session_type": "bike", "duration_min": 60, "details": {"watts": 200}, "notes": "Z2 Ausdauer"},
        {"day": "Mittwoch", "date": "2026-04-01", "session_type": "run", "duration_min": 30, "details": {}, "notes": "Lockeres Laufen"},
        {"day": "Donnerstag", "date": "2026-04-02", "session_type": "swim", "duration_min": 45, "details": {}, "notes": "Schwimmen"},
        {"day": "Freitag", "date": "2026-04-03", "session_type": "gym", "duration_min": 45, "details": {}, "notes": "Krafttraining"},
        {"day": "Samstag", "date": "2026-04-04", "session_type": "bike", "duration_min": 90, "details": {"watts": 190}, "notes": "Langer Ritt"},
        {"day": "Sonntag", "date": "2026-04-05", "session_type": "run", "duration_min": 45, "details": {}, "notes": "Langer Lauf"},
    ],
}


def test_no_plan_yet(client):
    resp = client.get("/api/plan/current")
    assert resp.status_code == 404


def test_generate_plan(client):
    with patch(
        "services.claude_service.generate_weekly_plan",
        new=AsyncMock(return_value=MOCK_PLAN),
    ):
        resp = client.get("/api/plan/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["week_number"] == 15
    assert data["plan_phase"] == "Base 2"
    assert len(data["plan_content"]["days"]) == 7


def test_current_plan_after_generate(client):
    with patch(
        "services.claude_service.generate_weekly_plan",
        new=AsyncMock(return_value=MOCK_PLAN),
    ):
        client.get("/api/plan/generate")
    resp = client.get("/api/plan/current")
    assert resp.status_code == 200
    assert "plan_content" in resp.json()


def test_history_plans(client):
    resp = client.get("/api/history/plans")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
