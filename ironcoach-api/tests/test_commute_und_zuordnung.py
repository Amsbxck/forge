"""Arbeitsweg und geplante Einheit am selben Tag.

Der Fall: Die Fahrt zur Arbeit wird mit der Uhr getrackt, abends steht die
eigentliche Radeinheit auf dem Plan. Die Zuordnung vergibt 0.5 Punkte für
dieselbe Sportart und 0.3 für denselben Tag, die Schwelle liegt bei 0.5 — eine
20-Minuten-Fahrt erreichte damit 0.8 und galt als die geplante Ausfahrt über
90 Minuten. Der Tag wurde grün, und die Belastbarkeitsrechnung meldete einen
Rückstand, der den Coach das Volumen senken lässt.

Löschte man den Arbeitsweg, blieb der Tag grün und die abends absolvierte
Einheit hing daneben: `matched_session_id` zeigte weiter auf die gelöschte.
"""

from datetime import date, datetime

import pytest

from models import PlannedSession, TrainingSession, User, WeeklyPlan
from services.classification import classify_session, find_best_planned, score_match
from services.planned_link import release_planned

TAG = date(2026, 10, 7)


@pytest.fixture
def vorgabe(db):
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=40, week_start=date(2026, 10, 5),
                      week_end=date(2026, 10, 11), plan_phase="Build", plan_content={"days": [1]})
    db.add(plan)
    db.commit()
    p = PlannedSession(user_id=nutzer.id, plan_id=plan.id, week_number=40,
                       planned_date=TAG, day_index=2, day_name="Mittwoch",
                       discipline="bike", duration_min=90, training_type="sweet_spot")
    db.add(p)
    db.commit()
    yield p
    db.query(TrainingSession).filter(TrainingSession.session_date == TAG).delete()
    db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.id == plan.id).delete()
    db.commit()


def _fahrt(db, minuten, commute=False):
    nutzer = db.query(User).first()
    s = TrainingSession(user_id=nutzer.id, session_date=TAG, discipline="bike",
                        duration_min=minuten, week_number=40, is_commute=commute)
    db.add(s)
    db.commit()
    return s


# --- Ohne Kennzeichen würde der Arbeitsweg passen ----------------------------

def test_der_punktwert_allein_haette_gereicht(vorgabe, db):
    """Belegt, warum das Kennzeichen nötig ist — nicht die Dauer rettet es."""
    kurz = _fahrt(db, 20)
    assert score_match(vorgabe, kurz) >= 0.5, "dieselbe Sportart am selben Tag genügt"


def test_arbeitsweg_wird_nicht_zugeordnet(vorgabe, db):
    weg = _fahrt(db, 20, commute=True)
    treffer, punkte = find_best_planned(db, weg)
    assert treffer is None
    assert punkte == 0.0


def test_arbeitsweg_laesst_den_tag_grau(vorgabe, db):
    """Er zählt in die Last, aber er erfüllt keine Vorgabe."""
    weg = _fahrt(db, 20, commute=True)
    classify_session(db, weg)
    db.refresh(vorgabe)
    assert vorgabe.status == "planned"
    assert vorgabe.matched_session_id is None
    assert weg.planned_session_id is None


def test_die_eigentliche_einheit_wird_zugeordnet(vorgabe, db):
    """Gegenprobe: Ohne Kennzeichen greift die Zuordnung wie bisher."""
    echt = _fahrt(db, 88)
    classify_session(db, echt)
    db.refresh(vorgabe)
    assert vorgabe.status == "completed"
    assert vorgabe.matched_session_id == echt.id


# --- Löschen gibt die Vorgabe frei ------------------------------------------

def test_loeschen_gibt_die_vorgabe_frei(vorgabe, db):
    echt = _fahrt(db, 88)
    classify_session(db, echt)
    assert vorgabe.status == "completed"

    echt.deleted_at = datetime.utcnow()
    ergebnis = release_planned(db, echt)

    db.refresh(vorgabe)
    assert ergebnis["status"] == "freigegeben"
    assert vorgabe.status == "planned", "sonst bleibt der Tag grün ohne Einheit"
    assert vorgabe.matched_session_id is None


def test_nach_dem_loeschen_greift_die_spaetere_einheit(vorgabe, db):
    """Der eigentliche Ablauf: morgens getrackt und gelöscht, abends gefahren.

    Vorher behielt `matched_session_id` die gelöschte Einheit — die Regel "die
    mit der kleineren id gewinnt" ist für Bricks gedacht und wirkte hier gegen
    den Athleten.
    """
    morgens = _fahrt(db, 20)
    classify_session(db, morgens)
    assert vorgabe.matched_session_id == morgens.id

    morgens.deleted_at = datetime.utcnow()
    release_planned(db, morgens)

    abends = _fahrt(db, 92)
    classify_session(db, abends)

    db.refresh(vorgabe)
    assert vorgabe.status == "completed"
    assert vorgabe.matched_session_id == abends.id
    assert abends.id > morgens.id, "die spätere hat die höhere id — genau der alte Stolperstein"


def test_brick_bleibt_erfuellt_wenn_eine_haelfte_geht(db):
    """Zwei Einheiten an einer Vorgabe: Nicht blind zurücksetzen."""
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=41, week_start=date(2026, 10, 12),
                      week_end=date(2026, 10, 18), plan_phase="Build", plan_content={"days": [1]})
    db.add(plan); db.commit()
    p = PlannedSession(user_id=nutzer.id, plan_id=plan.id, week_number=41,
                       planned_date=date(2026, 10, 17), day_index=5, day_name="Samstag",
                       discipline="brick", duration_min=150, training_type="brick",
                       status="completed")
    db.add(p); db.commit()

    teile = []
    for disz, minuten in (("bike", 120), ("run", 30)):
        s = TrainingSession(user_id=nutzer.id, session_date=date(2026, 10, 17),
                            discipline=disz, duration_min=minuten, week_number=41,
                            planned_session_id=p.id)
        db.add(s); db.commit()
        teile.append(s)
    p.matched_session_id = teile[0].id
    db.commit()

    teile[0].deleted_at = datetime.utcnow()
    ergebnis = release_planned(db, teile[0])

    db.refresh(p)
    assert ergebnis["status"] == "bleibt_erfuellt"
    assert p.status == "completed"
    assert p.matched_session_id == teile[1].id, "Rückverweis wandert auf die verbleibende Hälfte"

    db.query(TrainingSession).filter(TrainingSession.week_number == 41).delete()
    db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.id == plan.id).delete()
    db.commit()


# --- Über die Schnittstelle --------------------------------------------------

def test_endpunkt_gibt_die_vorgabe_frei_und_meldet_es(client, vorgabe, db):
    echt = _fahrt(db, 88)
    classify_session(db, echt)

    antwort = client.delete(f"/api/history/sessions/{echt.id}")
    assert antwort.status_code == 200
    assert antwort.json()["vorgabe"]["status"] == "freigegeben"

    db.expire_all()
    db.refresh(vorgabe)
    assert vorgabe.status == "planned"


def test_wiederherstellen_ordnet_neu_zu(client, vorgabe, db):
    """Sonst ist die Einheit zurück, gilt aber als ungeplant — Tag grau."""
    echt = _fahrt(db, 88)
    classify_session(db, echt)
    client.delete(f"/api/history/sessions/{echt.id}")

    antwort = client.post(f"/api/history/sessions/{echt.id}/restore")
    assert antwort.status_code == 200

    db.expire_all()
    db.refresh(vorgabe)
    assert vorgabe.status == "completed"
    assert vorgabe.matched_session_id == echt.id
