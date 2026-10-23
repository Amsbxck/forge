"""HRV aus Garmin Connect übernehmen: tägliche Werte und die Normalspanne.

Vorher tippte der Athlet beides von Hand ab: jeden Morgen die nächtliche HRV
ins Dashboard und ab und zu den grünen Bereich aus der Garmin-App ins Profil.
Jetzt holt FORGE beides selbst (`services/garmin_personal.py`).

**Garmin ist die Quelle.** Liegt für einen Tag schon ein Wert vor, auch ein
von Hand eingetragener, überschreibt Garmins Wert ihn. Gelöscht wird dabei
nichts: Gibt es an einem Tag zwei Zeilen (das kommt in Bestandsdaten vor,
siehe `HRVHistoryChart.jsx`), wird nur die erste angepasst und die zweite
bleibt stehen.

**Garmins Baseline hat Vorrang** vor der berechneten Spanne, mit demselben
unbedingten Vorrang wie früher eine eingetragene (`hrv_baseline.thresholds_for`).
Es ist genau der Bereich, den Amir bisher abgetippt hat.

`abgleich_fuer` ist so geschnitten, dass weitere Tageswerte (Ruhepuls, Schlaf)
später als zusätzliche Schritte im selben Lauf dazukommen: ein Token pro Lauf,
ein Athlet pro Session.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import AthleteProfile, HrvMeasurement, User
from services import garmin_personal
from services.garmin_personal import (
    GarminAntwortUnerwartet, GarminFehler, GarminNichtErreichbar, GarminRateLimit,
    GarminSchluesselUngueltig,
)

logger = logging.getLogger(__name__)

QUELLE = "garmin"

# Erste Hälfte der Kennung für `pg_advisory_xact_lock(art, nutzer)`: eine
# feste Zahl für „Garmin-HRV übernehmen" ("GHRV" in ASCII), damit sich die
# Sperre nicht mit einer anderen Sperre derselben Nutzer-ID überschneidet.
# Die zweite Hälfte ist die Nutzer-ID.
SPERRE_GARMIN_HRV = 0x47485256

# Garmin meldet einen Status je Nacht. NONE heißt „keine Messung", INVALID
# „Messung verworfen" — beides ist kein Wert, auch wenn `lastNightAvg` gefüllt
# sein sollte.
STATUS_OHNE_WERT = {"NONE", "INVALID"}

# Feste Texte für die Kachel. Nie die Antwort von Garmin oder eine Ausnahme
# im Wortlaut: Darin könnte ein Stück Schlüssel oder Token stehen.
FEHLERTEXT = {
    GarminSchluesselUngueltig: "Schlüssel ungültig oder abgelaufen. Bitte in Garmin Connect einen neuen anlegen und hier eintragen.",
    GarminRateLimit: "Garmin bremst gerade die Anfragen. Der nächste Lauf versucht es erneut.",
    GarminNichtErreichbar: "Garmin Connect war nicht erreichbar. Der nächste Lauf versucht es erneut.",
    GarminAntwortUnerwartet: "Garmin hat unerwartet geantwortet. Der nächste Lauf versucht es erneut.",
}
FEHLERTEXT_ALLGEMEIN = "Abruf bei Garmin fehlgeschlagen. Der nächste Lauf versucht es erneut."
FEHLERTEXT_UNLESBAR = "Der gespeicherte Schlüssel ist nicht mehr lesbar. Bitte neu eintragen."

# Texte, bei denen nur ein neuer Schlüssel hilft. Die Art wird aus dem Text
# abgeleitet statt in einer eigenen Spalte gespeichert: Die Texte sind feste
# Konstanten dieses Moduls, und nur sie landen in `garmin_letzter_fehler`.
# Eine zweite Spalte könnte dagegen vom Text abweichen.
SCHLUESSEL_FEHLERTEXTE = {FEHLERTEXT[GarminSchluesselUngueltig], FEHLERTEXT_UNLESBAR}


def fehler_art(text: str | None) -> str | None:
    """"schluessel", "vorruebergehend" oder None (kein Fehler)."""
    if not text:
        return None
    return "schluessel" if text in SCHLUESSEL_FEHLERTEXTE else "vorruebergehend"


def fehlertext(fehler: GarminFehler) -> str:
    for art, text in FEHLERTEXT.items():
        if isinstance(fehler, art):
            return text
    return FEHLERTEXT_ALLGEMEIN


def _tag(wert) -> date | None:
    if not isinstance(wert, str) or len(wert) < 10:
        return None
    try:
        return date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _zahl(wert) -> float | None:
    """Positive Zahl oder None. `bool` zählt nicht, obwohl es in Python eine
    Zahl ist; Garmin schickt für fehlende Werte `null` oder lässt das Feld weg."""
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    wert = float(wert)
    # Dieselbe Obergrenze wie bei der Handeingabe (`HrvCreate`): Ein Wert
    # darüber ist ein Messfehler, keine HRV.
    if wert <= 0 or wert >= 300:
        return None
    return wert


def _messwert(summary: dict) -> tuple[date, float] | None:
    """Tag und rMSSD einer Summary, oder None, wenn sie keinen Wert trägt.

    Hat die Uhr nach dem Aufwachen noch nicht synchronisiert, fehlt der Tag
    oder `lastNightAvg` ist leer. Das ist kein Fehler, nur „noch nicht da".
    """
    status = summary.get("status")
    if isinstance(status, str) and status.upper() in STATUS_OHNE_WERT:
        return None
    tag = _tag(summary.get("calendarDate"))
    wert = _zahl(summary.get("lastNightAvg"))
    if tag is None or wert is None:
        return None
    return tag, wert


def tage_uebernehmen(db: Session, user: User, summaries: list[dict]) -> dict:
    """Tägliche HRV-Werte anlegen oder aktualisieren. Idempotent.

    Der Nutzerfilter steht hier ausdrücklich, obwohl der Morgen-Job in
    `acting_as` läuft: Ohne gesetzten Nutzer (Skripte, Tests, Router ohne
    Anmeldung) filtert der Mandanten-Hook nichts, und „die erste Zeile des
    Tages" wäre dann die eines anderen Athleten. Gleiches Muster wie in
    `hrv_baseline.compute_baseline`.
    """
    # Je Athlet eine Transaktionssperre, bevor gelesen wird. Ohne sie legen
    # zwei gleichzeitige Läufe (Knopf „Jetzt abrufen" und der Morgen-Job zur
    # selben Minute) für denselben Tag je eine Zeile an: Beide lesen „noch
    # keine Zeile", beide schreiben. Eine eindeutige Spalte auf (Nutzer, Tag)
    # geht nicht, weil Bestandsdaten Tage mit zwei Zeilen haben, die nicht
    # automatisch gelöscht werden dürfen. Die Sperre endet mit dem Commit
    # unten; der zweite Lauf sieht dann die Zeilen des ersten.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:art, :nutzer)"),
        {"art": SPERRE_GARMIN_HRV, "nutzer": user.id},
    )
    neu = aktualisiert = ohne_daten = 0
    for summary in summaries or []:
        messwert = _messwert(summary) if isinstance(summary, dict) else None
        if messwert is None:
            ohne_daten += 1
            continue
        tag, wert = messwert
        vorhanden = (
            db.query(HrvMeasurement)
            .filter(HrvMeasurement.user_id == user.id, HrvMeasurement.measured_at == tag)
            .order_by(HrvMeasurement.id.asc())
            .first()
        )
        if vorhanden is None:
            db.add(HrvMeasurement(user_id=user.id, measured_at=tag, rmssd=wert, quelle=QUELLE))
            # Sofort schreiben: Steht derselbe Tag zweimal in der Antwort,
            # findet der zweite Durchgang die eben angelegte Zeile, statt eine
            # zweite anzulegen.
            db.flush()
            neu += 1
        elif vorhanden.rmssd != wert or vorhanden.quelle != QUELLE:
            # Vorher vergleichen statt blind schreiben: Nur so meldet ein
            # zweiter Lauf mit denselben Daten „nichts geändert", und der
            # Zähler in der Kachel bedeutet etwas.
            vorhanden.rmssd = wert
            vorhanden.quelle = QUELLE
            aktualisiert += 1
    db.commit()

    # Einmal am Ende statt je Tag, wie in `POST /hrv`: Jeder neue Wert
    # verschiebt die berechnete Spanne, und die Farben aller Messungen
    # müssen zur geltenden Spanne passen.
    from services.hrv_baseline import recompute_all

    recompute_all(db, user)
    return {"neu": neu, "aktualisiert": aktualisiert, "ohne_daten": ohne_daten}


def _baseline(summary: dict) -> tuple[float, float] | None:
    baseline = summary.get("baseline")
    if not isinstance(baseline, dict):
        return None
    unten = _zahl(baseline.get("balancedLow"))
    oben = _zahl(baseline.get("balancedUpper"))
    if unten is None or oben is None or oben <= unten:
        return None
    return unten, oben


def spanne_uebernehmen(db: Session, user: User, summaries: list[dict]) -> bool:
    """Garmins grünen Bereich als Normalspanne übernehmen.

    Genommen wird die jüngste Summary mit Baseline, sortiert nach Datum statt
    nach der Reihenfolge der Antwort: Die ist nirgends zugesichert.

    `lowUpper` bleibt bewusst unbenutzt. Die rote Grenze wird wie bisher aus
    dem grünen Bereich abgeleitet (`red_from_band`), weil Amir will, dass die
    Ampel so bleibt, wie sie ist.

    Ohne Baseline (Garmin lernt die ersten etwa drei Wochen) bleibt alles, wie
    es ist, und es kommt False zurück.
    """
    from core.deps import get_profile
    from services.hrv_baseline import recompute_all, red_from_band

    kandidaten = []
    for summary in summaries or []:
        if not isinstance(summary, dict):
            continue
        tag = _tag(summary.get("calendarDate"))
        spanne = _baseline(summary)
        if tag is not None and spanne is not None:
            kandidaten.append((tag, spanne))
    if not kandidaten:
        return False
    _, (unten, oben) = max(kandidaten, key=lambda k: k[0])

    profile = get_profile(db, user)
    if profile is None:
        return False
    rot = red_from_band(unten, oben)
    if (
        profile.hrv_range_source == QUELLE
        and profile.hrv_green_min == unten
        and profile.hrv_band_high == oben
        and profile.hrv_red_below == rot
    ):
        return True
    profile.hrv_green_min = unten
    profile.hrv_band_high = oben
    profile.hrv_red_below = rot
    profile.hrv_range_source = QUELLE
    db.commit()
    # Alte Messungen mitziehen, wie früher in `POST /hrv/range`: Sonst tragen
    # sie die Farbe der alten Spanne, und der Verlauf widerspricht der neuen.
    recompute_all(db, user)
    return True


def heute_schon_da(db: Session, user_id: int, heute: date | None = None) -> bool:
    """Liegt für heute schon Garmins Wert vor? Dann muss der Job nicht fragen.

    Nur `quelle == "garmin"` zählt: Ein von Hand eingetragener Wert soll den
    Abruf nicht verhindern, Garmin ist die Quelle.
    """
    heute = heute or date.today()
    return (
        db.query(HrvMeasurement.id)
        .filter(
            HrvMeasurement.user_id == user_id,
            HrvMeasurement.measured_at == heute,
            HrvMeasurement.quelle == QUELLE,
        )
        .first()
        is not None
    )


async def abgleich_fuer(
    db: Session,
    user: User,
    tage: int = 7,
    mit_spanne: bool = False,
    token: str | None = None,
    transport=None,
    heute: date | None = None,
) -> dict:
    """Ein Abgleich für einen Athleten: Token, HRV-Tage, optional Spanne.

    7 Tage Rückblick, damit ein verpasster Morgen (Rechner aus, Garmin
    langsam) von selbst nachgeholt wird. Die Spanne nimmt die Summaries aus
    demselben Abruf, es gibt keinen zweiten Aufruf.

    `token` lässt einen eben getauschten Token weiterverwenden (beim
    Verbinden), damit es bei einem Tausch je Lauf bleibt.

    Fehler von Garmin werden nicht geworfen, sondern als `ok: False` mit
    festem Text zurückgegeben und in `garmin_letzter_fehler` vermerkt. Der
    Schlüssel bleibt bei einem abgelehnten Schlüssel gespeichert: Der Athlet
    soll in der Kachel sehen, was los ist, statt eine leere Kachel vorzufinden.
    """
    from core.deps import get_profile

    profile: AthleteProfile | None = get_profile(db, user)
    if profile is None:
        return {"ok": False, "fehler": "Garmin ist nicht verbunden"}
    if not profile.garmin_api_key:
        if profile.garmin_verbunden_am is not None:
            # Gespeichert, aber nicht lesbar: `core/geheim.py` liefert None,
            # wenn DATA_ENCRYPTION_KEY bzw. JWT_SECRET gewechselt wurde. Ohne
            # diesen Text liefe der Job jeden Morgen still ins Leere.
            profile.garmin_letzter_fehler = FEHLERTEXT_UNLESBAR
            db.commit()
            return {"ok": False, "fehler": profile.garmin_letzter_fehler}
        return {"ok": False, "fehler": "Garmin ist nicht verbunden"}

    heute = heute or date.today()
    try:
        if token is None:
            token = await garmin_personal.token_holen(profile.garmin_api_key, transport=transport)
        summaries = await garmin_personal.hrv_tage(
            token, heute - timedelta(days=tage), heute, transport=transport,
        )
    except GarminFehler as fehler:
        meldung = fehlertext(fehler)
        profile.garmin_letzter_fehler = meldung
        db.commit()
        if isinstance(fehler, GarminRateLimit):
            # „Retry-After beachten" heißt hier: Dieser Athlet wird für diesen
            # Lauf ausgelassen, nicht im Lauf gewartet. Der nächste Versuch
            # kommt frühestens mit dem nächsten stündlichen Lauf (bzw. dem
            # nächsten Knopfdruck). Das genügt: Die Rate-Limits sind nicht
            # dokumentiert, und eine Stunde Abstand ist für einen Abruf am
            # Tag reichlich. Ein eigenes Merken von „nicht vor Zeitpunkt X"
            # wäre eine weitere Spalte für einen Fall, den der Stundentakt
            # schon abdeckt. Die Zahl steht deshalb nur im Log.
            logger.warning("Garmin 429 für Nutzer %s, Retry-After %s", user.id, fehler.retry_after)
        else:
            logger.warning("Garmin-Abruf für Nutzer %s: %s (%s)", user.id,
                           type(fehler).__name__, fehler.status)
        return {"ok": False, "fehler": meldung}

    ergebnis: dict = {"ok": True, **tage_uebernehmen(db, user, summaries)}
    if mit_spanne:
        ergebnis["spanne_uebernommen"] = spanne_uebernehmen(db, user, summaries)

    # Hier kommen später weitere Tageswerte dazu (Ruhepuls, Schlaf), mit
    # demselben Token und in derselben Session.

    profile.garmin_letzter_abruf = datetime.utcnow()
    profile.garmin_letzter_fehler = None
    db.commit()
    return ergebnis
