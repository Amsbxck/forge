"""Arbeitswege zählen als Last, nicht als Trainingseinheiten.

Der Wochenblock des Coach-Prompts trägt eine Spalte "Einheiten" und einen
Zusatz "Umfang erreicht, Ausführung abweichend". Der Zusatz existiert, um den
Coach vom Zurückfahren abzuhalten: Wer mehr Einheiten absolviert hat als geplant
waren, hat nichts ausgelassen, auch wenn die Zuordnung sie nicht trifft.

Gerechnet wurde er über **alle** Einheiten. Drei Fahrten zur Arbeit füllten die
Zahl damit auf, und der Satz feuerte nach Wochen, in denen die Hälfte des Plans
liegen geblieben war — ausgerechnet der Zusatz, der ein Zurückfahren verhindern
soll, verhinderte es, nachdem wirklich etwas gefehlt hatte.
"""

from datetime import date, timedelta

import pytest

from models import PlannedSession, TrainingSession, User, WeeklyPlan
from services.season_summary import build, prompt_block

MONTAG = date(2026, 10, 5)


@pytest.fixture
def woche(db):
    """Vier geplante Einheiten, zwei absolviert, drei Arbeitswege dazu."""
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=40, week_start=MONTAG,
                      week_end=MONTAG + timedelta(days=6), plan_phase="Build",
                      plan_content={"days": [1]})
    db.add(plan); db.commit()

    for i in range(4):
        db.add(PlannedSession(
            user_id=nutzer.id, plan_id=plan.id, week_number=40,
            planned_date=MONTAG + timedelta(days=i), day_index=i, day_name="Tag",
            discipline="bike", duration_min=90, training_type="z2_endurance",
            status="completed" if i < 2 else "planned",
        ))
    for i in range(2):
        db.add(TrainingSession(user_id=nutzer.id, session_date=MONTAG + timedelta(days=i),
                               discipline="bike", duration_min=90, tss=70, week_number=40))
    for i in range(3):
        db.add(TrainingSession(user_id=nutzer.id, session_date=MONTAG + timedelta(days=i),
                               discipline="bike", duration_min=21, tss=10, week_number=40,
                               is_commute=True))
    db.commit()
    yield nutzer
    db.query(TrainingSession).filter(TrainingSession.week_number == 40).delete()
    db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.id == plan.id).delete()
    db.commit()


def _zeile(db, nutzer):
    text = prompt_block(db, nutzer, heute=MONTAG + timedelta(days=6))
    for z in text.split("\n"):
        if str(MONTAG) in z:
            return z
    return ""


def test_umfang_gilt_nicht_als_erreicht(db, woche):
    """Der Kern: zwei von vier Einheiten sind kein erreichter Umfang."""
    zeile = _zeile(db, woche)
    assert "2/4" in zeile
    assert "Umfang erreicht" not in zeile, zeile


def test_die_wege_stehen_ausgewiesen_daneben(db, woche):
    """Die Last bleibt in der Summe, aber der Anteil ist sichtbar."""
    zeile = _zeile(db, woche)
    assert "davon 3 Wege" in zeile, zeile


def test_last_bleibt_vollstaendig(db, woche):
    """Arbeitswege sind echtes Radfahren — TSS und Stunden zählen sie mit."""
    daten = build(db, woche, heute=MONTAG + timedelta(days=6))
    w = next(x for x in daten["wochen"] if x["start"] == MONTAG)
    assert w["anzahl"] == 5
    assert w["wege"] == 3
    assert w["tss"] == round(2 * 70 + 3 * 10)
    assert w["stunden"] == round((2 * 90 + 3 * 21) / 60, 1)


def test_ohne_wege_bleibt_der_zusatz_erhalten(db):
    """Gegenprobe: Der Satz muss weiter feuern, wenn er zutrifft.

    Vier geplant, zwei zugeordnet, aber fünf echte Einheiten absolviert — dann
    wurde der Umfang tatsächlich erreicht und der Coach darf nicht kürzen.
    """
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=42, week_start=date(2026, 10, 19),
                      week_end=date(2026, 10, 25), plan_phase="Build", plan_content={"days": [1]})
    db.add(plan); db.commit()
    for i in range(4):
        db.add(PlannedSession(
            user_id=nutzer.id, plan_id=plan.id, week_number=42,
            planned_date=date(2026, 10, 19) + timedelta(days=i), day_index=i,
            day_name="Tag", discipline="bike", duration_min=90,
            status="completed" if i < 2 else "planned",
        ))
    for i in range(5):
        db.add(TrainingSession(user_id=nutzer.id, session_date=date(2026, 10, 19) + timedelta(days=i),
                               discipline="bike", duration_min=90, tss=70, week_number=42))
    db.commit()

    text = prompt_block(db, nutzer, heute=date(2026, 10, 25))
    zeile = next(z for z in text.split("\n") if "2026-10-19" in z)
    assert "Umfang erreicht" in zeile, zeile
    assert "Wege" not in zeile

    db.query(TrainingSession).filter(TrainingSession.week_number == 42).delete()
    db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
    db.query(WeeklyPlan).filter(WeeklyPlan.id == plan.id).delete()
    db.commit()
