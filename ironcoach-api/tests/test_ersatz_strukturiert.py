"""Ersatzeinheit mit Sportart, Dauer und Intensität.

Vorher trug ein Ersatz nur einen Satz und optional eine Dauer. Für den Menschen
genügt das, für die Planung nicht: Aus "war schwimmen" lässt sich nicht ablesen,
ob das eine Stunde locker oder zwanzig Minuten hart war — und beides bedeutet
für die Folgewoche etwas anderes.
"""

from datetime import date, timedelta

import pytest

from models import PlannedSession, User, WeeklyPlan

MONTAG = date(2026, 11, 2)


@pytest.fixture
def geplant(db):
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=50, week_start=MONTAG,
                      week_end=MONTAG + timedelta(days=6), plan_phase="Build",
                      plan_content={"days": [1]})
    db.add(plan); db.commit()
    p = PlannedSession(user_id=nutzer.id, plan_id=plan.id, week_number=50,
                       planned_date=MONTAG, day_index=0, day_name="Montag",
                       discipline="bike", duration_min=90, training_type="sweet_spot")
    db.add(p); db.commit()
    yield p
    db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.id == plan.id).delete()
    db.commit()


def test_sportart_dauer_und_intensitaet_werden_gespeichert(client, geplant, db):
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "", "discipline": "swim", "duration_min": 45, "intensity": "base",
    })
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["status"] == "replaced"
    assert daten["replacement_discipline"] == "swim"
    assert daten["replacement_intensity"] == "base"
    assert daten["replacement_min"] == 45


def test_ohne_notiz_entsteht_eine_lesbare_zeile(client, geplant):
    """Niemand soll zweimal dasselbe eintragen — im Plan steht trotzdem ein
    Satz statt drei Schlüsselwörter."""
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "", "discipline": "swim", "duration_min": 45, "intensity": "base",
    })
    text = antwort.json()["replacement"]
    assert "Schwimmen" in text
    assert "45 min" in text


def test_eigene_notiz_bleibt_stehen(client, geplant):
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "mit Freunden im See", "discipline": "swim", "duration_min": 40,
    })
    assert antwort.json()["replacement"] == "mit Freunden im See"


def test_nur_notiz_geht_weiter(client, geplant):
    """Der alte Weg muss bleiben: Was jemand tut, lässt sich nicht immer
    aufzählen."""
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "Umzug geholfen", "duration_min": 180,
    })
    assert antwort.status_code == 200
    assert antwort.json()["replacement_discipline"] is None


def test_leere_angabe_wird_abgewiesen(client, geplant):
    """Ein Ersatz ohne jede Angabe ist für die Planung ein Ausfall, sähe aber
    besser aus."""
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={"text": "  "})
    assert antwort.status_code == 422


def test_unbekannte_sportart_wird_abgewiesen(client, geplant):
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "", "discipline": "quidditch",
    })
    assert antwort.status_code == 422
    assert "Sportart" in antwort.json()["detail"]


def test_unbekannte_intensitaet_wird_abgewiesen(client, geplant):
    """Die vier Stufen sind dieselben wie überall in der Anwendung — "tempo"
    heisst hier `sweet_spot`."""
    antwort = client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "", "discipline": "run", "intensity": "tempo",
    })
    assert antwort.status_code == 422
    assert "sweet_spot" in antwort.json()["detail"]


def test_zuruecknehmen_leert_auch_die_neuen_felder(client, geplant, db):
    client.post(f"/api/planned/{geplant.id}/replacement", json={
        "text": "", "discipline": "swim", "duration_min": 45, "intensity": "base",
    })
    antwort = client.delete(f"/api/planned/{geplant.id}/replacement")
    daten = antwort.json()
    assert daten["status"] == "planned"
    assert daten["replacement_discipline"] is None
    assert daten["replacement_intensity"] is None
