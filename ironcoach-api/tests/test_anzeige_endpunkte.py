"""Die Lese-Endpunkte hinter den Anzeige-Leisten (Saison, Soll/Ist, HRV, Budget).

Anlass: Die Oberfläche zeigte Woche, Phase, HRV und Budget als Text. Die
Leisten, die das ersetzen, brauchen Zahlen, die es im Backend schon gab — nur
nicht abrufbar. Geprüft wird, dass sie aus **derselben** Quelle kommen wie der
Planer (Phasen, Deload, HRV-Status), sonst zeigt die Leiste etwas anderes, als
der Plan bekommt. Und dass ein Athlet nur seine eigenen Zahlen sieht.
"""

from datetime import date, datetime, timedelta

import pytest

from core.race_types import deload_wochen, phase_boundaries, phase_for_week, plan_start_for
from core.wochen import montag_von

HEUTE = date.today()
MONTAG = montag_von(HEUTE)


@pytest.fixture
def nutzer(db):
    from models import (
        AthleteProfile, ApiUsage, HrvMeasurement, PlannedSession, RaceGoal,
        TrainingSession, User, WeeklyPlan,
    )

    angelegt: list[int] = []

    def neu():
        u = User(email=f"anzeige-{len(angelegt)}-{datetime.utcnow().timestamp()}@test.local",
                 name="Anzeige")
        db.add(u)
        db.commit()
        db.add(AthleteProfile(user_id=u.id, name="Anzeige", plan_start_date=MONTAG))
        db.commit()
        angelegt.append(u.id)
        return u

    yield neu

    db.rollback()
    for uid in angelegt:
        db.query(TrainingSession).filter(TrainingSession.user_id == uid).update(
            {"planned_session_id": None}, synchronize_session=False)
        db.query(PlannedSession).filter(PlannedSession.user_id == uid).update(
            {"matched_session_id": None}, synchronize_session=False)
        db.query(PlannedSession).filter(PlannedSession.user_id == uid).delete(
            synchronize_session=False)
        db.query(WeeklyPlan).filter(WeeklyPlan.user_id == uid).delete(synchronize_session=False)
        for modell in (TrainingSession, RaceGoal, HrvMeasurement, ApiUsage, AthleteProfile):
            db.query(modell).filter(modell.user_id == uid).delete(synchronize_session=False)
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def auth_an(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "MAIL_API_KEY", "", raising=False)
    return settings


def _kopf(u):
    from core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(u.id, u.email)}"}


def _ziel(db, u, renntag, wochen=20, prioritaet="A", **felder):
    from models import RaceGoal
    g = RaceGoal(user_id=u.id, sport="triathlon", distance="olympic", race_date=renntag,
                 priority=prioritaet, plan_weeks=wochen, is_active=True,
                 plan_start_date=plan_start_for(renntag, wochen), **felder)
    db.add(g)
    db.commit()
    return g


# --- Saison --------------------------------------------------------------------

def test_saison_kommt_aus_denselben_phasen_wie_der_planer(client, db, nutzer, auth_an):
    u = nutzer()
    renntag = MONTAG + timedelta(weeks=12, days=6)
    _ziel(db, u, renntag, wochen=20)
    _ziel(db, u, MONTAG + timedelta(weeks=6, days=5), wochen=8, prioritaet="B",
          race_name="Testlauf B")

    data = client.get("/api/metrics/saison", headers=_kopf(u)).json()
    assert data["lage"] == "preparation"
    assert data["total_weeks"] == 20

    # Lückenlos von Woche 1 bis zur letzten, genau wie `phase_boundaries`.
    erwartet = phase_boundaries(20)
    assert [(p["name"], p["von_woche"], p["bis_woche"]) for p in data["phasen"]] == list(erwartet)
    assert data["phasen"][0]["von_woche"] == 1
    assert data["phasen"][-1]["bis_woche"] == 20
    for a, b in zip(data["phasen"], data["phasen"][1:]):
        assert b["von_woche"] == a["bis_woche"] + 1

    assert [d["woche"] for d in data["deload"]] == sorted(deload_wochen(20))
    # Die Unterphasen Woche für Woche wie `phase_for_week`, lückenlos je Phase.
    for p in data["phasen"]:
        assert p["teile"][0]["von_woche"] == p["von_woche"]
        assert p["teile"][-1]["bis_woche"] == p["bis_woche"]
        for t in p["teile"]:
            for w in range(t["von_woche"], t["bis_woche"] + 1):
                assert phase_for_week(w, 20) == t["name"]
    assert data["phasen"][-1]["teile"][-1]["name"] == "Race Week"
    # Die Woche, in der heute liegt.
    assert data["aktuelle_woche"] == 8
    assert [r["name"] for r in data["rennen"]] == ["Testlauf B"]


def test_saison_ohne_ziel_ist_off_season(client, db, nutzer, auth_an):
    u = nutzer()
    data = client.get("/api/metrics/saison", headers=_kopf(u)).json()
    assert data["lage"] == "off_season"
    assert data["offseason_phase"] == "Formerhalt"
    assert data["phasen"] == []


def test_saison_vor_dem_aufbau_zeigt_die_grundlage(client, db, nutzer, auth_an):
    u = nutzer()
    renntag = MONTAG + timedelta(weeks=40, days=6)
    g = _ziel(db, u, renntag, wochen=20)
    data = client.get("/api/metrics/saison", headers=_kopf(u)).json()
    assert data["lage"] == "base_period"
    assert data["aktuelle_woche"] is None
    assert data["grundlage"]["bis"] == str(g.plan_start_date - timedelta(days=1))


# --- Soll/Ist ------------------------------------------------------------------

def _woche_mit_plan(db, u):
    from models import PlannedSession, TrainingSession, WeeklyPlan

    plan = WeeklyPlan(user_id=u.id, week_number=1, week_start=MONTAG,
                      week_end=MONTAG + timedelta(days=6), plan_phase="Build 2",
                      plan_content={"days": [{"day": "Montag"}]})
    db.add(plan)
    db.commit()
    rad = PlannedSession(user_id=u.id, plan_id=plan.id, week_number=1, planned_date=MONTAG,
                         day_name="Montag", discipline="bike", duration_min=60,
                         target_tss=50, day_index=0)
    lauf = PlannedSession(user_id=u.id, plan_id=plan.id, week_number=1,
                          planned_date=MONTAG + timedelta(days=1), day_name="Dienstag",
                          discipline="run", duration_min=45, target_tss=40, day_index=1)
    ersetzt = PlannedSession(user_id=u.id, plan_id=plan.id, week_number=1,
                             planned_date=MONTAG + timedelta(days=2), day_name="Mittwoch",
                             discipline="bike", duration_min=90, day_index=2,
                             status="replaced", replacement="Wandern",
                             replacement_min=120, replacement_discipline="hike")
    db.add_all([rad, lauf, ersetzt])
    db.commit()
    # Über `planned_session_id` verknüpft: 75 statt 60 Minuten Rad.
    db.add(TrainingSession(user_id=u.id, session_date=MONTAG, week_number=1,
                           discipline="bike", duration_min=75, tss=62,
                           planned_session_id=rad.id))
    # Über `matched_session_id` verknüpft: 30 statt 45 Minuten Lauf.
    s = TrainingSession(user_id=u.id, session_date=MONTAG + timedelta(days=1), week_number=1,
                        discipline="run", duration_min=30, tss=25)
    db.add(s)
    db.commit()
    lauf.matched_session_id = s.id
    # Ungeplant: ein Schwimmen am Donnerstag.
    db.add(TrainingSession(user_id=u.id, session_date=MONTAG + timedelta(days=3), week_number=1,
                           discipline="swim", duration_min=40, tss=20))
    # Gelöscht: zählt nicht.
    db.add(TrainingSession(user_id=u.id, session_date=MONTAG + timedelta(days=3), week_number=1,
                           discipline="run", duration_min=99, tss=99,
                           deleted_at=datetime.utcnow()))
    db.commit()
    return rad, lauf


def test_bilanz_je_disziplin_und_je_einheit(client, db, nutzer, auth_an):
    u = nutzer()
    rad, lauf = _woche_mit_plan(db, u)
    data = client.get(f"/api/planned/am/{MONTAG}/bilanz", headers=_kopf(u)).json()
    d = {x["discipline"]: x for x in data["disziplinen"]}

    assert (d["bike"]["geplant_min"], d["bike"]["absolviert_min"]) == (150, 75)
    assert (d["run"]["geplant_min"], d["run"]["absolviert_min"]) == (45, 30)
    # Ungeplantes getrennt, der Ersatz unter seiner eigenen Sportart.
    assert d["swim"] == {**d["swim"], "geplant_min": 0, "absolviert_min": 40, "ungeplant_min": 40}
    assert (d["hike"]["absolviert_min"], d["hike"]["ungeplant_min"]) == (120, 120)
    assert [x["discipline"] for x in data["disziplinen"]][:3] == ["swim", "bike", "run"]

    assert data["einheiten"][str(rad.id)]["ist_min"] == 75
    assert data["einheiten"][str(lauf.id)]["ist_min"] == 30
    assert data["tss"] == {"soll": 90.0, "ist": 107.0}


def test_bilanz_sieht_nur_den_eigenen_athleten(client, db, nutzer, auth_an):
    a, b = nutzer(), nutzer()
    _woche_mit_plan(db, b)
    data = client.get(f"/api/planned/am/{MONTAG}/bilanz", headers=_kopf(a)).json()
    assert data["disziplinen"] == []
    assert data["tss"] == {"soll": 0, "ist": 0}


# --- HRV -----------------------------------------------------------------------

def test_hrv_lage_wie_in_der_doppeltag_kachel(client, db, nutzer, auth_an):
    from models import AthleteProfile, HrvMeasurement
    from services.doppel_urne import hrv_lage

    u = nutzer()
    assert client.get("/api/hrv/lage", headers=_kopf(u)).json() is None

    for tage, wert, status in ((0, 60, "yellow"), (2, 80, "green")):
        db.add(HrvMeasurement(user_id=u.id, measured_at=HEUTE - timedelta(days=tage),
                              rmssd=wert, hrv_status=status))
    db.commit()
    data = client.get("/api/hrv/lage", headers=_kopf(u)).json()
    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == u.id).one()
    erwartet = hrv_lage(db, profil)
    assert data["status"] == erwartet["status"] == "yellow"
    assert data["schnitt_7"] == erwartet["schnitt_7"] == 70.0


# --- Budget --------------------------------------------------------------------

def test_budget_je_art_ohne_reservierungen(client, db, nutzer, auth_an):
    from models import ApiUsage
    from services.api_budget import RESERVIERT

    u = nutzer()
    for art, kosten in (("plan", 0.10), ("plan", 0.20), ("chat", 0.02),
                        ("plan" + RESERVIERT, 0.50)):
        db.add(ApiUsage(user_id=u.id, kind=art, model="m", input_tokens=1,
                        output_tokens=1, cost_eur=kosten))
    db.commit()
    je_art = client.get("/api/budget", headers=_kopf(u)).json()["je_art"]
    assert set(je_art) == {"plan", "chat"}
    assert je_art["plan"]["aufrufe"] == 2
    assert je_art["plan"]["schnitt_eur"] == pytest.approx(0.15)
    assert je_art["chat"]["schnitt_eur"] == pytest.approx(0.02)


# --- Zonen der Woche -------------------------------------------------------------

def test_zonen_der_woche_nach_dauer_gewichtet(client, db, nutzer, auth_an):
    """Vier Stunden Z2 und 20 Minuten Z4: Die Woche ist fast nur Z2.

    Vorher das Mittel der Prozentwerte — das ergab 50 % / 50 %.
    """
    from models import TrainingSession

    u = nutzer()
    db.add(TrainingSession(user_id=u.id, session_date=HEUTE, week_number=1, discipline="bike",
                           duration_min=240, hr_zones={"z2": 100.0, "z4": 0.0}))
    db.add(TrainingSession(user_id=u.id, session_date=HEUTE, week_number=1, discipline="run",
                           duration_min=20, hr_zones={"z2": 0.0, "z4": 100.0}))
    db.commit()
    zonen = client.get("/api/metrics/week", headers=_kopf(u)).json()["hr_zones_avg"]
    assert zonen["z2"] == pytest.approx(92.3, abs=0.1)
    assert zonen["z4"] == pytest.approx(7.7, abs=0.1)
