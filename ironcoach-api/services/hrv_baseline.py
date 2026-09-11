"""Die HRV-Ampel — gegen die eigene Normalspanne, nicht gegen feste Zahlen.

Bisher galt: über 80 grün, ab 70 gelb, darunter rot. Das sind die Werte eines
einzelnen Athleten. rMSSD ist aber zwischen Menschen extrem verschieden — 35
und 120 sind beide völlig normal, je nach Person, Alter und Messgerät. Für
jemanden mit einer Normallage um 45 stünde die Ampel dauerhaft auf Rot, und
weil der Zustand in die Planung eingeht, würde der Coach dauerhaft Intensität
streichen. Eine falsche Ampel ist damit schlimmer als gar keine.

Deshalb wird verglichen, was allein vergleichbar ist: der heutige Wert gegen
die eigene Streuung der letzten Wochen.

    grün   ab Mittelwert − 0,5 σ
    gelb   zwischen Mittelwert − 1,0 σ und − 0,5 σ
    rot    darunter

Solange zu wenige Messungen vorliegen, gibt es keine Ampel — geraten wäre
schlechter als offen zu sagen, dass die Grundlinie noch entsteht. Wer seine
Spanne kennt, etwa aus Garmin Connect, kann sie eintragen und überspringt
die Wartezeit.
"""

import logging
import statistics
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import AthleteProfile, HrvMeasurement, User

logger = logging.getLogger(__name__)

# Die Grundlinie zählt Messungen, nicht Tage. Ein starres 60-Tage-Fenster
# scheitert an unregelmäßigem Messen: Wer zweimal pro Woche misst, hat darin
# zu wenige Werte, obwohl reichlich Daten vorliegen. Genommen werden die
# jüngsten Messungen innerhalb eines halben Jahres — älteres beschreibt einen
# anderen Trainingszustand.
FENSTER_TAGE = 180
MAX_MESSUNGEN = 30
# Darunter ist eine Standardabweichung nicht aussagekräftig.
MIN_MESSUNGEN = 14

GRUEN_SIGMA = 0.5
ROT_SIGMA = 1.0

# Aus einem eingetragenen grünen Bereich (wie Garmin ihn anzeigt) muss die
# rote Grenze abgeleitet werden — die Uhr nennt nur „ausgeglichen" und
# „darunter". Ein Viertel der Bandbreite unterhalb entspricht etwa einer
# halben Standardabweichung, wenn das Band rund zwei Standardabweichungen
# breit ist. So skaliert der gelbe Bereich mit der eigenen Streuung statt
# mit einer festen Zahl.
GELB_ANTEIL_BANDBREITE = 0.25


def red_from_band(unten: float, oben: float) -> float:
    """Rote Grenze aus dem grünen Bereich."""
    breite = max(0.0, oben - unten)
    return round(unten - GELB_ANTEIL_BANDBREITE * breite, 1)


def compute_baseline(db: Session, user: User | None = None, today: date | None = None) -> dict | None:
    """Mittelwert und Streuung der letzten Wochen."""
    today = today or date.today()
    cutoff = today - timedelta(days=FENSTER_TAGE)

    query = db.query(HrvMeasurement).filter(HrvMeasurement.measured_at >= cutoff)
    if user is not None:
        query = query.filter(HrvMeasurement.user_id == user.id)
    messungen = query.order_by(HrvMeasurement.measured_at.desc()).limit(MAX_MESSUNGEN).all()
    werte = [m.rmssd for m in messungen if m.rmssd]

    if len(werte) < MIN_MESSUNGEN:
        return {
            "status": "zu_wenige_daten",
            "messungen": len(werte),
            "benoetigt": MIN_MESSUNGEN,
        }

    mittel = statistics.fmean(werte)
    streuung = statistics.pstdev(werte)
    return {
        "status": "ok",
        "messungen": len(werte),
        "zeitraum_tage": FENSTER_TAGE,
        "mean": round(mittel, 1),
        "sd": round(streuung, 1),
        "gruen_ab": round(mittel - GRUEN_SIGMA * streuung, 1),
        "rot_unter": round(mittel - ROT_SIGMA * streuung, 1),
    }


def thresholds_for(profile: AthleteProfile | None, baseline: dict | None) -> dict | None:
    """Die geltenden Grenzen: eingetragene zuerst, sonst die berechneten."""
    if profile is not None and profile.hrv_range_source == "manual" \
            and profile.hrv_green_min and profile.hrv_red_below:
        return {
            "gruen_ab": profile.hrv_green_min,
            "gruen_bis": profile.hrv_band_high,
            "rot_unter": profile.hrv_red_below,
            "quelle": "manual",
        }
    if baseline and baseline.get("status") == "ok":
        return {
            "gruen_ab": baseline["gruen_ab"],
            "rot_unter": baseline["rot_unter"],
            "quelle": "auto",
        }
    return None


def status_for(rmssd: float, grenzen: dict | None) -> str | None:
    """Ampelfarbe. None, solange keine Grundlinie existiert."""
    if not grenzen or rmssd is None:
        return None
    if rmssd >= grenzen["gruen_ab"]:
        return "green"
    if rmssd >= grenzen["rot_unter"]:
        return "yellow"
    return "red"


def evaluate(db: Session, rmssd: float, user: User | None = None) -> tuple[str | None, dict]:
    """Ampel für einen Messwert samt der Begründung."""
    from core.deps import get_profile

    profile = get_profile(db, user)
    baseline = compute_baseline(db, user)
    grenzen = thresholds_for(profile, baseline)
    return status_for(rmssd, grenzen), {"baseline": baseline, "grenzen": grenzen}


def recompute_all(db: Session, user: User | None = None) -> int:
    """Alle gespeicherten Messungen neu bewerten.

    Nötig, wenn sich die Grundlinie verschiebt oder eine Spanne eingetragen
    wird — sonst tragen alte Messungen weiter die Farbe von gestern.
    """
    baseline = compute_baseline(db, user)
    from core.deps import get_profile

    grenzen = thresholds_for(get_profile(db, user), baseline)
    if not grenzen:
        return 0

    query = db.query(HrvMeasurement)
    if user is not None:
        query = query.filter(HrvMeasurement.user_id == user.id)

    geaendert = 0
    for messung in query.all():
        neu = status_for(messung.rmssd, grenzen)
        if neu and messung.hrv_status != neu:
            messung.hrv_status = neu
            geaendert += 1
    db.commit()
    return geaendert
