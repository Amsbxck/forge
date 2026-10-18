"""Audit B1 — Projektion, Planauswahl und Phasenetikett. Jeder Test beschreibt
einen Fehler aus der Code-Prüfung vom 18.10.2026 und hält seine Behebung fest."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from tests.test_pruefung_adversarial import nutzer_fabrik  # noqa: F401 - Fixture


def _tag(montag, offset=0, art="run"):
    d = montag + timedelta(days=offset)
    namen = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return {"day": namen[d.weekday()], "date": str(d), "session_type": art,
            "training_type": "z2_endurance", "duration_min": 40}


def _plan(db, uid, woche, montag, tage, phase="Base 1", erzeugt=None):
    from models import WeeklyPlan

    plan = WeeklyPlan(
        user_id=uid, week_number=woche, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase=phase,
        plan_content={"days": tage},
    )
    if erzeugt is not None:
        plan.generated_at = erzeugt
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ── Checkliste 2: gleiche Wochennummer, andere Kalenderwoche ─────────────────

def test_projektion_loescht_keine_fremde_kalenderwoche_gleicher_nummer(db, nutzer_fabrik):
    """`project_plan` löscht alle `planned_sessions` mit derselben
    `week_number` (`plan_projection.py:199-204`), nicht dieselbe Kalenderwoche.

    Realistischer Ablauf: Ein Athlet ohne Ziel plant über den Profilanker
    (Woche 1 = Registrierungsmontag), setzt dann ein Saisonziel mit eigenem
    `plan_start_date`. Dessen „Woche 3" ist eine andere Kalenderwoche als die
    alte Woche 3 — und die Projektion der neuen löscht die alte samt Status
    „completed" und Rückverweis der Trainingseinheit.
    """
    from models import PlannedSession
    from services.plan_projection import project_plan

    uid = nutzer_fabrik().id
    alt_montag, neu_montag = date(2031, 1, 13), date(2031, 3, 3)

    alt = _plan(db, uid, 3, alt_montag, [_tag(alt_montag)], phase="Off Season · Formerhalt")
    assert project_plan(db, alt) == 1
    zeile = db.query(PlannedSession).filter(PlannedSession.plan_id == alt.id).one()
    zeile.status = "completed"
    db.commit()

    neu = _plan(db, uid, 3, neu_montag, [_tag(neu_montag, art="bike")])
    assert project_plan(db, neu) == 1

    uebrig = db.query(PlannedSession).filter(PlannedSession.plan_id == alt.id).all()
    assert len(uebrig) == 1, "erledigte Einheit einer anderen Kalenderwoche gelöscht"


# ── Checkliste 4: /planned/am wählt anders als /plan/am ──────────────────────

def test_planned_am_folgt_derselben_auswahl_wie_plan_am(client, db):
    """`/plan/am/{montag}` nimmt über `pick_plan` den jüngsten Plan **mit Tagen**.
    `/planned/am/{montag}` (`routers/planned.py:64-69`) nimmt den jüngsten
    überhaupt. Liegt ein tagloser Plan obenauf, zeigt der Wochenplan sieben
    Tage und der Kalender keine Einheit."""
    from models import PlannedSession, User, WeeklyPlan
    from services.plan_projection import project_plan

    uid = db.query(User).order_by(User.id.asc()).first().id
    montag = date(2031, 5, 5)
    voll = _plan(db, uid, 9101, montag, [_tag(montag, i) for i in range(7)],
                 erzeugt=datetime(2031, 5, 1, 8, 0))
    project_plan(db, voll)
    leer = _plan(db, uid, 9101, montag, [], erzeugt=datetime(2031, 5, 2, 8, 0))
    try:
        plan = client.get(f"/api/plan/am/{montag}").json()
        einheiten = client.get(f"/api/planned/am/{montag}").json()
        assert plan["id"] == voll.id
        assert len(einheiten) == 7, (
            f"/plan/am zeigt Plan {voll.id} mit 7 Tagen, /planned/am liefert {einheiten}")
    finally:
        db.query(PlannedSession).filter(
            PlannedSession.plan_id.in_([voll.id, leer.id])).delete(synchronize_session=False)
        db.query(WeeklyPlan).filter(
            WeeklyPlan.id.in_([voll.id, leer.id])).delete(synchronize_session=False)
        db.commit()


# ── Checkliste 3: backfill_all wählt nicht den aktiven Plan ──────────────────

def test_backfill_projiziert_den_aktiven_plan_der_woche(db, nutzer_fabrik):
    """`backfill_all` sortiert nur nach `week_number`. Jede Projektion löscht
    die ganze Woche, also gewinnt der **zuletzt verarbeitete** Plan — nicht
    der, den `pick_plan` (jüngster mit Tagen) als aktiv auswählt. Danach
    liefert `/planned/week/{n}` für den aktiven Plan keine Einheit mehr."""
    from core.tenancy import acting_as
    from models import PlannedSession
    from services.plan_projection import backfill_all
    from services.plan_selection import plan_der_woche

    uid = nutzer_fabrik().id
    montag = date(2031, 7, 7)
    # Der neuere Plan wird zuerst eingefügt (kleinere ID), der ältere danach.
    neuer = _plan(db, uid, 9201, montag, [_tag(montag, i) for i in range(3)],
                  erzeugt=datetime(2031, 7, 3, 8, 0))
    aelter = _plan(db, uid, 9201, montag, [_tag(montag, i, "bike") for i in range(3)],
                   erzeugt=datetime(2031, 7, 1, 8, 0))

    with acting_as(uid):
        backfill_all(db)
        aktiv = plan_der_woche(db, montag)
        assert aktiv.id == neuer.id
        anzahl = db.query(PlannedSession).filter(PlannedSession.plan_id == aktiv.id).count()
    assert anzahl == 3, (
        f"aktiver Plan {neuer.id} ohne Projektion; projiziert ist Plan {aelter.id}")


# ── Checkliste 6: Phasenetikett und Countdown am falschen Tag ────────────────

MOCK = {"week": 0, "phase": "egal", "coaching_comment": "", "adjustments": [], "days": []}


def test_grundlagen_etikett_gilt_fuer_die_geplante_woche(db, nutzer_fabrik):
    """`plan_generator.py:302` speichert `base_phase(plan_start)` und
    `:206` baut den Grundlagenblock — beide rechnen mit `date.today()`,
    während `lage` (`:194`) mit `week_start` rechnet.

    Wer heute (neun Wochen vor dem Aufbau) die letzte Woche vor dem Aufbau
    plant, bekommt „Grundlage" und „noch 9 Wochen" statt
    „Vorbereitung auf den Aufbau" und „noch 1 Wochen"."""
    from core.tenancy import acting_as
    from core.wochen import montag_von
    from models import AthleteProfile, RaceGoal, WeeklyPlan
    from services.base_period import phase_label, wochen_bis_aufbau
    from services.plan_generator import generate_and_save_plan

    nutzer = nutzer_fabrik()
    heute = date.today()
    plan_start = montag_von(heute) + timedelta(weeks=10)
    ziel_montag = plan_start - timedelta(weeks=1)
    erwartet = phase_label(plan_start, heute=ziel_montag)
    tatsaechlich_heute = phase_label(plan_start)
    if erwartet == tatsaechlich_heute:  # pragma: no cover - Datumslage
        pytest.skip("heute und Zielwoche fallen auf dasselbe Etikett")

    db.add(AthleteProfile(user_id=nutzer.id, name="Grundlage"))
    ziel = RaceGoal(user_id=nutzer.id, sport="triathlon", distance="olympic",
                    priority="A", is_active=True, plan_weeks=20,
                    plan_start_date=plan_start,
                    race_date=plan_start + timedelta(weeks=19, days=6))
    db.add(ziel)
    db.commit()
    try:
        with acting_as(nutzer.id), patch(
            "services.plan_generator.generate_weekly_plan",
            autospec=True, return_value=dict(MOCK),
        ) as gen:
            plan = generate_and_save_plan(db, montag=ziel_montag)
            import asyncio
            plan = asyncio.run(plan)
        grundlage_text = gen.call_args.kwargs["base_period"]
        assert plan.plan_phase == erwartet, plan.plan_phase
        assert f"**{wochen_bis_aufbau(plan_start, ziel_montag)} Wochen**" in grundlage_text
    finally:
        db.rollback()
        db.query(WeeklyPlan).filter(WeeklyPlan.user_id == nutzer.id).delete(
            synchronize_session=False)
        db.query(RaceGoal).filter(RaceGoal.user_id == nutzer.id).delete(
            synchronize_session=False)
        db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).delete(
            synchronize_session=False)
        db.commit()
