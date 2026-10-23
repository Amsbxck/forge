"""HRV automatisch aus Garmin Connect (Personal API).

Garmin wird über `httpx.MockTransport` nachgestellt: `respx` ist bewusst nicht
installiert. Die Antwortformen sind am 23.10.2026 mit einem echten Schlüssel
geprüft: Das Token kommt als `text/plain`, direkt das JWT ohne
Anführungszeichen, und `Accept: application/json` beim Tausch ergibt 406. Die
HRV-Antwort ist `{"hrvSummaries": [...], "userProfilePk": …}` mit den Feldern
aus der Aufgabe plus `feedbackPhrase` und `createTimeStamp`.

Die meisten Tests arbeiten mit eigenen Athleten statt mit dem Testnutzer, auf
den Anfragen ohne Anmeldung zurückfallen. Ein auf dessen Profil vergessener
Garmin-Schlüssel ließe sonst `POST /hrv` in anderen Testdateien mit 409
scheitern. Wo ein Test über den Router gehen muss, stellt `rueckfallprofil`
den Zustand danach wieder her.
"""

import asyncio
import json
import uuid
from datetime import date, timedelta

import httpx
import pytest

from models import AthleteProfile, HrvMeasurement, User
from services import garmin_personal
from services.garmin_hrv import abgleich_fuer, spanne_uebernehmen, tage_uebernehmen
from services.garmin_personal import (
    GarminAntwortUnerwartet, GarminNichtErreichbar, GarminRateLimit,
    GarminSchluesselUngueltig,
)
from services.hrv_baseline import red_from_band, thresholds_for

HEUTE = date.today()


def _nutzer(db, email: str, **profilfelder) -> User:
    u = User(email=email, name="Garmin-Test")
    db.add(u)
    db.commit()
    db.add(AthleteProfile(user_id=u.id, name="Garmin-Test", **profilfelder))
    db.commit()
    return u


def _profil(db, user: User) -> AthleteProfile:
    db.expire_all()
    return db.query(AthleteProfile).filter(AthleteProfile.user_id == user.id).first()


def _messungen(db, user: User) -> list[HrvMeasurement]:
    db.expire_all()
    return (
        db.query(HrvMeasurement)
        .filter(HrvMeasurement.user_id == user.id)
        .order_by(HrvMeasurement.measured_at.asc(), HrvMeasurement.id.asc())
        .all()
    )


def _summary(tag: date, wert=81, status="BALANCED", baseline=True) -> dict:
    s = {
        "calendarDate": tag.isoformat(),
        "weeklyAvg": 78,
        "lastNightAvg": wert,
        "lastNight5MinHigh": 104,
        "status": status,
        # Live gesehen, hier nicht gebraucht: Sie dürfen nichts stören.
        "feedbackPhrase": "HRV_BALANCED_1",
        "createTimeStamp": f"{tag.isoformat()}T05:12:33.0",
    }
    if baseline:
        s["baseline"] = {"lowUpper": 62, "balancedLow": 70, "balancedUpper": 92, "markerValue": 0.4}
    return s


class Garmin:
    """Ein nachgestelltes Garmin: Schlüssel → Token → Summaries je Athlet.

    Antwortet je Token mit eigenen Daten, damit sich prüfen lässt, dass die
    Werte eines Athleten nicht bei einem anderen landen.
    """

    def __init__(self, daten_je_schluessel: dict[str, list[dict]], status_hrv: int = 200):
        self.daten = daten_je_schluessel
        self.status_hrv = status_hrv
        self.anfragen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.anfragen.append(request)
        auth = request.headers.get("Authorization", "")
        if request.url.path == garmin_personal.TOKEN_PFAD:
            assert request.method == "POST"
            # Wie live beobachtet: Wer beim Tausch JSON verlangt, bekommt 406.
            if "application/json" in request.headers.get("Accept", ""):
                return httpx.Response(406)
            schluessel = auth.removeprefix("ApiKey ")
            if not auth.startswith("ApiKey ") or schluessel not in self.daten:
                return httpx.Response(401, text=f"invalid key {schluessel}")
            # Wie live beobachtet: das JWT direkt als text/plain.
            return httpx.Response(200, text=f"tok.{schluessel}.sig",
                                  headers={"Content-Type": "text/plain"})
        if request.url.path.startswith("/hrv-service/hrv/daily/"):
            assert auth.startswith("Bearer tok.")
            if self.status_hrv != 200:
                return httpx.Response(self.status_hrv, headers={"Retry-After": "120"})
            schluessel = auth.removeprefix("Bearer tok.").removesuffix(".sig")
            return httpx.Response(200, json={
                "userProfilePk": 1, "hrvSummaries": self.daten[schluessel],
            })
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def rueckfallprofil(db):
    """Das Profil des Nutzers, auf den Anfragen ohne Anmeldung fallen.

    Garmin- und Spannenfelder werden danach zurückgesetzt und die im Test
    entstandenen HRV-Zeilen entfernt. Das ist Aufräumen im Test, kein
    automatisches Löschen in der App.
    """
    nutzer = db.query(User).order_by(User.id.asc()).first()
    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    felder = [
        "garmin_api_key", "garmin_verbunden_am", "garmin_letzter_abruf", "garmin_letzter_fehler",
        "hrv_green_min", "hrv_band_high", "hrv_red_below", "hrv_range_source",
    ]
    vorher = {f: getattr(profil, f) for f in felder}
    vorhandene_ids = {
        m.id for m in db.query(HrvMeasurement).filter(HrvMeasurement.user_id == nutzer.id)
    }
    yield nutzer, profil
    db.rollback()
    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    for f, wert in vorher.items():
        setattr(profil, f, wert)
    for m in db.query(HrvMeasurement).filter(HrvMeasurement.user_id == nutzer.id).all():
        if m.id not in vorhandene_ids:
            db.delete(m)
    db.commit()


# --- Client (garmin_personal) ------------------------------------------------

def test_token_als_text_und_als_json():
    """Live (23.10.2026): text/plain, direkt das JWT. JSON nur zur Sicherheit."""
    def text(req):
        # Ohne JSON-Accept, sonst antwortet Garmin mit 406.
        if "application/json" in req.headers.get("Accept", ""):
            return httpx.Response(406)
        return httpx.Response(200, text="abc.def.ghi\n", headers={"Content-Type": "text/plain"})

    def als_json(req):
        return httpx.Response(200, json={"access_token": "xyz.uvw.rst", "expires_in": 86400})

    assert asyncio.run(garmin_personal.token_holen("k", transport=httpx.MockTransport(text))) == "abc.def.ghi"
    assert asyncio.run(garmin_personal.token_holen("k", transport=httpx.MockTransport(als_json))) == "xyz.uvw.rst"


def test_token_fehler_enthalten_den_schluessel_nicht():
    """Garmin könnte den Schlüssel im Fehlertext zurückspiegeln. Der darf in
    keiner Meldung landen, die ins Protokoll oder in die Kachel geht."""
    def abgelehnt(req):
        return httpx.Response(401, text="bad key GEHEIM-123")

    with pytest.raises(GarminSchluesselUngueltig) as fehler:
        asyncio.run(garmin_personal.token_holen("GEHEIM-123", transport=httpx.MockTransport(abgelehnt)))
    assert "GEHEIM" not in str(fehler.value)


def test_leere_token_antwort_ist_unerwartet():
    def leer(req):
        return httpx.Response(200, text="")

    with pytest.raises(GarminAntwortUnerwartet):
        asyncio.run(garmin_personal.token_holen("k", transport=httpx.MockTransport(leer)))


def test_ohne_lesbaren_schluessel_wird_garmin_nicht_gefragt():
    def nie(req):  # pragma: no cover - darf nicht aufgerufen werden
        raise AssertionError("Garmin gefragt mit leerem Schlüssel")

    with pytest.raises(GarminSchluesselUngueltig):
        asyncio.run(garmin_personal.token_holen(None, transport=httpx.MockTransport(nie)))


@pytest.mark.parametrize("schluessel", ["ABC\u00fcDEF", "ABC\u200bDEF", "ABC DEF", "\u200b"])
def test_unzulaessige_zeichen_gehen_nicht_an_garmin(schluessel):
    """Ein „ü" oder U+200B ließ httpx mit einem UnicodeEncodeError abbrechen,
    dessen Text den vollen Schlüssel trug. Jetzt wird vorher abgelehnt."""
    def nie(req):  # pragma: no cover - darf nicht aufgerufen werden
        raise AssertionError("Garmin gefragt mit unzulässigem Schlüssel")

    with pytest.raises(GarminSchluesselUngueltig) as fehler:
        asyncio.run(garmin_personal.token_holen(schluessel, transport=httpx.MockTransport(nie)))
    assert "ABC" not in str(fehler.value)


def test_nullbreiten_zeichen_am_rand_werden_entfernt():
    gesehen = []

    def handler(req):
        gesehen.append(req.headers["Authorization"])
        return httpx.Response(200, text="a.b.c", headers={"Content-Type": "text/plain"})

    roh = "\ufeff\u200b KEY-123 \u200d\n"
    assert garmin_personal.schluessel_bereinigen(roh) == "KEY-123"
    asyncio.run(garmin_personal.token_holen(roh, transport=httpx.MockTransport(handler)))
    assert gesehen == ["ApiKey KEY-123"]


@pytest.mark.parametrize("antwort, erwartet", [
    (httpx.Response(204), []),
    (httpx.Response(200, json={"userProfilePk": 1}), []),
    (httpx.Response(200, json={"userProfilePk": 1, "hrvSummaries": None}), []),
    (httpx.Response(200, json={"hrvSummaries": [{"calendarDate": "2026-10-23"}, 5, "x"]}),
     [{"calendarDate": "2026-10-23"}]),
])
def test_hrv_antwort_defensiv(antwort, erwartet):
    transport = httpx.MockTransport(lambda req: antwort)
    tage = asyncio.run(garmin_personal.hrv_tage("t", HEUTE - timedelta(days=7), HEUTE, transport=transport))
    assert tage == erwartet


@pytest.mark.parametrize("status, art", [
    (401, GarminSchluesselUngueltig),
    (403, GarminSchluesselUngueltig),
    (429, GarminRateLimit),
    (500, GarminNichtErreichbar),
    (503, GarminNichtErreichbar),
    (400, GarminAntwortUnerwartet),
])
def test_hrv_status_wird_uebersetzt(status, art):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, headers={"Retry-After": "90"}))
    with pytest.raises(art) as fehler:
        asyncio.run(garmin_personal.hrv_tage("t", HEUTE, HEUTE, transport=transport))
    if art is GarminRateLimit:
        assert fehler.value.retry_after == 90


def test_netzfehler_ist_nicht_erreichbar():
    def kaputt(req):
        raise httpx.ConnectError("keine Verbindung", request=req)

    with pytest.raises(GarminNichtErreichbar):
        asyncio.run(garmin_personal.token_holen("k", transport=httpx.MockTransport(kaputt)))


def test_hrv_pfad_und_bearer():
    gesehen = []

    def handler(req):
        gesehen.append(req)
        return httpx.Response(200, json={"hrvSummaries": []})

    asyncio.run(garmin_personal.hrv_tage(
        "tok", date(2026, 10, 16), date(2026, 10, 23), transport=httpx.MockTransport(handler)))
    assert gesehen[0].url.path == "/hrv-service/hrv/daily/2026-10-16/2026-10-23"
    assert gesehen[0].headers["Authorization"] == "Bearer tok"
    assert gesehen[0].headers["Accept"] == "application/json"
    assert gesehen[0].url.host == "personal.connectapi.garmin.com"


# --- tage_uebernehmen --------------------------------------------------------

def test_ein_tag_wird_zur_garmin_messung_mit_status(db):
    u = _nutzer(db, "garmin-tag@example.invalid", hrv_range_source="garmin",
                hrv_green_min=70, hrv_band_high=92, hrv_red_below=red_from_band(70, 92))
    ergebnis = tage_uebernehmen(db, u, [_summary(HEUTE, 81)])
    assert ergebnis == {"neu": 1, "aktualisiert": 0, "ohne_daten": 0}
    [m] = _messungen(db, u)
    assert m.measured_at == HEUTE
    assert m.rmssd == 81
    assert m.quelle == "garmin"
    assert m.hrv_status == "green"


def test_zweiter_lauf_aendert_nichts(db):
    u = _nutzer(db, "garmin-idem@example.invalid")
    tage = [_summary(HEUTE - timedelta(days=i), 70 + i) for i in range(5)]
    assert tage_uebernehmen(db, u, tage)["neu"] == 5
    vorher = [(m.id, m.rmssd, m.quelle, m.hrv_status) for m in _messungen(db, u)]

    zweiter = tage_uebernehmen(db, u, tage)
    assert zweiter == {"neu": 0, "aktualisiert": 0, "ohne_daten": 0}
    assert [(m.id, m.rmssd, m.quelle, m.hrv_status) for m in _messungen(db, u)] == vorher


def test_derselbe_tag_doppelt_in_der_antwort_legt_eine_zeile_an(db):
    u = _nutzer(db, "garmin-doppelt-antwort@example.invalid")
    ergebnis = tage_uebernehmen(db, u, [_summary(HEUTE, 80), _summary(HEUTE, 80)])
    assert ergebnis["neu"] == 1
    assert len(_messungen(db, u)) == 1


def test_manueller_wert_wird_ueberschrieben_zweite_zeile_bleibt(db):
    """Garmin ist die Quelle. Gelöscht wird aber nichts: Bei Tagen mit zwei
    Zeilen (gibt es in Bestandsdaten) wird nur die erste angepasst."""
    u = _nutzer(db, "garmin-manuell@example.invalid")
    gestern = HEUTE - timedelta(days=1)
    erste = HrvMeasurement(user_id=u.id, measured_at=gestern, rmssd=60, quelle="manual",
                           readiness_score=55, notes="von Hand")
    db.add(erste)
    db.commit()
    zweite = HrvMeasurement(user_id=u.id, measured_at=gestern, rmssd=62)
    altdaten = HrvMeasurement(user_id=u.id, measured_at=HEUTE, rmssd=77)  # quelle NULL
    db.add_all([zweite, altdaten])
    db.commit()

    ergebnis = tage_uebernehmen(db, u, [_summary(gestern, 84), _summary(HEUTE, 79)])
    assert ergebnis == {"neu": 0, "aktualisiert": 2, "ohne_daten": 0}

    nach = {m.id: m for m in _messungen(db, u)}
    assert len(nach) == 3
    assert (nach[erste.id].rmssd, nach[erste.id].quelle) == (84, "garmin")
    # Was Garmin nicht kennt, bleibt: Notiz und Body Battery des Athleten.
    assert nach[erste.id].notes == "von Hand"
    assert nach[erste.id].readiness_score == 55
    assert (nach[zweite.id].rmssd, nach[zweite.id].quelle) == (62, None)
    assert (nach[altdaten.id].rmssd, nach[altdaten.id].quelle) == (79, "garmin")


@pytest.mark.parametrize("summary", [
    _summary(HEUTE, 80, status="NONE"),
    _summary(HEUTE, 80, status="INVALID"),
    _summary(HEUTE, None),
    _summary(HEUTE, 0),
    _summary(HEUTE, "81"),
    {"calendarDate": HEUTE.isoformat()},
    {"lastNightAvg": 80, "status": "BALANCED"},
    {"calendarDate": "kein-datum", "lastNightAvg": 80},
])
def test_ohne_gueltigen_wert_wird_nichts_angelegt(db, summary):
    u = _nutzer(db, f"garmin-leer-{uuid.uuid4().hex}@example.invalid")
    ergebnis = tage_uebernehmen(db, u, [summary])
    assert ergebnis == {"neu": 0, "aktualisiert": 0, "ohne_daten": 1}
    assert _messungen(db, u) == []


# --- spanne_uebernehmen ------------------------------------------------------

def test_spanne_kommt_aus_garmins_baseline_und_bewertet_neu(db):
    u = _nutzer(db, "garmin-spanne@example.invalid")
    # Zwei alte Messungen ohne Ampel: zu wenige für eine berechnete Spanne.
    db.add_all([
        HrvMeasurement(user_id=u.id, measured_at=HEUTE - timedelta(days=10), rmssd=50),
        HrvMeasurement(user_id=u.id, measured_at=HEUTE - timedelta(days=9), rmssd=85),
    ])
    db.commit()
    assert all(m.hrv_status is None for m in _messungen(db, u))

    aelter = _summary(HEUTE - timedelta(days=1))
    aelter["baseline"] = {"balancedLow": 60, "balancedUpper": 80}
    juengste = _summary(HEUTE)  # 70–92
    # Bewusst die jüngste zuerst: Gewählt wird nach Datum, nicht nach Reihenfolge.
    assert spanne_uebernehmen(db, u, [juengste, aelter]) is True

    p = _profil(db, u)
    assert p.hrv_green_min == 70
    assert p.hrv_band_high == 92
    assert p.hrv_red_below == red_from_band(70, 92)
    assert p.hrv_range_source == "garmin"
    farben = [m.hrv_status for m in _messungen(db, u)]
    assert farben == ["red", "green"], "alte Messungen nach der neuen Spanne bewertet"


def test_ohne_baseline_bleibt_die_spanne(db):
    u = _nutzer(db, "garmin-lernphase@example.invalid", hrv_range_source="manual",
                hrv_green_min=65, hrv_band_high=100, hrv_red_below=56.2)
    ohne = [
        _summary(HEUTE, baseline=False),
        {**_summary(HEUTE - timedelta(days=1)), "baseline": None},
        {**_summary(HEUTE - timedelta(days=2)), "baseline": {"balancedLow": None, "balancedUpper": 90}},
        {**_summary(HEUTE - timedelta(days=3)), "baseline": {"balancedLow": 90, "balancedUpper": 80}},
    ]
    assert spanne_uebernehmen(db, u, ohne) is False
    p = _profil(db, u)
    assert (p.hrv_green_min, p.hrv_band_high, p.hrv_red_below, p.hrv_range_source) == (65, 100, 56.2, "manual")


# --- abgleich_fuer -----------------------------------------------------------

def test_401_beim_token_setzt_fehler_und_behaelt_schluessel(db):
    u = _nutzer(db, "garmin-401@example.invalid", garmin_api_key="ABGELAUFEN-9876")
    garmin = Garmin({})  # kennt keinen Schlüssel
    ergebnis = asyncio.run(abgleich_fuer(db, u, transport=garmin.transport))
    assert ergebnis["ok"] is False

    p = _profil(db, u)
    assert p.garmin_api_key == "ABGELAUFEN-9876", "Schlüssel nicht löschen"
    assert p.garmin_letzter_fehler
    assert "ungültig oder abgelaufen" in p.garmin_letzter_fehler
    assert "9876" not in p.garmin_letzter_fehler
    assert p.garmin_letzter_abruf is None


def test_erfolg_setzt_letzten_abruf_und_leert_fehler(db):
    u = _nutzer(db, "garmin-ok@example.invalid", garmin_api_key="K-OK",
                garmin_letzter_fehler="alter Fehler")
    garmin = Garmin({"K-OK": [_summary(HEUTE, 80), _summary(HEUTE - timedelta(days=1), 75)]})
    ergebnis = asyncio.run(abgleich_fuer(db, u, tage=7, mit_spanne=True, transport=garmin.transport))
    assert ergebnis == {"ok": True, "neu": 2, "aktualisiert": 0, "ohne_daten": 0,
                        "spanne_uebernommen": True}

    p = _profil(db, u)
    assert p.garmin_letzter_fehler is None
    assert p.garmin_letzter_abruf is not None
    assert p.hrv_range_source == "garmin"
    # Ein Token, ein HRV-Abruf über 7 Tage — kein zweiter Aufruf für die Spanne.
    pfade = [r.url.path for r in garmin.anfragen]
    assert pfade == [
        garmin_personal.TOKEN_PFAD,
        f"/hrv-service/hrv/daily/{(HEUTE - timedelta(days=7)).isoformat()}/{HEUTE.isoformat()}",
    ]


def test_429_setzt_festen_text(db):
    u = _nutzer(db, "garmin-429@example.invalid", garmin_api_key="K-429")
    garmin = Garmin({"K-429": []}, status_hrv=429)
    ergebnis = asyncio.run(abgleich_fuer(db, u, transport=garmin.transport))
    assert ergebnis["ok"] is False
    assert "bremst" in _profil(db, u).garmin_letzter_fehler


# --- Morgen-Job und Mandanten ------------------------------------------------

def test_job_fuer_a_schreibt_nichts_bei_b(db, monkeypatch):
    """Je Athlet eine eigene Session in `acting_as`, und die Werte landen beim
    richtigen Athleten. Ein abgelehnter Schlüssel (C) hält die anderen nicht auf."""
    import core.scheduler as scheduler

    a = _nutzer(db, "garmin-job-a@example.invalid", garmin_api_key="K-A")
    b = _nutzer(db, "garmin-job-b@example.invalid")
    c = _nutzer(db, "garmin-job-c@example.invalid", garmin_api_key="K-C-UNGUELTIG")
    d = _nutzer(db, "garmin-job-d@example.invalid", garmin_api_key="K-D")
    db.add(HrvMeasurement(user_id=b.id, measured_at=HEUTE, rmssd=55, quelle="manual"))
    db.commit()

    garmin = Garmin({
        "K-A": [_summary(HEUTE, 88), _summary(HEUTE - timedelta(days=1), 86)],
        "K-D": [_summary(HEUTE, 64)],
    })
    monkeypatch.setattr(garmin_personal, "STANDARD_TRANSPORT", garmin.transport)
    asyncio.run(scheduler._garmin_morgens_job())

    assert [(m.rmssd, m.quelle) for m in _messungen(db, a)] == [(86, "garmin"), (88, "garmin")]
    assert [(m.rmssd, m.quelle) for m in _messungen(db, b)] == [(55, "manual")]
    assert _messungen(db, c) == []
    assert _profil(db, c).garmin_letzter_fehler
    assert [(m.rmssd, m.quelle) for m in _messungen(db, d)] == [(64, "garmin")]

    # Zweiter Lauf am selben Vormittag: Für A und D ist Garmins Wert von heute
    # da, also wird nicht mehr gefragt. Nur C (ohne Wert) fragt erneut.
    garmin.anfragen.clear()
    asyncio.run(scheduler._garmin_morgens_job())
    schluessel = {r.headers.get("Authorization") for r in garmin.anfragen}
    assert "ApiKey K-A" not in schluessel
    assert "ApiKey K-D" not in schluessel
    assert "ApiKey K-C-UNGUELTIG" in schluessel

    # Aufräumen, damit spätere Jobläufe in anderen Tests diese Athleten nicht sehen.
    for u in (a, c, d):
        _profil(db, u).garmin_api_key = None
    db.commit()


def test_fehler_bei_einem_athleten_stoppt_den_job_nicht(db, monkeypatch):
    import core.scheduler as scheduler
    import services.garmin_hrv as garmin_hrv

    a = _nutzer(db, "garmin-crash-a@example.invalid", garmin_api_key="K-CRASH-A")
    b = _nutzer(db, "garmin-crash-b@example.invalid", garmin_api_key="K-CRASH-B")
    gesehen = []

    async def abgleich(sitzung, user, tage=7, mit_spanne=False, **kw):
        gesehen.append(user.id)
        if user.id == a.id:
            raise RuntimeError("kaputt")
        return {"ok": True}

    monkeypatch.setattr(garmin_hrv, "abgleich_fuer", abgleich)
    asyncio.run(scheduler._garmin_sonntag_job())
    assert a.id in gesehen and b.id in gesehen

    for u in (a, b):
        _profil(db, u).garmin_api_key = None
    db.commit()


def test_scheduler_haengt_nur_eingeschaltete_jobs_an(monkeypatch):
    import core.scheduler as scheduler
    from core.config import settings

    monkeypatch.setattr(settings, "RECONCILE_ENABLED", False)
    monkeypatch.setattr(settings, "GARMIN_SYNC_ENABLED", True)

    async def starten():
        s = scheduler.start_scheduler()
        try:
            return {j.id for j in s.get_jobs()}, scheduler.scheduler_status()
        finally:
            scheduler.shutdown_scheduler()

    jobs, status = asyncio.run(starten())
    assert jobs == {"garmin_hrv_morgens", "garmin_spanne_sonntag"}
    assert status["garmin_enabled"] is True and status["reconcile_enabled"] is False


# --- Router ------------------------------------------------------------------

def test_put_mit_ungueltigem_schluessel_speichert_nichts(client, db, rueckfallprofil, monkeypatch):
    nutzer, _ = rueckfallprofil
    monkeypatch.setattr(garmin_personal, "STANDARD_TRANSPORT", Garmin({}).transport)

    antwort = client.put("/api/integrations/garmin", json={"api_key": "FALSCH-4711"})
    assert antwort.status_code == 422
    assert "4711" not in antwort.text

    db.expire_all()
    p = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    assert p.garmin_api_key is None
    assert p.garmin_verbunden_am is None


@pytest.mark.parametrize("schluessel", ["GEHEIM\u00fcSCHLUESSEL", "GEHEIM\u200bSCHLUESSEL"])
def test_put_mit_nicht_ascii_schluessel_422_ohne_speichern(client, db, rueckfallprofil, monkeypatch, schluessel):
    """Vorher ein 500 mit dem Schlüssel im Ausnahmetext."""
    nutzer, _ = rueckfallprofil
    garmin = Garmin({schluessel: []})
    monkeypatch.setattr(garmin_personal, "STANDARD_TRANSPORT", garmin.transport)

    antwort = client.put("/api/integrations/garmin", json={"api_key": schluessel})
    assert antwort.status_code == 422
    assert "GEHEIM" not in antwort.text and "SCHLUESSEL" not in antwort.text
    assert garmin.anfragen == [], "gar nicht erst an Garmin geschickt"

    db.expire_all()
    p = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    assert p.garmin_api_key is None
    assert p.garmin_verbunden_am is None


def test_put_mit_gueltigem_schluessel_holt_30_tage_mit_spanne(client, db, rueckfallprofil, monkeypatch):
    nutzer, _ = rueckfallprofil
    # Tage weit weg von heute: Andere Testdateien legen für diesen Nutzer
    # Messungen um das heutige Datum an.
    garmin = Garmin({"GUELTIG-abcd": [_summary(HEUTE - timedelta(days=25 + i), 75 + i) for i in range(3)]})
    monkeypatch.setattr(garmin_personal, "STANDARD_TRANSPORT", garmin.transport)

    antwort = client.put("/api/integrations/garmin", json={"api_key": "GUELTIG-abcd"})
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert "GUELTIG-abcd" not in antwort.text
    assert daten["garmin"]["configured"] is True
    assert daten["garmin"]["api_key_hint"] == "…abcd"
    assert daten["ergebnis"]["neu"] + daten["ergebnis"]["aktualisiert"] == 3
    assert daten["ergebnis"]["spanne_uebernommen"] is True

    # Ein Tausch für Prüfung und Abruf, und der Rückblick über 30 Tage.
    pfade = [r.url.path for r in garmin.anfragen]
    assert pfade.count(garmin_personal.TOKEN_PFAD) == 1
    assert pfade[-1].startswith(f"/hrv-service/hrv/daily/{(HEUTE - timedelta(days=30)).isoformat()}/")

    db.expire_all()
    p = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    assert p.garmin_api_key == "GUELTIG-abcd"
    assert p.garmin_verbunden_am is not None
    assert p.hrv_range_source == "garmin"

    # `GET /hrv/range` meldet dem Dashboard die Verbindung, ohne eigenen Aufruf.
    spanne = client.get("/api/hrv/range").json()
    assert spanne["garmin_verbunden"] is True
    assert spanne["grenzen"]["quelle"] == "garmin"


def test_get_integrations_gibt_den_schluessel_nie_im_klartext(client, db, rueckfallprofil):
    _, profil = rueckfallprofil
    profil.garmin_api_key = "SEHR-GEHEIM-SCHLUESSEL-wxyz"
    profil.garmin_letzter_fehler = "Schlüssel ungültig oder abgelaufen."
    db.commit()

    antwort = client.get("/api/integrations")
    assert antwort.status_code == 200
    assert "SEHR-GEHEIM" not in antwort.text
    garmin = antwort.json()["garmin"]
    assert garmin["configured"] is True
    assert garmin["api_key_hint"] == "…wxyz"
    assert garmin["letzter_fehler"] == "Schlüssel ungültig oder abgelaufen."
    assert garmin["sync_aktiv"] is False


def test_fehler_art_unterscheidet_schluessel_und_voruebergehend(client, db, rueckfallprofil):
    """Das Feld für einen neuen Schlüssel erscheint nur, wenn der Schlüssel
    das Problem ist. Bei einem 429 hilft ein neuer nicht."""
    from services.garmin_hrv import FEHLERTEXT, FEHLERTEXT_UNLESBAR

    _, profil = rueckfallprofil
    profil.garmin_api_key = "K-ART"
    erwartet = [
        (FEHLERTEXT[GarminSchluesselUngueltig], "schluessel"),
        (FEHLERTEXT_UNLESBAR, "schluessel"),
        (FEHLERTEXT[GarminRateLimit], "vorruebergehend"),
        (FEHLERTEXT[GarminNichtErreichbar], "vorruebergehend"),
        (None, None),
    ]
    for text, art in erwartet:
        profil.garmin_letzter_fehler = text
        db.commit()
        assert client.get("/api/integrations").json()["garmin"]["fehler_art"] == art, text


def test_abrufen_und_trennen(client, db, rueckfallprofil, monkeypatch):
    nutzer, profil = rueckfallprofil
    profil.garmin_api_key = "K-KNOPF"
    profil.hrv_range_source = "garmin"
    profil.hrv_green_min, profil.hrv_band_high, profil.hrv_red_below = 70, 92, red_from_band(70, 92)
    db.commit()
    garmin = Garmin({"K-KNOPF": [_summary(HEUTE, 90)]})
    monkeypatch.setattr(garmin_personal, "STANDARD_TRANSPORT", garmin.transport)

    antwort = client.post("/api/integrations/garmin/abrufen")
    assert antwort.status_code == 200
    assert antwort.json()["ergebnis"]["ok"] is True
    # 7 Tage, ohne Spanne.
    assert "spanne_uebernommen" not in antwort.json()["ergebnis"]
    assert garmin.anfragen[-1].url.path.startswith(
        f"/hrv-service/hrv/daily/{(HEUTE - timedelta(days=7)).isoformat()}/")

    antwort = client.delete("/api/integrations/garmin")
    assert antwort.status_code == 200
    assert antwort.json()["garmin"]["configured"] is False

    db.expire_all()
    p = db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).first()
    assert p.garmin_api_key is None and p.garmin_letzter_abruf is None
    # Die Trennung stellt die Ampel nicht still um, und Messungen bleiben.
    assert p.hrv_range_source == "garmin" and p.hrv_green_min == 70
    assert db.query(HrvMeasurement).filter(
        HrvMeasurement.user_id == nutzer.id, HrvMeasurement.quelle == "garmin").count() >= 1


def test_post_hrv_mit_garmin_409_ohne_garmin_wie_bisher(client, db, rueckfallprofil):
    _, profil = rueckfallprofil
    profil.garmin_api_key = "K-409"
    db.commit()
    antwort = client.post("/api/hrv", json={"measured_at": "2026-03-20", "rmssd": 70})
    assert antwort.status_code == 409
    assert "Garmin" in antwort.json()["detail"]

    profil.garmin_api_key = None
    db.commit()
    antwort = client.post("/api/hrv", json={"measured_at": "2026-03-20", "rmssd": 70})
    assert antwort.status_code == 200
    assert antwort.json()["quelle"] == "manual"


def test_range_setzen_gibt_es_nicht_mehr(client):
    """Die Spanne ist nicht mehr von Hand änderbar."""
    assert client.post("/api/hrv/range", json={"band_low": 60, "band_high": 90}).status_code == 405
    assert client.delete("/api/hrv/range").status_code == 405


# --- Vorrang, Prompt, Export -------------------------------------------------

class GarminSpanne:
    hrv_range_source = "garmin"
    hrv_green_min = 70.0
    hrv_band_high = 92.0
    hrv_red_below = 64.5


GRUNDLINIE_OK = {
    "status": "ok", "messungen": 30, "mean": 77.1, "sd": 12.0,
    "band_unten": 71.1, "band_oben": 83.1, "gruen_ab": 71.1, "rot_unter": 65.1,
}


def test_garmin_hat_vorrang_vor_der_rechnung():
    grenzen = thresholds_for(GarminSpanne(), GRUNDLINIE_OK)
    assert grenzen == {"gruen_ab": 70.0, "gruen_bis": 92.0, "rot_unter": 64.5, "quelle": "garmin"}


def test_der_prompt_nennt_garmin_als_herkunft():
    from core.prompt_templates import format_hrv

    text = format_hrv([{"measured_at": "2026-10-23", "rmssd": 80, "hrv_status": "green"}],
                      thresholds_for(GarminSpanne(), GRUNDLINIE_OK))
    assert "Garmin" in text
    assert "Mittelwert ± 0,5 σ" not in text


def test_export_enthaelt_den_garmin_schluessel_nicht(db):
    from services.account_export import build_export

    u = _nutzer(db, "garmin-export@example.invalid", garmin_api_key="EXPORT-GEHEIM-1")
    export = build_export(db, u)
    assert "garmin_api_key" not in export["profil"][0]
    assert "EXPORT-GEHEIM-1" not in json.dumps(export, default=str)
