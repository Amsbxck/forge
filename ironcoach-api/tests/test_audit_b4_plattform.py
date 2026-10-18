"""Audit B4 (Plattform): Tests, die gefundene Fehler belegen.

Aus der Code-Prüfung vom 18.10.2026. Jeder Test beschreibt das **erwartete**
Verhalten und hält die Behebung des jeweiligen Befunds fest.
"""

import asyncio
import os
from datetime import date, datetime, timedelta

import pytest

from models import (
    ApiUsage, AthleteProfile, PlannedSession, RaceGoal, StravaCredentials,
    TrainingSession, User, WeeklyPlan,
)


def _nutzer(db, email: str) -> User:
    u = User(email=email, name="Audit")
    db.add(u)
    db.commit()
    return u


# --- Checkliste 2: Scheduler teilt eine Sitzung über alle Athleten ---------

def test_scheduler_naechster_athlet_laeuft_nach_db_fehler(client, db, monkeypatch):
    """Ein Datenbankfehler bei Athlet A darf Athlet B nicht mitreißen."""
    import core.scheduler as scheduler
    import services.reconcile as reconcile

    a = _nutzer(db, "b4-sched-a@example.invalid")
    b = _nutzer(db, "b4-sched-b@example.invalid")
    db.add_all([
        StravaCredentials(user_id=a.id, athlete_id=91000001, access_token="x",
                          refresh_token="y", expires_at=0),
        StravaCredentials(user_id=b.id, athlete_id=91000002, access_token="x",
                          refresh_token="y", expires_at=0),
    ])
    db.commit()

    gesehen: list[int] = []
    fertig: list[int] = []

    async def fake_reconcile(sitzung, days=14):
        from core.tenancy import get_current_user_id

        uid = get_current_user_id()
        gesehen.append(uid)
        if len(gesehen) == 1:
            # Wie ein echter Ingest: erst ein Commit (läßt alle Objekte
            # verfallen), dann ein Flush, der an einer Bedingung scheitert.
            sitzung.commit()
            sitzung.add(TrainingSession(user_id=uid, session_date=None,
                                        week_number=1, discipline="run"))
            sitzung.flush()
        sitzung.query(User).filter(User.id == uid).first()
        fertig.append(uid)
        return {"activities": {}, "obsidian": {}}

    monkeypatch.setattr(reconcile, "run_full_reconcile", fake_reconcile)
    asyncio.run(scheduler._reconcile_job())

    # Erwartet: der zweite Athlet wurde trotz des Fehlers beim ersten
    # vollständig abgeglichen.
    assert len(fertig) >= 1, f"gesehen={gesehen}, fertig={fertig}"


# --- Checkliste 6: Export und Löschung ---------------------------------------

def test_export_enthaelt_api_verbrauch():
    from services.account_export import NUTZERDATEN

    assert any(modell is ApiUsage for _, modell in NUTZERDATEN), (
        "ApiUsage fehlt in NUTZERDATEN: Export unvollständig, Nachkontrolle blind"
    )


def test_loeschen_mit_zyklischen_verweisen(db):
    """planned_sessions <-> training_sessions zeigen aufeinander — die
    Löschung per CASCADE muss trotzdem durchgehen (erwartet: grün)."""
    from services.account_export import delete_user_data

    u = _nutzer(db, "b4-zyklus@example.invalid")
    plan = WeeklyPlan(user_id=u.id, week_number=1, week_start=date(2026, 10, 12),
                      week_end=date(2026, 10, 18), plan_content={"days": []})
    db.add(plan)
    db.commit()
    ps = PlannedSession(user_id=u.id, plan_id=plan.id, week_number=1,
                        planned_date=date(2026, 10, 12), discipline="run")
    db.add(ps)
    db.commit()
    ts = TrainingSession(user_id=u.id, session_date=date(2026, 10, 12), week_number=1,
                         discipline="run", planned_session_id=ps.id)
    db.add(ts)
    db.commit()
    ps.matched_session_id = ts.id
    db.add(ApiUsage(user_id=u.id, kind="plan", model="m", cost_eur=0.1))
    db.commit()

    uid = u.id
    delete_user_data(db, u)
    for modell in (WeeklyPlan, PlannedSession, TrainingSession, ApiUsage):
        assert db.query(modell).filter(modell.user_id == uid).count() == 0


def test_loeschen_entfernt_fit_dateien(db, tmp_path, monkeypatch):
    from core.config import settings
    from services.account_export import delete_user_data

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    datei = tmp_path / "audit_b4.fit"
    datei.write_bytes(b"FIT")

    u = _nutzer(db, "b4-fit@example.invalid")
    db.add(TrainingSession(user_id=u.id, session_date=date(2026, 10, 1), week_number=1,
                           discipline="run", fit_file_path=str(datei)))
    db.commit()
    delete_user_data(db, u)

    assert not datei.exists(), "FIT-Datei bleibt nach Kontolöschung auf dem Datenträger"


# --- Checkliste 9: Platzhalter aus dem Profil im Prompt ----------------------

def _registriertes_profil(db, email: str) -> tuple[AthleteProfile, RaceGoal]:
    """Profil genau so, wie `routers/auth.register` es anlegt, plus Ziel."""
    from core.wochen import montag_von

    # Nicht gespeichert: `build_athlete_dict` liest nur Attribute. Gespeichert
    # blieb hier ein zweites Profil samt aktivem Ziel in der Testdatenbank, und
    # reguläre Tests, die `query(AthleteProfile).first()` nehmen, griffen
    # danach dieses statt des eigenen.
    heute = date.today()
    profil = AthleteProfile(name="Audit", plan_start_date=montag_von(heute),
                            race_date=heute + timedelta(days=180), zones_source="default")
    ziel = RaceGoal(sport="running", distance="marathon",
                    race_date=date(2027, 4, 11), priority="A")
    return profil, ziel


def test_prompt_renntag_kommt_aus_dem_ziel(db):
    from services.plan_generator import build_athlete_dict

    profil, ziel = _registriertes_profil(db, "b4-prompt-datum@example.invalid")
    daten = build_athlete_dict(profil, ziel)
    assert daten["race_date"] == str(ziel.race_date), (
        f"Prompt nennt {daten['race_date']} (Platzhalter heute+180) statt {ziel.race_date}"
    )


def test_prompt_traegt_keine_fremde_zielzeit(db):
    from services.plan_generator import build_athlete_dict

    profil, ziel = _registriertes_profil(db, "b4-prompt-zeit@example.invalid")
    daten = build_athlete_dict(profil, ziel)
    assert "70.3" not in (daten.get("race_goal") or ""), (
        f"Neuer Marathon-Athlet bekommt Zielzeit {daten['race_goal']!r} in den Prompt"
    )


# --- Checkliste 4/13: Links in der Willkommensmail ---------------------------

def test_willkommensmail_folgt_frontend_url(monkeypatch):
    from core.config import settings
    from services.welcome_mail import build_welcome

    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example.invalid")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://api.example.invalid")

    _, text, _ = build_welcome("Audit", "tok123")
    assert "https://app.example.invalid/verify?token=tok123" in text, (
        "Willkommensmail ignoriert FRONTEND_URL und verlinkt PUBLIC_BASE_URL"
    )


# --- Checkliste 5: Strava-state ist ein Zugangstoken ohne Widerrufsprüfung --

def test_strava_callback_verwirft_widerrufenes_token(client, db, monkeypatch):
    import routers.strava_webhook as webhook
    from core.security import create_access_token
    from services.strava_service import StravaService

    u = _nutzer(db, "b4-widerruf@example.invalid")
    token = create_access_token(u.id, u.email)
    # Abgemeldet: alles, was vorher ausgestellt wurde, gilt nicht mehr.
    u.tokens_valid_from = datetime.utcnow() + timedelta(minutes=5)
    db.commit()

    async def fake_exchange(self, code):
        return {"athlete": {"id": 92000001}, "access_token": "a",
                "refresh_token": "r", "expires_at": 0}

    async def kein_nachholen(user_id):
        return None

    monkeypatch.setattr(StravaService, "exchange_code", fake_exchange)
    monkeypatch.setattr(webhook, "_historie_nachholen", kein_nachholen)

    r = client.get("/api/strava/callback", params={"code": "c", "state": token},
                   follow_redirects=False)
    gebunden = (
        db.query(StravaCredentials)
        .execution_options(skip_tenant_filter=True)
        .filter(StravaCredentials.athlete_id == 92000001)
        .count()
    )
    assert gebunden == 0 and "strava=fehler" in r.headers.get("location", ""), (
        f"Widerrufenes Token band Strava an das Konto: {r.status_code} {r.headers.get('location')}"
    )


# --- Checkliste 1: Mandantenfilter und Massenänderungen ----------------------

def test_mandantenfilter_greift_bei_massenaenderung(client, db):
    """Erwartet wäre Schutz auch für UPDATE — tatsächlich filtert
    `core/tenancy.py` nur SELECTs. Jede Massenänderung ohne eigenen
    Nutzerfilter trifft fremde Zeilen."""
    from core.tenancy import acting_as

    a = _nutzer(db, "b4-bulk-a@example.invalid")
    b = _nutzer(db, "b4-bulk-b@example.invalid")
    db.add(TrainingSession(user_id=a.id, session_date=date(2026, 9, 1), week_number=1,
                           discipline="run", notes="von A"))
    db.commit()

    with acting_as(b.id):
        db.query(TrainingSession).filter(
            TrainingSession.notes == "von A"
        ).update({"notes": "von B überschrieben"}, synchronize_session=False)
        db.commit()

    db.expire_all()
    with acting_as(a.id):
        zeile = db.query(TrainingSession).filter(TrainingSession.user_id == a.id).first()
    assert zeile.notes == "von A"


# --- Checkliste 12: NoBillingContext in /plan/anpassen ----------------------

def test_plan_anpassen_ohne_abrechnungskontext_ist_503(client, db, monkeypatch):
    import services.plan_adjust as plan_adjust
    from core.wochen import kalenderwoche
    from services.api_budget import NoBillingContext

    erster = db.query(User).order_by(User.id.asc()).first()
    montag, sonntag = kalenderwoche()
    db.add(WeeklyPlan(user_id=erster.id, week_number=1, week_start=montag, week_end=sonntag,
                      plan_content={"days": [{"day": "Montag"}]}))
    db.commit()

    async def ohne_kontext(db_, plan, wunsch):
        raise NoBillingContext()

    monkeypatch.setattr(plan_adjust, "tage_anpassen", ohne_kontext)
    r = client.post("/api/plan/anpassen", params={"wunsch": "x"})
    assert r.status_code == 503, f"{r.status_code}: {r.text[:200]}"
