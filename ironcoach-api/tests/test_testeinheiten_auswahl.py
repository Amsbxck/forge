"""Zonen kommen aus der Testwoche — und nur aus ihr.

Die Auswahl nahm alle Einheiten des Zeitraums und suchte darin das
schnellste 20-Minuten-Fenster. Bei einem Intervalltraining sind das die
härtesten zwanzig Minuten einer Einheit, die nie als gleichmässiger Test
gedacht war: Der Schwellenwert fällt zu hoch aus und gilt anschliessend
monatelang als Vorgabe.

Dafür gibt es die Testwoche. Sie schreibt in jeder Disziplin genau die
Einheit vor, aus der die Werte hervorgehen.
"""

from datetime import date, timedelta

import pytest

from models import AthleteProfile, PlannedSession, TrainingSession, WeeklyPlan
from services.benchmark import BENCHMARK_PHASE, _benchmark_sessions


@pytest.fixture(autouse=True)
def leer(db):
    for modell in (TrainingSession, PlannedSession, WeeklyPlan):
        db.query(modell).delete()
    db.commit()
    yield
    for modell in (TrainingSession, PlannedSession, WeeklyPlan):
        db.query(modell).delete()
    db.commit()


def _plan(db, phase):
    profil = db.query(AthleteProfile).first()
    montag = date.today() - timedelta(days=3)
    p = WeeklyPlan(user_id=profil.user_id, week_number=1, week_start=montag,
                   week_end=montag + timedelta(days=6), plan_phase=phase,
                   plan_content={"days": []}, plan_text="")
    db.add(p); db.commit()
    return p


def _einheit(db, plan=None, disziplin="run"):
    profil = db.query(AthleteProfile).first()
    geplant = None
    if plan is not None:
        geplant = PlannedSession(
            user_id=profil.user_id, plan_id=plan.id, week_number=1,
            planned_date=date.today() - timedelta(days=1),
            discipline=disziplin, training_type="threshold", duration_min=45,
        )
        db.add(geplant); db.commit()
    s = TrainingSession(
        user_id=profil.user_id, session_date=date.today() - timedelta(days=1),
        week_number=1, discipline=disziplin, duration_min=45,
        planned_session_id=geplant.id if geplant else None,
    )
    db.add(s); db.commit()
    return s


def test_nur_einheiten_aus_der_testwoche(db):
    testwoche = _plan(db, BENCHMARK_PHASE)
    normal = _plan(db, "Base 1")

    aus_test = _einheit(db, testwoche)
    _einheit(db, normal)          # geplante Einheit, aber keine Testeinheit
    _einheit(db, None)            # ganz ungeplant, etwa ein spontanes Intervall

    treffer = _benchmark_sessions(db, days=21)
    assert [s.id for s in treffer] == [aus_test.id]


def test_alle_disziplinen_der_testwoche_zaehlen(db):
    """Rad, Lauf und Schwimmen — die Testwoche schreibt für jede eine vor."""
    testwoche = _plan(db, BENCHMARK_PHASE)
    ids = {_einheit(db, testwoche, d).id for d in ("bike", "run", "swim")}
    assert {s.id for s in _benchmark_sessions(db, days=21)} == ids


def test_ohne_testwoche_wird_nichts_abgeleitet(client, db):
    _plan(db, "Base 1")
    _einheit(db, None)

    assert _benchmark_sessions(db, days=21) == []

    antwort = client.post("/api/benchmark/derive?apply=false").json()
    assert antwort["status"] == "no_sessions"
    assert "Testwoche" in antwort["hinweis"]


def test_alte_testeinheiten_fallen_aus_dem_zeitraum(db):
    testwoche = _plan(db, BENCHMARK_PHASE)
    alt = _einheit(db, testwoche)
    alt.session_date = date.today() - timedelta(days=60)
    db.commit()
    assert _benchmark_sessions(db, days=21) == []
