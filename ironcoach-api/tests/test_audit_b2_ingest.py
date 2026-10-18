"""Audit B2 — Einlesen, Klassifizieren, Zuordnen, Obsidian.

Aus der Code-Prüfung vom 18.10.2026. Jeder Test beschreibt das **erwartete**
Verhalten; seit der Behebung laufen alle und halten sie fest.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from models import (
    PlannedSession, RaceGoal, StravaCredentials, TrainingSession, User, WeeklyPlan,
)


# ── Hilfen ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _aufraeumen(db):
    """Was ein Test hier anlegt, verschwindet danach wieder.

    Die Tests arbeiten teils mit dem ersten (gesäten) Nutzer. Blieben seine
    Strava-Verbindung, Einheiten und Pläne liegen, sahen reguläre Tests
    danach einen anderen Stand — etwa „Strava verbunden".
    """
    from sqlalchemy import func

    from models import AthleteProfile, GeloeschteStravaAktivitaet

    modelle = (GeloeschteStravaAktivitaet, StravaCredentials, PlannedSession,
               TrainingSession, WeeklyPlan, RaceGoal)
    vorher = {m: db.query(func.coalesce(func.max(m.id), 0)).scalar() for m in modelle}
    profil = db.query(AthleteProfile).order_by(AthleteProfile.id.asc()).first()
    stand = {c.key: getattr(profil, c.key) for c in profil.__table__.columns} if profil else {}
    yield
    db.rollback()
    for modell in modelle:
        db.query(modell).filter(modell.id > vorher[modell]).delete(synchronize_session=False)
    if profil is not None:
        db.query(AthleteProfile).filter(AthleteProfile.id == stand["id"]).update(
            {k: v for k, v in stand.items() if k != "id"}, synchronize_session=False)
    db.commit()

def _erster_nutzer(db) -> User:
    return db.query(User).order_by(User.id.asc()).first()


def _zweiter_nutzer(db) -> User:
    u = db.query(User).filter(User.email == "b2-zwei@test.local").first()
    if u is None:
        u = User(email="b2-zwei@test.local", name="Zweiter")
        db.add(u)
        db.commit()
    return u


def _plan(db, uid, woche, montag, einheiten, erzeugt=None):
    """Ein Wochenplan mit Tagen plus projizierte Einheiten."""
    plan = WeeklyPlan(
        user_id=uid, week_number=woche, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase="Base 1",
        plan_content={"days": [{"day": "Montag"}]},
        generated_at=erzeugt or datetime.utcnow(),
    )
    db.add(plan)
    db.commit()
    rows = []
    for i, (tag, disziplin, dauer) in enumerate(einheiten):
        row = PlannedSession(
            user_id=uid, plan_id=plan.id, week_number=woche, planned_date=tag,
            day_name="Tag", discipline=disziplin, training_type=None,
            duration_min=dauer, day_index=i, status="planned",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return plan, rows


def _strava(monkeypatch, aktivitaeten: dict):
    """Strava vollständig nachgebaut — kein Netz."""
    from services.strava_service import StravaService

    async def fetch_activity(self, activity_id, athlete_id):
        return aktivitaeten[activity_id]

    async def leer(self, activity_id, athlete_id):
        return {}

    async def keine_runden(self, activity_id, athlete_id):
        return []

    async def liste(self, athlete_id, after=None, per_page=50, max_seiten=1):
        return [{"id": i} for i in aktivitaeten]

    monkeypatch.setattr(StravaService, "fetch_activity", fetch_activity)
    monkeypatch.setattr(StravaService, "fetch_activity_streams", leer)
    monkeypatch.setattr(StravaService, "fetch_activity_laps", keine_runden)
    monkeypatch.setattr(StravaService, "list_activities", liste)


def _ride(aid, tag: str, minuten: int, **extra):
    return {
        "id": aid, "sport_type": "Ride", "start_date_local": f"{tag}T07:30:00Z",
        "moving_time": minuten * 60, "distance": 9000, **extra,
    }


GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="audit" xmlns="http://www.topografix.com/GPX/1/1">
<trk><type>running</type><trkseg>
<trkpt lat="48.1000" lon="11.5000"><time>{tag}T06:00:00Z</time></trkpt>
<trkpt lat="48.1100" lon="11.5000"><time>{tag}T06:{ende:02d}:00Z</time></trkpt>
</trkseg></trk></gpx>
"""


def _gpx(tag: str, minuten: int = 40) -> bytes:
    return GPX.format(tag=tag, ende=minuten).encode()


# ── 1. Intensitätsstufe ein Band zu hart (Checkliste 1) ──────────────────────

@pytest.mark.parametrize("np_watt, erwartet", [(230, "sweet_spot"), (250, "threshold")])
def test_intensitaet_folgt_coggan_wie_classify_bike(np_watt, erwartet):
    """NP/FTP 0.92 ist Sweet Spot (Z3), 1.00 ist Schwelle (Z4).

    `classify_bike` sagt genau das, `intensity_from_session` eine Stufe härter —
    und die Stufe bestimmt Anzeige, Notizordner und Prompt.
    """
    from services.classification import classify_bike, intensity_from_session

    s = SimpleNamespace(discipline="bike", normalized_power=np_watt, hr_zones=None,
                        duration_min=60, actual_type=None)
    assert classify_bike(s, 250) == erwartet, "Gegenprobe: classify_bike"
    assert intensity_from_session(s, 250) == erwartet


# ── 2. Arbeitsweg geht beim Verknüpfen verloren (Checkliste 4) ───────────────

@pytest.mark.asyncio
async def test_verknuepfen_uebernimmt_arbeitsweg(client, db, monkeypatch):
    from core.tenancy import acting_as
    from services.ingest import ingest_activity

    uid = _erster_nutzer(db).id
    tag = date(2024, 3, 5)
    _, (geplant,) = _plan(db, uid, 81, tag - timedelta(days=1), [(tag, "bike", 30)])
    fit = TrainingSession(user_id=uid, session_date=tag, week_number=81,
                          discipline="bike", duration_min=30, is_commute=False)
    db.add(fit)
    db.commit()

    _strava(monkeypatch, {770001: _ride(770001, str(tag), 30, commute=True)})
    with acting_as(uid):
        ergebnis = await ingest_activity(db, 770001, 1, sync_obsidian=False)

    db.refresh(fit)
    assert ergebnis["action"] == "linked"
    assert fit.is_commute is True, "Strava kennt den Arbeitsweg, die Einheit nicht"
    assert fit.planned_session_id is None, "Arbeitsweg erfüllt die Vorgabe"


# ── 3. Endgültig gelöscht → der Abgleich holt sie zurück (Checkliste 12) ─────

@pytest.mark.asyncio
async def test_endgueltig_geloeschte_stravaeinheit_bleibt_weg(client, db, monkeypatch):
    from core.tenancy import acting_as
    from services.ingest import ingest_activity
    from services.reconcile import reconcile_activities

    uid = _erster_nutzer(db).id
    db.add(StravaCredentials(user_id=uid, athlete_id=5550001, access_token="a",
                             refresh_token="r", expires_at=9_999_999_999))
    db.commit()

    _strava(monkeypatch, {770002: _ride(770002, "2024-03-12", 60)})
    with acting_as(uid):
        erst = await ingest_activity(db, 770002, 5550001, sync_obsidian=False)
    assert erst["action"] == "created"

    antwort = client.delete(f"/api/history/sessions/{erst['session_id']}/hard")
    assert antwort.status_code == 200

    with acting_as(uid):
        bericht = await reconcile_activities(db, days=5000)

    zurueck = db.query(TrainingSession).filter(
        TrainingSession.strava_activity_id == 770002).count()
    assert zurueck == 0, f"Doppelaufnahme wieder da: {bericht['by_action']}"


# ── 4. Ein Strava-Athlet, zwei Konten (Checkliste 6) ────────────────────────

def test_ein_stravaathlet_haengt_an_hoechstens_einem_konto(client, db):
    from core.tenancy import SKIP_OPTION, acting_as
    from services.strava_service import StravaService

    a, b = _erster_nutzer(db), _zweiter_nutzer(db)
    token = {"athlete": {"id": 6660001}, "access_token": "x",
             "refresh_token": "y", "expires_at": 9_999_999_999}
    with acting_as(a.id):
        StravaService(db).save_credentials(token)
    # Der zweite Versuch wird abgewiesen, statt eine zweite Zeile anzulegen.
    with acting_as(b.id), pytest.raises(ValueError):
        StravaService(db).save_credentials(token)
    db.rollback()

    zeilen = (db.query(StravaCredentials)
              .filter(StravaCredentials.athlete_id == 6660001)
              .execution_options(**{SKIP_OPTION: True}).all())
    assert len(zeilen) == 1, f"{len(zeilen)} Zeilen, Nutzer {[z.user_id for z in zeilen]}"


# ── 5. Ein Datenbankfehler vergiftet den ganzen Lauf (Checkliste 8/6) ───────

@pytest.mark.asyncio
async def test_ein_fehler_haelt_die_uebrigen_aktivitaeten_nicht_auf(client, db, monkeypatch):
    from core.tenancy import acting_as
    from services.reconcile import reconcile_activities

    a, b = _erster_nutzer(db), _zweiter_nutzer(db)
    # Dieselbe Strava-Aktivität liegt schon beim anderen Konto (gleicher
    # Athlet an zwei Konten, oder ein Wettlauf Webhook/Abgleich).
    db.add(TrainingSession(user_id=a.id, session_date=date(2024, 4, 1), week_number=1,
                           discipline="bike", duration_min=45, strava_activity_id=770010))
    db.add(StravaCredentials(user_id=b.id, athlete_id=6660002, access_token="a",
                             refresh_token="r", expires_at=9_999_999_999))
    db.commit()

    _strava(monkeypatch, {
        770010: _ride(770010, "2024-04-01", 45),
        770011: _ride(770011, "2024-04-02", 50),
    })
    try:
        with acting_as(b.id):
            bericht = await reconcile_activities(db, days=5000)
    finally:
        db.rollback()

    assert bericht["by_action"].get("created") == 1, bericht


# ── 6. Upload: Dateiname ungeprüft (Checkliste 2) ───────────────────────────

def test_upload_schreibt_nicht_ausserhalb_des_ordners(client, tmp_path, monkeypatch):
    from core.config import settings

    ablage = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(ablage))
    antwort = client.post("/api/upload", files={
        "file": ("../ausbruch_b2.gpx", _gpx("2024-05-01"), "application/gpx+xml")})
    assert antwort.status_code == 200, antwort.text
    assert not (tmp_path / "ausbruch_b2.gpx").exists(), "Datei liegt außerhalb von UPLOAD_DIR"


def test_upload_gleichen_namens_ueberschreibt_fremde_datei_nicht(client, db, tmp_path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    erste = client.post("/api/upload", files={
        "file": ("Morning_Run.gpx", _gpx("2024-05-02"), "application/gpx+xml")}).json()
    client.post("/api/upload", files={
        "file": ("Morning_Run.gpx", _gpx("2024-05-03"), "application/gpx+xml")})

    s = db.query(TrainingSession).filter(TrainingSession.id == erste["session_id"]).first()
    with open(s.fit_file_path, "rb") as f:
        assert b"2024-05-02" in f.read(), "die erste Einheit zeigt jetzt auf die zweite Datei"


def test_upload_derselben_datei_legt_keine_dublette_an(client, db, tmp_path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    for _ in range(2):
        client.post("/api/upload", files={
            "file": ("dup.gpx", _gpx("2024-05-04"), "application/gpx+xml")})
    n = db.query(TrainingSession).filter(
        TrainingSession.session_date == date(2024, 5, 4)).count()
    assert n == 1, f"{n} Einheiten aus derselben Datei — doppelte TSS in der Formkurve"


# ── 7. Upload ordnet nicht zu (Checkliste 2) ────────────────────────────────

def test_upload_wird_dem_plan_zugeordnet(client, db, tmp_path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    uid = _erster_nutzer(db).id
    tag = date(2024, 5, 7)
    _, (geplant,) = _plan(db, uid, 82, tag - timedelta(days=1), [(tag, "run", 40)])

    antwort = client.post("/api/upload", files={
        "file": ("lauf.gpx", _gpx(str(tag), 40), "application/gpx+xml")}).json()
    s = db.query(TrainingSession).filter(TrainingSession.id == antwort["session_id"]).first()
    db.refresh(geplant)
    assert s.planned_session_id == geplant.id, "Strava-Weg ordnet zu, der Upload nicht"
    assert geplant.status == "completed"


# ── 8. Upload zählt Wochen gegen das Profil, nicht gegen das Ziel (Checkliste 2) ─

def test_upload_wochennummer_wie_beim_strava_import(client, db, tmp_path, monkeypatch):
    from core.config import settings
    from core.deps import get_plan_anchor
    from core.tenancy import acting_as
    from services.plan_generator import get_week_for_date

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    uid = _erster_nutzer(db).id
    ziel = RaceGoal(user_id=uid, sport="triathlon", distance="middle",
                    race_date=date(2024, 12, 1), priority="A", is_active=True,
                    plan_start_date=date(2024, 6, 3), plan_weeks=26)
    db.add(ziel)
    db.commit()
    try:
        antwort = client.post("/api/upload", files={
            "file": ("woche.gpx", _gpx("2024-07-01"), "application/gpx+xml")}).json()
        s = db.query(TrainingSession).filter(TrainingSession.id == antwort["session_id"]).first()
        with acting_as(uid):
            erwartet = get_week_for_date(get_plan_anchor(db), date(2024, 7, 1))
        assert s.week_number == erwartet, f"Upload {s.week_number}, Ingest {erwartet}"
    finally:
        db.delete(ziel)
        db.commit()


# ── 9. Zuordnung über Saisons hinweg (Checkliste 9) ─────────────────────────

def test_alte_saison_behaelt_ihre_vorgabe_nach_zielwechsel(client, db):
    from core.tenancy import acting_as
    from services.classification import classify_session

    uid = _erster_nutzer(db).id
    tag = date(2023, 3, 7)
    _, (alt,) = _plan(db, uid, 83, tag - timedelta(days=1), [(tag, "run", 45)],
                      erzeugt=datetime(2023, 3, 1))
    # Neue Saison: gleiche Wochennummer, später erzeugt.
    _plan(db, uid, 83, date(2026, 9, 7), [(date(2026, 9, 8), "run", 45)])

    lauf = TrainingSession(user_id=uid, session_date=tag, week_number=83,
                           discipline="run", duration_min=45)
    db.add(lauf)
    db.commit()
    with acting_as(uid):
        classify_session(db, lauf)
    assert lauf.planned_session_id == alt.id, "der Plan der neuen Saison verdeckt den alten"


# ── 10. Freigeben setzt „ersetzt" zurück (Checkliste 12) ─────────────────────

def test_loeschen_laesst_ersetzt_markierung_stehen(client, db):
    from core.tenancy import acting_as
    from services.classification import classify_session

    uid = _erster_nutzer(db).id
    tag = date(2023, 2, 14)
    _, (geplant,) = _plan(db, uid, 84, tag - timedelta(days=1), [(tag, "run", 45)])
    geplant.status = "replaced"
    geplant.replacement = "Wandern"
    db.commit()

    lauf = TrainingSession(user_id=uid, session_date=tag, week_number=84,
                           discipline="run", duration_min=45)
    db.add(lauf)
    db.commit()
    with acting_as(uid):
        classify_session(db, lauf)
    assert lauf.planned_session_id == geplant.id

    client.delete(f"/api/history/sessions/{lauf.id}")
    db.refresh(geplant)
    assert geplant.status == "replaced", "die Ersatzangabe des Athleten ist verloren"


# ── 11. Arbeitsweg markieren lässt den Planvergleich stehen (Checkliste 12) ──

def test_arbeitsweg_markieren_entfernt_planvergleich(client, db):
    from core.tenancy import acting_as
    from services.classification import classify_session

    uid = _erster_nutzer(db).id
    tag = date(2023, 1, 17)
    _plan(db, uid, 85, tag - timedelta(days=1), [(tag, "bike", 90)])
    fahrt = TrainingSession(user_id=uid, session_date=tag, week_number=85,
                            discipline="bike", duration_min=25)
    db.add(fahrt)
    db.commit()
    with acting_as(uid):
        classify_session(db, fahrt)
    assert "Dauer" in (fahrt.deviation_note or "")

    client.patch(f"/api/history/sessions/{fahrt.id}/commute", params={"is_commute": True})
    db.refresh(fahrt)
    assert fahrt.planned_session_id is None
    assert "statt 90" not in (fahrt.deviation_note or ""), (
        f"Notiz vergleicht weiter mit einer Vorgabe, die nicht mehr gilt: {fahrt.deviation_note}"
    )


# ── 12. Fremdes Frontmatter geht beim Merge verloren (Checkliste 13) ────────

def test_merge_behaelt_mehrzeiliges_fremdes_frontmatter():
    from services.obsidian.notes import MARKER_END, MARKER_START, merge_note

    vorher = (
        "---\n"
        "date: 2024-01-01\n"
        "aliases:\n"
        "  - Lange Ausfahrt\n"
        "  - Rennrad\n"
        "---\n\n"
        f"{MARKER_START}\nalt\n{MARKER_END}\n\n## Reflexion\n\ngut\n"
    )
    nachher = merge_note(vorher, {"session_date": date(2024, 1, 1), "discipline": "bike"})
    assert "  - Lange Ausfahrt" in nachher, nachher.split("---")[1]


# ── 13. Geschätzte Strava-Watt gelten als Messung (Checkliste 3) ────────────

def test_geschaetzte_watt_werden_nicht_als_leistungsquelle_ausgewiesen():
    from services.strava_service import StravaService

    daten = StravaService(None).map_strava_to_session(
        {"id": 1, "sport_type": "Ride", "start_date_local": "2024-06-01T08:00:00Z",
         "moving_time": 3600, "distance": 30000, "average_watts": 150.0,
         "device_watts": False, "average_heartrate": 140},
        {}, 250, 1, hr_zone_bounds={"z1_max": 130, "z2_max": 160, "z3_max": 170,
                                     "z4_max": 180, "threshold_hr": 170},
    )
    # TSS stammt aus dem Puls (keine NP) ...
    assert daten["normalized_power"] is None and daten["tss"] is not None
    # ... die geschätzten Watt landen aber als Messwert in der Einheit und
    # werden in Prompt und Abweichungsnotiz gegen Zielbänder gestellt.
    assert daten["avg_watts"] is None, "Stravas Schätzung (device_watts=false) als Messung gespeichert"
