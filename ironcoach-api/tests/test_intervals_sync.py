"""Abgleich der geplanten Läufe und Radeinheiten mit dem intervals.icu-Kalender.

intervals.icu wird über `httpx.MockTransport` als kleiner Kalender im
Speicher nachgestellt (`respx` ist bewusst nicht installiert, wie bei Garmin).
Jeder Test arbeitet mit eigenen Athleten. Ein Zugang auf dem Testnutzer, auf
den Anfragen ohne Anmeldung zurückfallen, ließe sonst in anderen Testdateien
jede Planänderung einen Abgleich anstoßen.
"""

import ast
import asyncio
import json
import pathlib
import uuid
from datetime import date, timedelta

import httpx
import pytest

from core.wochen import montag_von
from models import AthleteProfile, PlannedSession, User, WeeklyPlan
from services import intervals_icu
from services.intervals_sync import (
    FEHLER_ZUGANG, abgleichen, anstossen, woche_abgleichen,
)

HEUTE = date.today()
MONTAG = montag_von(HEUTE + timedelta(days=7))   # kommende Woche, ganz in der Zukunft
SCHLUESSEL = "geheimerschluessel123"


class Kalender:
    """intervals.icu im Speicher: Events je Athlet, mit Aufrufprotokoll."""

    def __init__(self, ablehnen: bool = False, mit_kennung: bool = True, langsam: float = 0.0):
        self.events: dict[int, dict] = {}
        self.naechste = 100
        self.aufrufe: list[str] = []
        self.ablehnen = ablehnen
        self.mit_kennung = mit_kennung
        # Verzögert das Lesen, damit zwei Abgleiche sicher ineinanderlaufen.
        self.langsam = langsam

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.aufrufe.append(f"{request.method} {request.url.path}")
        if self.ablehnen:
            return httpx.Response(401, text=f"bad key {SCHLUESSEL}")
        teile = request.url.path.strip("/").split("/")   # api v1 athlete <id> events [<eid>]
        if teile[-1] == "events" and request.method == "GET":
            if self.langsam:
                import time
                time.sleep(self.langsam)
            von, bis = request.url.params["oldest"], request.url.params["newest"]
            treffer = [
                {k: v for k, v in e.items() if self.mit_kennung or k != "external_id"}
                for e in self.events.values()
                if von <= e["start_date_local"][:10] <= bis
            ]
            return httpx.Response(200, json=treffer)
        if teile[-1] == "events" and request.method == "POST":
            event = json.loads(request.content)
            event["id"] = self.naechste
            self.naechste += 1
            self.events[event["id"]] = event
            return httpx.Response(200, json=event)
        if teile[-2] == "events" and request.method == "PUT":
            eid = int(teile[-1])
            self.events[eid] = {**json.loads(request.content), "id": eid}
            return httpx.Response(200, json=self.events[eid])
        if teile[-2] == "events" and request.method == "DELETE":
            if self.events.pop(int(teile[-1]), None) is None:
                return httpx.Response(404)
            return httpx.Response(200, json={})
        if teile[-2] == "athlete" and request.method == "GET":
            return httpx.Response(200, json={"id": teile[-1], "name": "Test"})
        return httpx.Response(404)

    def transport(self):
        return httpx.MockTransport(self)

    def am(self, tag: date) -> list[dict]:
        return [e for e in self.events.values() if e["start_date_local"].startswith(tag.isoformat())]


def _nutzer(db, verbunden: bool = True) -> User:
    u = User(email=f"intervals-{uuid.uuid4().hex[:8]}@example.invalid", name="Intervals-Test")
    db.add(u)
    db.commit()
    felder = dict(intervals_athlete_id="i4711", intervals_api_key=SCHLUESSEL) if verbunden else {}
    db.add(AthleteProfile(user_id=u.id, name="Intervals-Test", **felder))
    db.commit()
    return u


def _plan(db, u, einheiten: list[dict]) -> WeeklyPlan:
    plan = WeeklyPlan(user_id=u.id, week_number=1, week_start=MONTAG,
                      week_end=MONTAG + timedelta(days=6), plan_content={"days": []})
    db.add(plan)
    db.commit()
    for i, felder in enumerate(einheiten):
        werte = dict(user_id=u.id, plan_id=plan.id, week_number=1, planned_date=MONTAG,
                     discipline="run", duration_min=40, day_index=i)
        werte.update(felder)
        db.add(PlannedSession(**werte))
    db.commit()
    return plan


def _laeufe(db, u) -> list[PlannedSession]:
    # Von Hand nach Nutzer: Der Mandantenfilter hängt erst nach dem App-Start.
    return (db.query(PlannedSession)
            .filter(PlannedSession.user_id == u.id, PlannedSession.discipline == "run")
            .order_by(PlannedSession.planned_date).all())


def _abgleich(db, u, kalender, montag=MONTAG, heute=HEUTE):
    return asyncio.run(woche_abgleichen(db, u.id, montag, transport=kalender.transport(), heute=heute))


def _profil(db, u) -> AthleteProfile:
    db.expire_all()
    return db.query(AthleteProfile).filter(AthleteProfile.user_id == u.id).first()


def test_anlegen_und_unveraendert_beim_zweiten_mal(db):
    u = _nutzer(db)
    _plan(db, u, [
        {"details": {"typ": "Dauerlauf Z2", "dauer": "40 min", "pace": "6:00–6:30/km"}},
        {"discipline": "bike", "planned_date": MONTAG + timedelta(days=1), "duration_min": 90,
         "training_type": "z2_endurance", "target_watts_low": 150, "target_watts_high": 170},
        {"discipline": "swim", "planned_date": MONTAG + timedelta(days=2), "duration_min": 45},
    ])
    kalender = Kalender()
    erstes = _abgleich(db, u, kalender)
    # Lauf und Rad, Schwimmen nicht: Geschickt wird nur, was Amir wollte.
    assert erstes["angelegt"] == 2, erstes
    (lauf,) = kalender.am(MONTAG)
    assert lauf["category"] == "WORKOUT" and lauf["type"] == "Run"
    assert lauf["start_date_local"] == f"{MONTAG.isoformat()}T00:00:00"
    assert lauf["description"] == "Main Set\n- 40m 6:00-6:30/km Pace"
    assert lauf["external_id"] == f"forge-{u.id}-{MONTAG.isoformat()}-1"
    (rad,) = kalender.am(MONTAG + timedelta(days=1))
    assert rad["type"] == "Ride" and rad["description"] == "Main Set\n- 90m 150-170w"

    zweiter = _abgleich(db, u, kalender)
    assert zweiter["angelegt"] == 0 and zweiter["unveraendert"] == 2
    assert _profil(db, u).intervals_letzter_abgleich is not None


def test_brick_wird_zu_rad_und_lauf(db):
    u = _nutzer(db)
    _plan(db, u, [{"discipline": "brick", "duration_min": 105, "details": {
        "bike": {"workout": "Koppel Z2", "dauer": "90 min", "watt": "150–170 W"},
        "run": {"typ": "Koppellauf", "dauer": "15 min", "pace": "5:30–5:50/km"},
    }}])
    kalender = Kalender()
    assert _abgleich(db, u, kalender)["angelegt"] == 2
    rad, lauf = sorted(kalender.am(MONTAG), key=lambda e: e["external_id"])
    assert (rad["type"], lauf["type"]) == ("Ride", "Run")
    assert rad["description"] == "Main Set\n- 90m 150-170w"
    assert lauf["description"] == "Main Set\n- 15m 5:30-5:50/km Pace"


def test_verschieben_wandert_mit_und_fremde_events_bleiben(db):
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "Dauerlauf", "dauer": "30 min"}}])
    kalender = Kalender()
    # Ein eigenes Workout des Athleten am selben Tag, nicht von FORGE.
    kalender.events[1] = {"id": 1, "category": "WORKOUT", "name": "Mein Workout",
                          "start_date_local": f"{MONTAG.isoformat()}T00:00:00"}
    _abgleich(db, u, kalender)

    # Wie Drag & Drop: neues Datum, Status "moved".
    lauf = _laeufe(db, u)[0]
    lauf.moved_from_date, lauf.planned_date, lauf.status = lauf.planned_date, MONTAG + timedelta(days=2), "moved"
    db.commit()

    ergebnis = _abgleich(db, u, kalender)
    assert ergebnis["angelegt"] == 1 and ergebnis["geloescht"] == 1
    assert [e["name"] for e in kalender.am(MONTAG)] == ["Mein Workout"]
    assert len(kalender.am(MONTAG + timedelta(days=2))) == 1


def test_erkennt_eigene_events_auch_ohne_external_id(db):
    """Liefert intervals.icu die Kennung nicht zurück, entstehen keine Dubletten."""
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "Dauerlauf", "dauer": "30 min"}}])
    kalender = Kalender(mit_kennung=False)
    _abgleich(db, u, kalender)
    zweiter = _abgleich(db, u, kalender)
    assert zweiter["angelegt"] == 0 and len(kalender.events) == 1


def test_zwei_abgleiche_zugleich_legen_nur_ein_workout_an(db):
    """Verbinden und gleich danach „Sync now": ohne Sperre lasen beide eine
    leere Woche und legten beide an."""
    import threading

    from sqlalchemy.orm import sessionmaker

    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender(langsam=0.2)
    neue_sitzung = sessionmaker(bind=db.get_bind())

    def lauf():
        eigene = neue_sitzung()
        try:
            abgleichen(eigene, u.id, [MONTAG], transport=kalender.transport())
        finally:
            eigene.close()

    faeden = [threading.Thread(target=lauf) for _ in range(2)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(timeout=10)
    assert len(kalender.events) == 1


def test_dublette_wird_abgeraeumt(db):
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender()
    _abgleich(db, u, kalender)
    (erstes,) = kalender.events.values()
    # Wie aus einem zweiten Prozess: dasselbe Event noch einmal.
    kalender.events[999] = {**erstes, "id": 999}
    ergebnis = _abgleich(db, u, kalender)
    assert ergebnis["geloescht"] == 1 and list(kalender.events) == [erstes["id"]]


def test_ersetzt_gestrichen_und_vergangen(db):
    u = _nutzer(db)
    _plan(db, u, [
        {"details": {"typ": "A", "dauer": "30 min"}, "planned_date": MONTAG},
        {"details": {"typ": "B", "dauer": "30 min"}, "planned_date": MONTAG + timedelta(days=3)},
    ])
    kalender = Kalender()
    _abgleich(db, u, kalender)
    assert len(kalender.events) == 2

    b = [p for p in _laeufe(db, u) if p.planned_date == MONTAG + timedelta(days=3)][0]
    b.status, b.replacement = "replaced", "Wandern"
    db.commit()
    # Aus Sicht von Mittwoch: Montag ist vorbei und bleibt unangetastet.
    ergebnis = _abgleich(db, u, kalender, heute=MONTAG + timedelta(days=2))
    assert ergebnis["geloescht"] == 1
    assert len(kalender.am(MONTAG)) == 1 and not kalender.am(MONTAG + timedelta(days=3))


def test_erledigter_lauf_bleibt_stehen(db):
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender()
    _abgleich(db, u, kalender, heute=MONTAG)
    lauf = _laeufe(db, u)[0]
    lauf.status = "completed"
    db.commit()
    ergebnis = _abgleich(db, u, kalender, heute=MONTAG)
    assert ergebnis["geloescht"] == 0 and len(kalender.events) == 1


def test_nur_eigene_laeufe(db):
    u, fremd = _nutzer(db), _nutzer(db)
    _plan(db, u, [{"details": {"typ": "Meiner", "dauer": "30 min"}}])
    _plan(db, fremd, [{"details": {"typ": "Fremder", "dauer": "50 min"}}])
    kalender = Kalender()
    _abgleich(db, u, kalender)
    assert [e["name"] for e in kalender.events.values()] == ["FORGE · Meiner"]


def test_abgelehnter_zugang_kippt_nichts_und_verraet_nichts(db):
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    ergebnis = _abgleich(db, u, Kalender(ablehnen=True))
    assert ergebnis["fehler"] == FEHLER_ZUGANG
    profil = _profil(db, u)
    assert profil.intervals_letzter_fehler == FEHLER_ZUGANG
    assert SCHLUESSEL not in profil.intervals_letzter_fehler


def test_ohne_zugang_kein_aufruf(db, monkeypatch):
    u = _nutzer(db, verbunden=False)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender()
    assert _abgleich(db, u, kalender)["uebersprungen"] == "nicht verbunden"
    monkeypatch.setattr(intervals_icu, "STANDARD_TRANSPORT", kalender.transport())
    assert anstossen(db, u.id, [MONTAG]) is None
    assert kalender.aufrufe == []


def test_anstossen_im_hintergrund_auf_derselben_datenbank(db, monkeypatch):
    u = _nutzer(db)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender()
    monkeypatch.setattr(intervals_icu, "STANDARD_TRANSPORT", kalender.transport())
    faden = anstossen(db, u.id, [MONTAG, MONTAG + timedelta(days=3)])
    assert faden is not None
    faden.join(timeout=10)
    # Zwei Tage derselben Woche: ein Abgleich, ein Event.
    assert len(kalender.events) == 1


def test_verbinden_und_trennen_raeumt_auf(client, db, monkeypatch):
    from core.security import create_access_token

    u = _nutzer(db, verbunden=False)
    _plan(db, u, [{"details": {"typ": "A", "dauer": "30 min"}}])
    kalender = Kalender()
    monkeypatch.setattr(intervals_icu, "STANDARD_TRANSPORT", kalender.transport())
    # Den Faden nach dem Verbinden abschalten, der Test gleicht selbst ab.
    # Sonst liefen beide zugleich und legten dasselbe Event zweimal an.
    import services.intervals_sync as sync
    monkeypatch.setattr(sync, "anstossen", lambda *a, **k: None)
    kopf = {"Authorization": f"Bearer {create_access_token(u.id, u.email)}"}

    antwort = client.put("/api/integrations/intervals", headers=kopf,
                         json={"athlete_id": "i4711", "api_key": f"  {SCHLUESSEL}​"})
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert daten["intervals"]["configured"] and daten["intervals"]["weg"] == "schluessel"
    assert SCHLUESSEL not in antwort.text

    # Den Abgleich direkt laufen lassen statt auf den Faden zu warten.
    asyncio.run(woche_abgleichen(db, u.id, MONTAG, transport=kalender.transport()))
    assert len(kalender.events) == 1

    antwort = client.delete("/api/integrations/intervals", headers=kopf)
    assert antwort.status_code == 200
    assert antwort.json()["aufgeraeumt"] is True
    assert kalender.events == {}
    assert _profil(db, u).intervals_api_key is None


def test_falsche_athleten_id_wird_abgewiesen(client, db):
    from core.security import create_access_token

    u = _nutzer(db, verbunden=False)
    kopf = {"Authorization": f"Bearer {create_access_token(u.id, u.email)}"}
    antwort = client.put("/api/integrations/intervals", headers=kopf,
                         json={"athlete_id": "../../admin", "api_key": SCHLUESSEL})
    assert antwort.status_code == 422


# --- Kreuzprobe: jede Projektion stößt den Abgleich an ------------------------

# Ausnahmen mit Grund. Die Nachprojektion aller Pläne ist Wartung und betrifft
# fast nur vergangene Wochen.
AUSNAHMEN = {("services/plan_projection.py", "backfill_all")}


def _funktionen_mit_aufruf(quelle: str, name: str):
    baum = ast.parse(quelle)
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
            aufrufe = {
                (k.func.id if isinstance(k.func, ast.Name) else getattr(k.func, "attr", None))
                for k in ast.walk(knoten) if isinstance(k, ast.Call)
            }
            yield knoten.name, aufrufe


def test_jede_projektion_stoesst_den_abgleich_an():
    wurzel = pathlib.Path(__file__).resolve().parents[1]
    fehlend = []
    for datei in list((wurzel / "services").rglob("*.py")) + list((wurzel / "routers").glob("*.py")):
        relativ = str(datei.relative_to(wurzel))
        for name, aufrufe in _funktionen_mit_aufruf(datei.read_text(), "project_plan"):
            if name == "project_plan" or "project_plan" not in aufrufe:
                continue
            if (relativ, name) in AUSNAHMEN:
                continue
            if "anstossen" not in aufrufe:
                fehlend.append(f"{relativ}:{name}")
    assert not fehlend, f"project_plan ohne intervals-Abgleich: {fehlend}"
