"""Audit B3: Saison- und Kalenderrechnung, Schwellen, Testwoche, Gesundheit.

Aus der Code-Prüfung vom 18.10.2026. Jeder Test beschreibt das **erwartete**
Verhalten; die damalige Fehlerbeschreibung steht jeweils im Docstring.
"""

import types
from datetime import date, datetime, timedelta

import pytest

from core.race_types import (
    RACE_TYPES, phase_for_week, plan_start_for, season_state,
)
from core.wochen import montag_von
from services.benchmark_timing import pruefe
from services.plan_generator import get_week_for_date


# ── Hilfen ──────────────────────────────────────────────────────────────────

@pytest.fixture
def nutzer(db):
    from models import (
        AthleteProfile, AuthAction, HealthEvent, HrvMeasurement, PlannedSession,
        RaceGoal, RaceResult, TrainingSession, User, WeeklyPlan,
    )

    angelegt: list[int] = []

    def neu():
        u = User(email=f"audit-b3-{len(angelegt)}-{datetime.utcnow().timestamp()}@test.local",
                 name="Audit B3")
        db.add(u)
        db.commit()
        angelegt.append(u.id)
        return u

    yield neu

    db.rollback()
    for uid in angelegt:
        db.query(TrainingSession).filter(TrainingSession.user_id == uid).update(
            {"planned_session_id": None}, synchronize_session=False)
        db.query(PlannedSession).filter(PlannedSession.user_id == uid).delete(
            synchronize_session=False)
        db.query(WeeklyPlan).filter(WeeklyPlan.user_id == uid).delete(synchronize_session=False)
        for modell in (TrainingSession, HealthEvent, RaceGoal, RaceResult,
                       HrvMeasurement, AthleteProfile, AuthAction):
            db.query(modell).filter(modell.user_id == uid).delete(synchronize_session=False)
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def auth_an(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    # Kein Mailversand: dann verlangt `bestaetigung_noetig` nichts.
    monkeypatch.setattr(settings, "MAIL_API_KEY", "", raising=False)
    return settings


def _kopf(u):
    from core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(u.id, u.email)}"}


def _profil(db, u, **felder):
    from models import AthleteProfile
    felder.setdefault("name", "Audit")
    felder.setdefault("plan_start_date", montag_von(date.today()))
    p = AthleteProfile(user_id=u.id, **felder)
    db.add(p)
    db.commit()
    return p


class _KeinDB:
    """`pruefe` ohne Rennen und ohne Krankheit."""

    class _Leer:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return None

    def query(self, *a, **k):
        return self._Leer()


# ── 1. Testwoche ────────────────────────────────────────────────────────────

def test_eingetragene_werte_sperren_die_testwoche_nicht(client, db, nutzer, auth_an):
    """`submit_intake` verspricht: „Die Testwoche entfällt dadurch ausdrücklich
    nicht." Es setzt aber `zones_updated_at = jetzt`, und `pruefe` liest genau
    das als frische Messung — wer beim Einstieg nur seinen Maximalpuls
    einträgt, kann 90 Tage lang keine Testwoche anlegen."""
    u = nutzer()
    _profil(db, u, zones_source="default")
    r = client.post("/api/profile/intake", json={"max_hr": 190}, headers=_kopf(u))
    assert r.status_code == 200, r.text

    lage = client.get("/api/benchmark/timing", headers=_kopf(u)).json()
    assert lage["moeglich"] is True, lage["gruende"]


def test_nach_dem_saisonziel_ohne_ergebnis_keine_testwoche():
    """Die Sperre nach einem Wettkampf hängt allein an `RaceResult`. Wer sein
    A-Rennen nicht nachträgt, darf ab dem Tag danach testen — die Sperre vor
    dem Ziel endet am Renntag (`0 <= tage_bis`)."""
    heute = date(2027, 6, 27)          # Sonntag
    renntag = heute - timedelta(days=1)  # Samstag, gestern
    lage = pruefe(_KeinDB(), ziel_datum=renntag, heute=heute)
    assert lage["moeglich"] is False, lage


def test_testwoche_nicht_im_taper():
    """Modul-Docstring: „In Taper und Wettkampfwoche gibt es nichts zu
    messen." Die Sperre zählt 21 Tage ab heute; bei drei Taperwochen
    (33/40 Wochen) liegt die erlaubte Testwoche dann in Taper-Woche 1."""
    renntag = date(2027, 6, 27)                   # Sonntag
    gesamt = 33
    start_plan = plan_start_for(renntag, gesamt)
    heute = renntag - timedelta(days=21)          # Sonntag
    lage = pruefe(_KeinDB(), ziel_datum=renntag, heute=heute)
    woche = (lage["start"] - start_plan).days // 7 + 1 if lage["start"] else None
    phase = phase_for_week(woche, gesamt) if woche else None
    assert not (lage["moeglich"] and phase and phase.startswith("Taper")), (woche, phase)


def test_onboarding_radsport_braucht_keinen_lauftest(db, nutzer):
    """`needs_bike = goal is None or sport == "triathlon"` — bei einem
    Radsportziel wird der Radtest ignoriert und ein Lauftest verlangt, den die
    Radsport-Testwoche (`benchmark_week("cycling")`) gar nicht enthält. Der
    Schritt „Tests absolviert" wird nie erledigt."""
    from core.tenancy import acting_as
    from models import RaceGoal, TrainingSession, WeeklyPlan
    from services.onboarding import status

    u = nutzer()
    montag = montag_von(date.today()) - timedelta(days=7)
    db.add(RaceGoal(user_id=u.id, sport="cycling", distance="gran_fondo",
                    race_date=date.today() + timedelta(days=200), priority="A",
                    plan_weeks=16, plan_start_date=montag, is_active=True))
    db.add(WeeklyPlan(user_id=u.id, week_number=1, week_start=montag,
                      week_end=montag + timedelta(days=6), plan_phase="Benchmark",
                      plan_content={"days": [{"day": "Montag"}]}))
    db.add(TrainingSession(user_id=u.id, session_date=montag + timedelta(days=1),
                           week_number=1, discipline="bike", duration_min=60,
                           streams={"watts": [250] * 10}))
    db.commit()

    with acting_as(u.id):
        schritte = {s["key"]: s for s in status(db, u)["steps"]}
    assert schritte["benchmark_done"]["done"] is True, schritte["benchmark_done"]


# ── 2. Zonen aus der Testwoche ──────────────────────────────────────────────

def _schwimmtest(db, u, runden):
    from models import PlannedSession, TrainingSession, WeeklyPlan

    montag = montag_von(date.today())
    plan = WeeklyPlan(user_id=u.id, week_number=1, week_start=montag,
                      week_end=montag + timedelta(days=6), plan_phase="Benchmark",
                      plan_content={"days": []})
    db.add(plan)
    db.commit()
    ps = PlannedSession(user_id=u.id, plan_id=plan.id, week_number=1,
                        planned_date=date.today(), discipline="swim",
                        training_type="intervals", day_index=0, status="planned")
    db.add(ps)
    db.commit()
    db.add(TrainingSession(user_id=u.id, session_date=date.today(), week_number=1,
                           discipline="swim", duration_min=45, planned_session_id=ps.id,
                           streams={"laps": runden}))
    db.commit()


def test_von_hand_gesetzte_css_bleibt_stehen(db, nutzer):
    """`benchmark.py` ~804: „Ein von Hand eingetragener CSS-Wert wird nicht
    überschrieben", ebenso `/profile/swim-test`: „Von Hand gesetzte Werte
    werden von der automatischen Ableitung nicht mehr überschrieben." Der
    Code darunter schreibt die CSS ohne Blick auf `css_source`."""
    from core.tenancy import acting_as
    from services.benchmark import derive_zones

    u = nutzer()
    profil = _profil(db, u, css_pace_s_per_100m=100.0, css_source="manual",
                     zones_source="default")
    _schwimmtest(db, u, [{"d": 0.4, "t": 360, "hr": 150}, {"d": 0.2, "t": 170}])

    # Die automatische Übernahme nach einem Import (`maybe_autoderive`) —
    # der Knopf „Übernehmen" darf den Handwert bewusst ersetzen.
    with acting_as(u.id):
        ergebnis = derive_zones(db, days=21, apply=True, von_hand=False)
    db.refresh(profil)
    assert ergebnis.get("css_pace_s_per_100m") == 95.0, ergebnis
    assert profil.css_pace_s_per_100m == 100.0
    assert profil.css_source == "manual"
    assert "css_pace_s_per_100m" in ergebnis.get("nicht_ueberschrieben", [])


def test_abgeleitete_css_behaelt_ihre_strecken(db, nutzer):
    """`derive_zones` liest `d_lang_m`/`d_kurz_m` aus `sources["css"]`, legt
    dort aber nur `t400_s`/`t200_s` ab. Die Strecken landen immer als None im
    Profil — bei einem 200/100-Test steht dann die 200-m-Zeit in `css_t400_s`
    ohne Hinweis, dass es keine 400 m waren."""
    from core.tenancy import acting_as
    from services.benchmark import derive_zones

    u = nutzer()
    profil = _profil(db, u, zones_source="default")
    _schwimmtest(db, u, [{"d": 0.2, "t": 180, "hr": 150}, {"d": 0.1, "t": 80}])

    with acting_as(u.id):
        derive_zones(db, days=21, apply=True)
    db.refresh(profil)
    assert profil.css_pace_s_per_100m == 100.0
    assert (profil.css_dist_lang_m, profil.css_dist_kurz_m) == (200, 100)


def test_unplausibles_paar_faellt_nicht_still_auf_kuerzeres():
    """`detect_from_session`: „Nicht stillschweigend das nächstkürzere Paar
    nehmen … Der Grund wird gemeldet" — direkt darunter steht `continue`, und
    das nächste Paar (hier die 200 m des verunglückten Tests gegen eine 100-m-
    Einschwimmrunde) wird als CSS zurückgegeben."""
    from services.swim_css import detect_from_session

    sitzung = types.SimpleNamespace(
        id=1, session_date=date.today(),
        streams={"laps": [
            {"d": 0.4, "t": 300},   # 1:15/100 m
            {"d": 0.2, "t": 150},   # 1:15/100 m → nicht schneller: Einwand
            {"d": 0.1, "t": 68},    # Einschwimmen
        ]},
    )
    treffer = detect_from_session(sitzung)
    assert treffer is not None and "einwand" in treffer, treffer


# ── 3. Krankheit ────────────────────────────────────────────────────────────

def test_lange_krankheit_bekommt_einen_wiedereinstieg(db, nutzer):
    """`guidance` sucht beendete Episoden über `recent_events`, das nach
    `start_date >= heute - 28` filtert. Eine fünfwöchige Krankheit, die
    gestern endete, fällt heraus — ausgerechnet der längste Ausfall gilt als
    „healthy", ohne Wiedereinstieg."""
    from models import HealthEvent
    from services.health import guidance

    u = nutzer()
    heute = date.today()
    db.add(HealthEvent(user_id=u.id, kind="illness", severity="severe", fever=True,
                       start_date=heute - timedelta(days=35),
                       end_date=heute - timedelta(days=1)))
    db.commit()
    assert guidance(db, u, today=heute).status == "returning"


def test_taperanpassung_nur_vor_dem_rennen(db, nutzer):
    """`taper_adjustment` zählt Ausfalltage der letzten 21 Tage **vor heute**
    und prüft nie, ob das Rennen nahe ist. Ein Schnupfen im Grundlagenblock
    erzeugt im Prompt „TAPER ANGEPASST: … in den letzten drei Wochen vor dem
    Rennen" — ein halbes Jahr vor dem Rennen."""
    from models import HealthEvent
    from services.health import prompt_block

    u = nutzer()
    heute = date.today()
    db.add(HealthEvent(user_id=u.id, kind="illness", severity="mild",
                       start_date=heute - timedelta(days=6),
                       end_date=heute - timedelta(days=4)))
    db.commit()
    text = prompt_block(db, u, race_date=heute + timedelta(days=180), total_weeks=33)
    assert "TAPER ANGEPASST" not in text, text


# ── 4. Saisonstruktur ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sport,distanz",
    [(s, d) for s, ds in RACE_TYPES.items() for d in ds],
)
def test_jede_vorlage_hat_eine_eigene_taperwoche(sport, distanz):
    """Für Olympisch steht in `race_types.py`, dass ein Taper, der mit der
    Wettkampfwoche zusammenfällt, ein Fehler war. Behoben wurde nur diese
    Distanz: Sprint, 10 km, Halbmarathon, Zeitfahren und Radmarathon haben
    nach `phase_for_week` keine einzige Taperwoche (Taper == letzte Woche ==
    „Race Week")."""
    wochen = RACE_TYPES[sport][distanz]["weeks"]
    phasen = [phase_for_week(w, wochen) for w in range(1, wochen + 1)]
    assert any(p.startswith("Taper") for p in phasen), phasen[-4:]


def test_wettkampfwoche_ist_die_kalenderwoche_des_rennens():
    """`season_state` meldet `race_week`, sobald das Rennen weniger als
    7 Tage entfernt ist; Phasen und Planwoche nennen die Kalenderwoche des
    Rennens so. Bei einem Samstagsrennen sagt `/metrics/week` am Sonntag davor
    `race_week` — mit Woche 19/20 und Phase „Taper"."""
    renntag = date(2027, 6, 26)            # Samstag
    gesamt = 20
    start = plan_start_for(renntag, gesamt)
    heute = renntag - timedelta(days=6)    # Sonntag der Vorwoche
    zustand = season_state(renntag, today=heute, plan_start=start)
    woche = get_week_for_date(types.SimpleNamespace(plan_start_date=start), heute)
    assert (zustand == "race_week") == (woche == gesamt), (zustand, woche)


def test_ohne_ziel_kein_platzhalter_rennen(client, db, nutzer, auth_an):
    """`season_state`: „Ohne Ziel gilt Vorbereitung". `/metrics/week` reicht
    aber das Profil als Anker durch und damit dessen Platzhalter-Renndatum aus
    der Registrierung (heute + 180). Ist der verstrichen, zeigt das Dashboard
    „OFF SEASON · N TAGE SEIT DEM RENNEN" für ein Rennen, das es nie gab."""
    u = nutzer()
    _profil(db, u, race_date=date.today() - timedelta(days=10),
            plan_start_date=montag_von(date.today()) - timedelta(weeks=26))
    r = client.get("/api/metrics/week", headers=_kopf(u))
    assert r.status_code == 200, r.text
    assert r.json()["season_state"] == "preparation", r.json()


# ── 5. Ziele ändern ─────────────────────────────────────────────────────────

def _ziel(db, u, renntag, wochen=20, aktiv=True):
    from models import RaceGoal
    g = RaceGoal(user_id=u.id, sport="triathlon", distance="olympic",
                 race_date=renntag, priority="A", plan_weeks=wochen,
                 plan_start_date=plan_start_for(renntag, wochen), is_active=aktiv)
    db.add(g)
    db.commit()
    return g


def test_verschobenes_renndatum_bleibt_in_der_letzten_woche(client, db, nutzer, auth_an):
    """`update_goal` übernimmt ein neues `race_date` roh und rechnet den
    Planstart nicht nach. Das Rennen liegt danach in Woche 24 von 20 —
    `phase_for_week` nennt die Wochen davor „Off Season"."""
    u = nutzer()
    renntag = date(2027, 6, 27)
    g = _ziel(db, u, renntag)
    r = client.patch(f"/api/goals/{g.id}", json={"race_date": str(renntag + timedelta(days=28))},
                     headers=_kopf(u))
    assert r.status_code == 200, r.text
    db.refresh(g)
    assert get_week_for_date(g, g.race_date) == g.total_weeks


def test_reaktiviertes_ziel_deaktiviert_das_andere(client, db, nutzer, auth_an):
    """`create_goal` hält genau ein aktives A-Ziel; `update_goal` mit
    `is_active: true` nicht. Danach sind zwei aktiv, und welches die Planung
    verankert, entscheidet allein das frühere Renndatum."""
    from models import RaceGoal

    u = nutzer()
    _ziel(db, u, date(2027, 6, 27), aktiv=True)
    zweites = _ziel(db, u, date(2027, 9, 12), aktiv=False)
    r = client.patch(f"/api/goals/{zweites.id}", json={"is_active": True}, headers=_kopf(u))
    assert r.status_code == 200, r.text
    aktive = db.query(RaceGoal).filter(RaceGoal.user_id == u.id, RaceGoal.priority == "A",
                                      RaceGoal.is_active == True).count()  # noqa: E712
    assert aktive == 1


def test_neues_saisonziel_loescht_keine_alte_saison(db, nutzer):
    """Ein neues A-Ziel beginnt die Wochenzählung neu. `project_plan` löscht
    geplante Einheiten über die Wochennummer — Woche 3 der neuen Saison
    räumt die erledigte Woche 3 der alten Saison ab (siehe Docstring von
    Migration 038, der genau diesen Mechanismus beschreibt)."""
    from models import PlannedSession, WeeklyPlan
    from services.plan_projection import project_plan

    u = nutzer()
    alt_montag = date(2025, 3, 3)
    alt = WeeklyPlan(user_id=u.id, week_number=3, week_start=alt_montag,
                     week_end=alt_montag + timedelta(days=6), plan_phase="Base 1",
                     plan_content={"days": []})
    db.add(alt)
    db.commit()
    erledigt = PlannedSession(user_id=u.id, plan_id=alt.id, week_number=3,
                              planned_date=alt_montag, discipline="run",
                              training_type="z2_endurance", day_index=0,
                              status="completed")
    db.add(erledigt)
    db.commit()
    erledigt_id = erledigt.id

    neu_montag = date(2026, 11, 2)
    neu = WeeklyPlan(user_id=u.id, week_number=3, week_start=neu_montag,
                     week_end=neu_montag + timedelta(days=6), plan_phase="Base 1",
                     plan_content={"days": [{"day": "Montag", "date": str(neu_montag),
                                             "session_type": "run",
                                             "training_type": "z2_endurance",
                                             "duration_min": 40}]})
    db.add(neu)
    db.commit()
    project_plan(db, neu)

    db.expire_all()
    assert db.get(PlannedSession, erledigt_id) is not None


# ── 6. Profil ───────────────────────────────────────────────────────────────

def test_maximalpuls_unter_zonenende_wird_abgelehnt(client, db, nutzer, auth_an):
    """`PATCH /profile` prüft „Z4-Ende ≤ Maximalpuls" nur, wenn Zonenfelder
    mitkommen. Ein Maximalpuls allein unter das bestehende Z4-Ende geht durch."""
    u = nutzer()
    _profil(db, u, max_hr=200, z1_hr_max=130, z2_hr_min=131, z2_hr_max=160,
            z3_hr_min=161, z3_hr_max=170, z4_hr_min=171, z4_hr_max=185)
    r = client.patch("/api/profile", json={"max_hr": 150}, headers=_kopf(u))
    assert r.status_code == 422, r.json()
