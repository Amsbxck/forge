"""Die Testwoche braucht ein Saisonziel.

Die Testeinheiten richten sich nach der Sportart des Ziels. Ohne Ziel galt
Triathlon: Ein Läufer, der vor dem Anlegen seines Ziels auf „Testwoche planen"
drückte, bekam FTP- und CSS-Test, die nie in eine Vorgabe eingehen — und
konnte die passende Testwoche wegen der 90-Tage-Sperre erst drei Monate
später buchen.
"""

from datetime import datetime

import pytest

from tests.test_pruefung_adversarial import _frei, _kopf, auth_an, nutzer_fabrik, saisonziel  # noqa: F401


def test_ohne_ziel_keine_testwoche(client, db, nutzer_fabrik, auth_an):
    from models import WeeklyPlan

    u = nutzer_fabrik(email_verified_at=datetime.utcnow())
    antwort = client.post("/api/benchmark/plan", headers=_kopf(u))
    assert antwort.status_code == 409, antwort.text
    detail = antwort.json()["detail"]
    assert detail["ohne_ziel"] is True
    assert "Saisonziel" in detail["gruende"][0]
    assert db.query(WeeklyPlan).filter(WeeklyPlan.user_id == u.id).count() == 0


def test_timing_meldet_ohne_ziel(client, nutzer_fabrik, auth_an):
    u = nutzer_fabrik(email_verified_at=datetime.utcnow())
    lage = client.get("/api/benchmark/timing", headers=_kopf(u)).json()
    assert lage["moeglich"] is False
    assert lage["ohne_ziel"] is True


def test_laufziel_ergibt_nur_lauftests(client, db, nutzer_fabrik, auth_an, monkeypatch):
    _frei(monkeypatch)
    u = nutzer_fabrik(email_verified_at=datetime.utcnow())
    saisonziel(db, u, sport="running", distanz="half_marathon")

    lage = client.get("/api/benchmark/timing", headers=_kopf(u)).json()
    assert lage["ohne_ziel"] is False

    antwort = client.post("/api/benchmark/plan", headers=_kopf(u))
    assert antwort.status_code == 200, antwort.text

    from models import WeeklyPlan
    plan = db.query(WeeklyPlan).filter(WeeklyPlan.id == antwort.json()["plan_id"]).one()
    arten = {t["session_type"] for t in plan.plan_content["days"]}
    assert "bike" not in arten and "swim" not in arten, arten
    assert "run" in arten
