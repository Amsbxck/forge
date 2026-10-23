"""Garmin Connect Personal API: Schlüssel tauschen, Daten holen.

Ein allgemeiner, schmaler Client: Token holen plus eine generische GET-Hilfe.
HRV ist nur die erste Methode darauf. Ruhepuls, Schlaf und weitere Tageswerte
sollen später als weitere kleine Methoden dazukommen, ohne dass sich an der
Struktur etwas ändert.

Bewusst kein eigenes Paket (etwa der inoffizielle Client `gcpapi-sync`): Es
sind zwei Endpunkte, das vorhandene `httpx` reicht, wie in
`services/strava_service.py`. Ein weiteres Paket hieße eine weitere
Abhängigkeit, die im Container nachgezogen werden muss (siehe CLAUDE.md zum
alten Anthropic-SDK).

Ablauf bei Garmin:

- Der persönliche API-Schlüssel wird per `POST` gegen ein Zugriffstoken
  getauscht (Header `Authorization: ApiKey <schlüssel>`). **Am 23.10.2026 mit
  einem echten Schlüssel live geprüft:** Die Antwort ist HTTP 200 mit
  `Content-Type: text/plain` und als Body direkt das JWT (drei durch Punkte
  getrennte Teile, ohne Anführungszeichen, kein JSON, kein `access_token`).
  Und: Mit `Accept: application/json` antwortet Garmin beim Tausch mit
  **406**. Der inoffizielle Client (und die erste Fassung der Aufgabe, die
  von einem OAuth2-Objekt ausging) stimmte hier nicht. Deshalb sendet der
  Tausch `Accept: */*`, und nur die Datenabrufe verlangen JSON. Ein
  JSON-Objekt mit `access_token` wird trotzdem angenommen, falls Garmin das
  einmal ändert; ein leerer Body ist ein Fehler, kein Token.
- Der HRV-Endpunkt liefert (ebenfalls am 23.10.2026 geprüft) genau die
  dokumentierte Form `{"hrvSummaries": [...], "userProfilePk": …}`, mit
  zusätzlichen Feldern `feedbackPhrase` und `createTimeStamp`, die hier
  nicht gebraucht werden. `lastNightAvg` kann `null` sein.
- Das Token gilt 24 Stunden. Refresh-Tokens gibt es nicht, und gespeichert
  wird es auch nicht: Jeder Lauf tauscht neu. Ein gespeichertes Token wäre
  ein zweites Geheimnis in der Datenbank, für einen Tausch am Tag.
- Garmin schickt nichts von selbst (nur Pull).

**Geheimnisse:** Schlüssel und Token tauchen in keiner Ausnahme, keinem
Protokoll und keiner Antwort auf. Die Ausnahmen tragen feste Texte und
höchstens den HTTP-Status. Garmins Antworttext wird nie durchgereicht: Bei
einem Fehler im Tausch könnte er den Schlüssel zurückspiegeln.

**Injizierbar:** Jede Funktion nimmt einen `transport` (für Tests ein
`httpx.MockTransport`). Ohne Angabe gilt `STANDARD_TRANSPORT`, den Tests per
`monkeypatch` setzen, wenn sie über Router oder Scheduler gehen und den
Aufruf nicht selbst in der Hand haben. `respx` ist nicht installiert und soll
es auch nicht werden.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

TOKEN_PFAD = "/personalapitoken-service/personal-api/personal-api-key/token"
HRV_TAGE_PFAD = "/hrv-service/hrv/daily/{von}/{bis}"

# Der inoffizielle Client teilt HRV-Zeiträume in Fenster von höchstens 365
# Tagen; größere beantwortet Garmin mit einem Fehler. FORGE fragt nie mehr
# als 30 Tage, die Teilung steht trotzdem hier, damit ein späterer längerer
# Rückblick nicht still scheitert.
MAX_TAGE_HRV = 365

ZEITLIMIT_S = 20.0

# Für Tests: ein Transport, der statt des echten Netzes genommen wird.
STANDARD_TRANSPORT: httpx.AsyncBaseTransport | None = None


class GarminFehler(Exception):
    """Oberklasse. Die Meldung ist immer ein fester Text ohne Geheimnisse."""

    def __init__(self, meldung: str, status: int | None = None):
        super().__init__(meldung)
        self.status = status


class GarminSchluesselUngueltig(GarminFehler):
    """401/403 beim Tausch oder beim Abruf: Schlüssel falsch, gelöscht oder
    abgelaufen. Ein gelöschter Schlüssel macht auch alle Tokens ungültig."""


class GarminRateLimit(GarminFehler):
    """429. Rate-Limits sind nicht dokumentiert, also nicht warten, sondern
    den Athleten bis zum nächsten Lauf auslassen."""

    def __init__(self, meldung: str, status: int | None = 429, retry_after: float | None = None):
        super().__init__(meldung, status)
        self.retry_after = retry_after


class GarminNichtErreichbar(GarminFehler):
    """Netzfehler, Zeitüberschreitung oder 5xx."""


class GarminAntwortUnerwartet(GarminFehler):
    """Garmin hat geantwortet, aber nicht in der erwarteten Form (leeres
    Token, kein JSON, ein anderer 4xx-Status). Eigene Klasse, weil die
    Feldnamen aus einem inoffiziellen Client stammen: Ändert Garmin etwas,
    soll das als eigener Fehler sichtbar werden und nicht wie ein falscher
    Schlüssel aussehen."""


def _retry_after(wert: str | None) -> float | None:
    if not wert:
        return None
    try:
        return max(0.0, float(wert))
    except ValueError:
        # HTTP-Datum statt Sekunden. Gewartet wird ohnehin nicht, der nächste
        # Lauf kommt frühestens in einer Stunde; die Zahl dient nur dem Log.
        return None


def _status_pruefen(antwort: httpx.Response) -> None:
    """HTTP-Status in eigene Ausnahmen übersetzen — ohne den Antworttext."""
    status = antwort.status_code
    if status in (401, 403):
        raise GarminSchluesselUngueltig("Garmin hat den Schlüssel abgelehnt", status)
    if status == 429:
        raise GarminRateLimit(
            "Garmin bremst die Anfragen (429)",
            retry_after=_retry_after(antwort.headers.get("Retry-After")),
        )
    if status >= 500:
        raise GarminNichtErreichbar("Garmin Connect antwortet mit einem Serverfehler", status)
    if status >= 400:
        raise GarminAntwortUnerwartet("Garmin hat die Anfrage abgelehnt", status)


def _client(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    # Kein Accept-Kopf hier für alle Anfragen: Der Token-Tausch scheitert mit
    # 406, sobald JSON verlangt wird (live geprüft am 23.10.2026). Jede
    # Anfrage setzt ihren eigenen.
    return httpx.AsyncClient(
        base_url=settings.GARMIN_PERSONAL_BASE_URL.rstrip("/"),
        timeout=ZEITLIMIT_S,
        transport=transport or STANDARD_TRANSPORT,
    )


async def _senden(
    methode: str,
    pfad: str,
    headers: dict,
    transport: httpx.AsyncBaseTransport | None,
    params: dict | None = None,
) -> httpx.Response:
    try:
        async with _client(transport) as client:
            antwort = await client.request(methode, pfad, headers=headers, params=params)
    except httpx.HTTPError:
        # Bewusst ohne die Ausnahme selbst: Ihr Text enthält die Anfrage-URL
        # und je nach Fehler mehr. Die Art genügt fürs Protokoll.
        logger.warning("Garmin nicht erreichbar (%s %s)", methode, pfad.split("/")[1])
        raise GarminNichtErreichbar("Garmin Connect ist nicht erreichbar") from None
    _status_pruefen(antwort)
    return antwort


# Leerraum, den `str.strip()` nicht entfernt: Nullbreiten-Leerzeichen und
# -Verbinder sowie das Byte-Order-Mark. Beim Kopieren aus dem Browser oder
# aus Passwortmanagern rutschen sie gern mit an den Rand.
NULLBREITE = "\u200b\u200c\u200d\ufeff"


def schluessel_bereinigen(roh: str | None) -> str:
    """Leerraum samt Nullbreiten-Zeichen am Rand entfernen.

    Nur am Rand: Steht so ein Zeichen mitten im Schlüssel, ist das kein
    Kopierrest mehr, den man still reparieren dürfte, sondern ein anderer
    Schlüssel. Den lehnt `zeichen_gueltig` ab.
    """
    wert = roh or ""
    vorher = None
    while vorher != wert:
        vorher = wert
        wert = wert.strip().strip(NULLBREITE)
    return wert


def zeichen_gueltig(wert: str | None) -> bool:
    """Taugt die Zeichenkette als HTTP-Kopfwert (Schlüssel oder Token)?

    Ein Zeichen wie „ü" oder ein Nullbreiten-Leerzeichen (U+200B) ließ httpx
    beim Kopf `ApiKey …` einen UnicodeEncodeError werfen. Der wurde zum 500,
    und seine `args` enthielten den vollen Schlüssel, der damit im Protokoll
    landen konnte. Deshalb vorher prüfen: nicht leer, nur druckbares ASCII,
    kein Leerraum. Garmins Schlüssel und JWTs erfüllen das immer.
    """
    return bool(
        wert
        and wert.isascii()
        and wert.isprintable()
        and not any(z.isspace() for z in wert)
    )


def _token_aus_antwort(antwort: httpx.Response) -> str:
    text = (antwort.text or "").strip()
    if text.startswith("{"):
        try:
            daten = json.loads(text)
        except ValueError:
            daten = None
        if isinstance(daten, dict):
            for feld in ("access_token", "accessToken", "token"):
                wert = daten.get(feld)
                if isinstance(wert, str) and zeichen_gueltig(wert.strip()):
                    return wert.strip()
        raise GarminAntwortUnerwartet("Token-Antwort von Garmin ohne Token")
    token = text.strip('"').strip()
    # Dieselbe Prüfung wie beim Schlüssel: Das Token geht gleich danach in
    # den Kopf `Bearer …`. Eine Fehlerseite als Text fiele hier auch heraus.
    if not zeichen_gueltig(token):
        raise GarminAntwortUnerwartet("Token-Antwort von Garmin ohne Token")
    return token


async def token_holen(api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Persönlichen API-Schlüssel gegen ein 24-Stunden-Token tauschen."""
    schluessel = schluessel_bereinigen(api_key)
    if not zeichen_gueltig(schluessel):
        # Ohne diese Prüfung ginge „ApiKey None" an Garmin, etwa wenn ein
        # gespeicherter Schlüssel nach einem Wechsel von DATA_ENCRYPTION_KEY
        # nicht mehr lesbar ist. Und ein Nicht-ASCII-Zeichen ließe httpx mit
        # einem UnicodeEncodeError abbrechen, der den Schlüssel im Text trägt
        # (siehe `zeichen_gueltig`). Ein solcher Schlüssel ist ohnehin keiner,
        # den Garmin ausgestellt hat.
        raise GarminSchluesselUngueltig("Garmin-Schlüssel fehlt oder enthält unzulässige Zeichen")
    antwort = await _senden(
        "POST", TOKEN_PFAD,
        # `*/*` statt JSON: Garmin liefert das Token als text/plain und
        # beantwortet `Accept: application/json` mit 406.
        {"Authorization": f"ApiKey {schluessel}", "Accept": "*/*"},
        transport,
    )
    return _token_aus_antwort(antwort)


async def get_json(
    token: str,
    pfad: str,
    transport: httpx.AsyncBaseTransport | None = None,
    params: dict | None = None,
):
    """Generische GET-Hilfe für alle Datenendpunkte.

    204 heißt bei Garmin „keine Daten" und wird zu None. Alles, was sich nicht
    als JSON lesen lässt, ist eine unerwartete Antwort.
    """
    # Heute kommt jedes Token aus `token_holen` und ist damit schon geprüft.
    # Diese Hilfe ist aber für weitere Endpunkte (Ruhepuls, Schlaf) gedacht,
    # und ein ungeprüftes Token mit Nicht-ASCII ließe httpx einen
    # UnicodeEncodeError werfen, der den Kopf samt Token in `args` trägt.
    if not zeichen_gueltig(token):
        raise GarminSchluesselUngueltig("Garmin-Token fehlt oder enthält unzulässige Zeichen")
    antwort = await _senden(
        "GET", pfad,
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        transport, params=params,
    )
    if antwort.status_code == 204 or not (antwort.content or b"").strip():
        return None
    try:
        return antwort.json()
    except ValueError:
        raise GarminAntwortUnerwartet("Garmin hat kein JSON geliefert") from None


def _summaries(daten) -> list[dict]:
    """`hrvSummaries` aus der Antwort, defensiv.

    Dokumentiert ist `{"userProfilePk": …, "hrvSummaries": [...]}`. Fehlt der
    Schlüssel, ist er `null` oder kommt gleich eine Liste, wird daraus eine
    Liste von Objekten; alles andere (Zahlen, Text) fällt weg.
    """
    if isinstance(daten, dict):
        daten = daten.get("hrvSummaries")
    if not isinstance(daten, list):
        return []
    return [s for s in daten if isinstance(s, dict)]


async def hrv_tage(
    token: str,
    von: date,
    bis: date,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict]:
    """Die täglichen HRV-Zusammenfassungen von `von` bis `bis` (je einschließlich)."""
    ergebnis: list[dict] = []
    start = von
    while start <= bis:
        ende = min(bis, start + timedelta(days=MAX_TAGE_HRV - 1))
        daten = await get_json(
            token,
            HRV_TAGE_PFAD.format(von=start.isoformat(), bis=ende.isoformat()),
            transport,
        )
        ergebnis.extend(_summaries(daten))
        start = ende + timedelta(days=1)
    return ergebnis
