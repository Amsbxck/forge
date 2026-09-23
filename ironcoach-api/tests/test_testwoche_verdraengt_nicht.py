"""Die Testwoche liegt in der kommenden Woche und verdrängt nichts.

Zwei Wege führten hier früher zusammen, obwohl sie verschiedene Wochen
meinen: Die Anzeige wählte den Plan über die Planwochennummer, und die
Testwoche leitete ihre Nummer aus demselben `max(1, …)` ab. Vor dem Beginn
des Aufbaus ist diese Nummer für jedes Datum 1 — die Testwoche für den
kommenden Montag hätte dieselbe Nummer getragen wie der laufende Plan.

Folge wäre zweierlei gewesen: Die Testwoche wäre gar nicht angelegt worden
(der gleichnamige Plan galt als "schon vorhanden"), oder sie hätte in der
Anzeige den Plan der laufenden Woche ersetzt.
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


@pytest.fixture
def aufbau_beginnt_spaeter(db):
    """Der Fall, in dem die Wochennummern zusammenfallen.

    `zones_updated_at` wird geleert: Geprüft wird hier die Wochennummer,
    nicht die Frist bis zum nächsten Test. Mit frisch gemessenen Werten
    verweigert die Anlage zu Recht, und der Test prüfte dann etwas anderes,
    als sein Name behauptet.
    """
    profil = db.query(AthleteProfile).first()
    vorher = profil.zones_updated_at
    profil.plan_start_date = date.today() + timedelta(days=90)
    profil.zones_updated_at = None
    db.commit()
    yield profil
    profil.zones_updated_at = vorher
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


def test_anzeige_nimmt_die_laufende_woche_nicht_die_nummer(client, db, aufbau_beginnt_spaeter):
    montag, _ = kalenderwoche()
    laufend = _plan(db, montag, 1, "Grundlage")
    # Gleiche Nummer, andere Woche — vor dem Aufbaubeginn ist das der Normalfall.
    _plan(db, montag + timedelta(days=7), 1, "Benchmark")

    aktuell = client.get("/api/plan/current").json()
    assert aktuell["id"] == laufend["id"] if isinstance(laufend, dict) else aktuell["id"] == laufend.id
    assert aktuell["week_start"] == str(montag)
    assert aktuell["plan_phase"] == "Grundlage", "die Testwoche der Folgewoche darf nicht einspringen"


def test_testwoche_wird_trotz_gleicher_nummer_angelegt(client, db, aufbau_beginnt_spaeter):
    """Vorher galt ein Plan gleicher Nummer als 'schon vorhanden'."""
    from services.benchmark import create_benchmark_plan
    from services.benchmark_timing import naechster_montag

    montag, _ = kalenderwoche()
    _plan(db, montag, 1, "Grundlage")

    plan, neu = create_benchmark_plan(db)
    assert neu is True, "die Testwoche muss angelegt werden"
    assert plan.week_start == naechster_montag(), "und zwar für die kommende Woche"
    assert plan.week_start > montag
