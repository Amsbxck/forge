"""intervals.icu: geplante Workouts in den Kalender des Athleten schreiben.

Wozu: Die Läufe aus dem FORGE-Plan sollen als Workout auf der Garmin-Uhr
landen. Garmin selbst nimmt nichts an (Personal API nur lesend, Garmin Connect
importiert keine Workout-Dateien). intervals.icu nimmt geplante Workouts über
seine API an und schiebt sie selbst in den Garmin-Kalender, wenn der Athlet
dort Garmin verbunden und „Upload planned workouts" eingeschaltet hat.

Zwei Zugänge:

- **Persönlicher Schlüssel** (Settings → Developer Settings): Basic Auth mit
  dem festen Benutzernamen `API_KEY` und dem Schlüssel als Passwort, dazu die
  Athleten-ID (`i12345`).
- **OAuth-Token** der FORGE-App: `Bearer`. Die Athleten-ID kommt aus der
  Token-Antwort. Tokens haben laut den Anleitungen keinen Refresh.

Bewusst nur die einfachen Endpunkte (lesen, anlegen, ersetzen, löschen je
Event) statt des Bulk-Upserts über `external_id`: Nach Forenberichten greift
der Upsert nur bei Events derselben OAuth-App, mit dem persönlichen Schlüssel
entstünden Dubletten. Den Abgleich macht `services/intervals_sync.py`.

**Geheimnisse:** wie in `garmin_personal.py`. Schlüssel und Token tauchen in
keiner Ausnahme, keinem Protokoll und keiner Antwort auf, die Antwort von
intervals.icu wird nie durchgereicht.

**Injizierbar:** Jede Funktion nimmt einen `transport`, sonst gilt
`STANDARD_TRANSPORT` (für Tests per `monkeypatch`).
"""

from __future__ import annotations

import base64
import logging
from datetime import date

import httpx

from core.config import settings
from services.garmin_personal import schluessel_bereinigen, zeichen_gueltig

logger = logging.getLogger(__name__)

ZEITLIMIT_S = 20.0
OAUTH_SCOPE = "CALENDAR:WRITE"

STANDARD_TRANSPORT: httpx.AsyncBaseTransport | None = None


class IntervalsFehler(Exception):
    """Oberklasse. Die Meldung ist immer ein fester Text ohne Geheimnisse."""

    def __init__(self, meldung: str, status: int | None = None):
        super().__init__(meldung)
        self.status = status


class IntervalsZugangUngueltig(IntervalsFehler):
    """401/403: Schlüssel oder Token falsch, widerrufen, oder die Athleten-ID
    gehört nicht zum Schlüssel."""


class IntervalsNichtErreichbar(IntervalsFehler):
    """Netzfehler, Zeitüberschreitung, 429 oder 5xx."""


class IntervalsAntwortUnerwartet(IntervalsFehler):
    """Andere 4xx oder eine Antwort, die sich nicht lesen lässt."""


class Zugang:
    """Wer schreibt, und wohin: Athleten-ID plus Schlüssel oder Token."""

    def __init__(self, athlete_id: str | None, api_key: str | None = None, token: str | None = None):
        self.athlete_id = (athlete_id or "").strip()
        self.api_key = schluessel_bereinigen(api_key) if api_key else None
        self.token = schluessel_bereinigen(token) if token else None

    @property
    def vollstaendig(self) -> bool:
        return bool(self.athlete_id) and bool(self.api_key or self.token)

    def kopf(self) -> dict:
        # Erst prüfen, dann in den Kopf: Ein Nicht-ASCII-Zeichen ließe httpx
        # einen UnicodeEncodeError werfen, der den Kopf samt Geheimnis trägt
        # (siehe `garmin_personal.zeichen_gueltig`).
        if self.token:
            if not zeichen_gueltig(self.token):
                raise IntervalsZugangUngueltig("intervals.icu-Token enthält unzulässige Zeichen")
            return {"Authorization": f"Bearer {self.token}"}
        if not zeichen_gueltig(self.api_key):
            raise IntervalsZugangUngueltig("intervals.icu-Schlüssel fehlt oder enthält unzulässige Zeichen")
        roh = base64.b64encode(f"API_KEY:{self.api_key}".encode("ascii")).decode("ascii")
        return {"Authorization": f"Basic {roh}"}


def athleten_id_gueltig(wert: str | None) -> bool:
    """`i12345` oder nur Ziffern. Die ID geht in den Pfad, also streng."""
    w = (wert or "").strip()
    if w.startswith("i"):
        w = w[1:]
    return w.isdigit() and 0 < len(w) <= 12


def zugang_aus_profil(profile) -> Zugang | None:
    if profile is None:
        return None
    zugang = Zugang(
        profile.intervals_athlete_id,
        api_key=profile.intervals_api_key,
        token=profile.intervals_token,
    )
    return zugang if zugang.vollstaendig else None


def _status_pruefen(antwort: httpx.Response) -> None:
    status = antwort.status_code
    if status in (401, 403):
        raise IntervalsZugangUngueltig("intervals.icu hat den Zugang abgelehnt", status)
    if status == 429 or status >= 500:
        raise IntervalsNichtErreichbar("intervals.icu ist gerade nicht erreichbar", status)
    if status >= 400:
        raise IntervalsAntwortUnerwartet("intervals.icu hat die Anfrage abgelehnt", status)


async def _senden(
    methode: str,
    pfad: str,
    zugang: Zugang | None,
    transport: httpx.AsyncBaseTransport | None,
    *,
    params: dict | None = None,
    json_body=None,
    form: dict | None = None,
) -> httpx.Response:
    headers = {"Accept": "application/json"}
    if zugang is not None:
        headers.update(zugang.kopf())
    try:
        async with httpx.AsyncClient(
            base_url=settings.INTERVALS_BASE_URL.rstrip("/"),
            timeout=ZEITLIMIT_S,
            transport=transport or STANDARD_TRANSPORT,
        ) as client:
            antwort = await client.request(
                methode, pfad, headers=headers, params=params, json=json_body, data=form,
            )
    except httpx.HTTPError:
        # Ohne die Ausnahme selbst, ihr Text trägt die Anfrage.
        logger.warning("intervals.icu nicht erreichbar (%s)", methode)
        raise IntervalsNichtErreichbar("intervals.icu ist nicht erreichbar") from None
    _status_pruefen(antwort)
    return antwort


def _json(antwort: httpx.Response):
    if antwort.status_code == 204 or not (antwort.content or b"").strip():
        return None
    try:
        return antwort.json()
    except ValueError:
        raise IntervalsAntwortUnerwartet("intervals.icu hat kein JSON geliefert") from None


def _athlet_pfad(zugang: Zugang) -> str:
    if not athleten_id_gueltig(zugang.athlete_id):
        raise IntervalsZugangUngueltig("Athleten-ID von intervals.icu ist ungültig")
    return f"/api/v1/athlete/{zugang.athlete_id}"


async def athlet_pruefen(zugang: Zugang, transport=None) -> dict:
    """Passt der Zugang zur Athleten-ID? Liefert ID und Name."""
    daten = _json(await _senden("GET", _athlet_pfad(zugang), zugang, transport))
    if not isinstance(daten, dict):
        raise IntervalsAntwortUnerwartet("intervals.icu hat keinen Athleten geliefert")
    return {"id": str(daten.get("id") or zugang.athlete_id), "name": daten.get("name")}


async def events_lesen(zugang: Zugang, von: date, bis: date, transport=None) -> list[dict]:
    """Geplante Workouts zwischen `von` und `bis` (je einschließlich)."""
    daten = _json(await _senden(
        "GET", f"{_athlet_pfad(zugang)}/events", zugang, transport,
        params={"oldest": von.isoformat(), "newest": bis.isoformat(), "category": "WORKOUT"},
    ))
    if not isinstance(daten, list):
        return []
    return [e for e in daten if isinstance(e, dict)]


async def event_anlegen(zugang: Zugang, event: dict, transport=None) -> dict:
    daten = _json(await _senden("POST", f"{_athlet_pfad(zugang)}/events", zugang, transport, json_body=event))
    return daten if isinstance(daten, dict) else {}


async def event_ersetzen(zugang: Zugang, event_id, event: dict, transport=None) -> dict:
    daten = _json(await _senden(
        "PUT", f"{_athlet_pfad(zugang)}/events/{int(event_id)}", zugang, transport, json_body=event,
    ))
    return daten if isinstance(daten, dict) else {}


async def event_loeschen(zugang: Zugang, event_id, transport=None) -> None:
    try:
        await _senden("DELETE", f"{_athlet_pfad(zugang)}/events/{int(event_id)}", zugang, transport)
    except IntervalsAntwortUnerwartet as e:
        # Schon weg (von Hand gelöscht): Das Ziel ist erreicht.
        if e.status != 404:
            raise


# --- OAuth -----------------------------------------------------------------

def oauth_bereit() -> bool:
    return bool(settings.INTERVALS_CLIENT_ID and settings.INTERVALS_CLIENT_SECRET)


def oauth_adresse(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode

    return f"{settings.INTERVALS_BASE_URL.rstrip('/')}/oauth/authorize?" + urlencode({
        "client_id": settings.INTERVALS_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPE,
        "state": state,
    })


async def code_tauschen(code: str, transport=None) -> dict:
    """Code gegen Token tauschen. Muss sofort passieren, intervals.icu lässt
    dafür nur zwei Minuten. Liefert `{"token", "athlete_id"}`."""
    daten = _json(await _senden(
        "POST", "/api/oauth/token", None, transport,
        form={
            "client_id": settings.INTERVALS_CLIENT_ID,
            "client_secret": settings.INTERVALS_CLIENT_SECRET,
            "code": code,
        },
    ))
    if not isinstance(daten, dict):
        raise IntervalsAntwortUnerwartet("Token-Antwort von intervals.icu ohne Inhalt")
    token = str(daten.get("access_token") or "").strip()
    athlet = daten.get("athlete") if isinstance(daten.get("athlete"), dict) else {}
    athlete_id = str(athlet.get("id") or "").strip()
    if not zeichen_gueltig(token) or not athleten_id_gueltig(athlete_id):
        raise IntervalsAntwortUnerwartet("Token-Antwort von intervals.icu ohne Token")
    return {"token": token, "athlete_id": athlete_id}
