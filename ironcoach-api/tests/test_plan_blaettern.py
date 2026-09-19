"""Blättern zwischen Kalenderwochen, nicht zwischen Wochennummern.

Ein Plan für die kommende Woche war bis zum Wochenwechsel unsichtbar. Die
Navigation lief über die Planwochennummer, und die entsteht aus
`max(1, …)`: Vor dem Beginn des Aufbaus trägt jedes Datum die 1. "Eine
Woche vor" führte dort auf Nummer 2, für die es nie einen Plan gibt —
während die kommende Woche unter derselben 1 lag wie die laufende.
"""

from datetime import date, timedelta

import pytest

from core.wochen import kalenderwoche
from models import AthleteProfile, WeeklyPlan


@pytest.fixture(autouse=True)
def leere_plaene(db):
    db.query(WeeklyPlan).delete()
    db.commit()
    yield
    db.query(WeeklyPlan).delete()
    db.commit()


def _plan(db, montag, nummer, phase):
    profil = db.query(AthleteProfile).first()
    p = WeeklyPlan(
        user_id=profil.user_id, week_number=nummer,
        week_start=montag, week_end=montag + timedelta(days=6),
        plan_phase=phase, plan_content={"days": []}, plan_text="",
    )
    db.add(p); db.commit()
    return p


def test_kommende_woche_ist_erreichbar_trotz_gleicher_nummer(client, db):
    montag, _ = kalenderwoche()
    _plan(db, montag, 1, "Grundlage")
    _plan(db, montag + timedelta(days=7), 1, "Benchmark")

    laufend = client.get("/api/plan/current").json()
    kommend = client.get(f"/api/plan/am/{montag + timedelta(days=7)}").json()

    assert laufend["plan_phase"] == "Grundlage"
    assert kommend["plan_phase"] == "Benchmark"
    assert kommend["week_start"] == str(montag + timedelta(days=7))


def test_beliebiger_wochentag_findet_dieselbe_woche(client, db):
    """Die Adresse darf nicht davon abhängen, welchen Tag jemand schickt."""
    montag, _ = kalenderwoche()
    _plan(db, montag, 1, "Grundlage")

    for versatz in range(7):
        antwort = client.get(f"/api/plan/am/{montag + timedelta(days=versatz)}")
        assert antwort.status_code == 200
        assert antwort.json()["week_start"] == str(montag)


def test_leere_woche_meldet_404(client, db):
    montag, _ = kalenderwoche()
    antwort = client.get(f"/api/plan/am/{montag + timedelta(days=7)}")
    assert antwort.status_code == 404


def test_geplante_einheiten_folgen_derselben_adresse(client, db):
    montag, _ = kalenderwoche()
    kommend = _plan(db, montag + timedelta(days=7), 1, "Benchmark")
    _plan(db, montag, 1, "Grundlage")

    from models import PlannedSession
    db.add(PlannedSession(
        user_id=kommend.user_id, plan_id=kommend.id, week_number=1,
        planned_date=montag + timedelta(days=8), discipline="bike",
        training_type="threshold", duration_min=60,
    ))
    db.commit()

    einheiten = client.get(f"/api/planned/am/{montag + timedelta(days=7)}").json()
    assert len(einheiten) == 1
    assert einheiten[0]["discipline"] == "bike"
    # Die laufende Woche bleibt davon unberührt.
    assert client.get(f"/api/planned/am/{montag}").json() == []
