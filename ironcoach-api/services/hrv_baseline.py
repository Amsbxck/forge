"""Die HRV-Ampel — gegen die eigene Normalspanne, nicht gegen feste Zahlen.

Bisher galt: über 80 grün, ab 70 gelb, darunter rot. Das sind die Werte eines
einzelnen Athleten. rMSSD ist aber zwischen Menschen extrem verschieden — 35
und 120 sind beide völlig normal, je nach Person, Alter und Messgerät. Für
jemanden mit einer Normallage um 45 stünde die Ampel dauerhaft auf Rot, und
weil der Zustand in die Planung eingeht, würde der Coach dauerhaft Intensität
streichen. Eine falsche Ampel ist damit schlimmer als gar keine.

Deshalb wird verglichen, was allein vergleichbar ist: der heutige Wert gegen
die eigene Streuung der letzten Wochen.

    Normalspanne   Mittelwert ± 0,5 σ
    gelb           zwischen Mittelwert − 1,0 σ und − 0,5 σ
    rot            darunter

Die halbe Standardabweichung ist nicht beliebig gewählt: Sie ist die
**kleinste bedeutsame Änderung** — die kleinste Verschiebung, die mehr ist als
das normale Rauschen der Messung. Innerhalb der Spanne ist ein Unterschied
Zufall und keine Aussage; wer darauf reagiert, reagiert auf Messrauschen.

Die Spanne hat deshalb **zwei** Grenzen. Die untere entscheidet über die Ampel,
die obere sagt, wann ein Wert tatsächlich über der eigenen Norm liegt. Lange
gab es nur die untere: Alles darüber war grün, ob fünf oder fünfzig Prozent —
und damit war nicht zu erkennen, ob ein guter Wert wirklich gut war oder nur
innerhalb der Streuung lag.

Solange zu wenige Messungen vorliegen, gibt es keine Ampel — geraten wäre
schlechter als offen zu sagen, dass die Grundlinie noch entsteht. Wer Garmin
Connect verbindet, bekommt Garmins Baseline als Spanne (`services/garmin_hrv.py`)
und überspringt die Wartezeit.
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

# Die halbe Standardabweichung: die kleinste Verschiebung, die über das
# Messrauschen hinausgeht. Sie begrenzt die Normalspanne nach **beiden** Seiten.
BAND_SIGMA = 0.5
GRUEN_SIGMA = BAND_SIGMA   # die untere Bandgrenze ist die Ampelschwelle
ROT_SIGMA = 1.0

# Aus Garmins grünem Bereich (früher abgetippt, jetzt automatisch) muss die
# rote Grenze abgeleitet werden — die Uhr nennt nur „ausgeglichen" und
# „darunter". Ein Viertel der Bandbreite unterhalb entspricht etwa einer
# halben Standardabweichung, wenn das Band rund zwei Standardabweichungen
# breit ist. So skaliert der gelbe Bereich mit der eigenen Streuung statt
# mit einer festen Zahl.
GELB_ANTEIL_BANDBREITE = 0.25


# Spannen aus der Uhr. Beide gelten unbedingt vor der Rechnung, siehe
# `thresholds_for`. Eine Stelle statt zweier Vergleiche, damit eine dritte
# Quelle nicht an einer Stelle vergessen wird.
VORRANG_QUELLEN = ("manual", "garmin")


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
        # Die Normalspanne, beide Grenzen. `gruen_ab` ist identisch mit
        # `band_unten` und bleibt stehen, weil die Ampel darauf verweist —
        # zwei Namen für eine Zahl sind hier ehrlicher als ein Name für zwei
        # Bedeutungen.
        "band_unten": round(mittel - BAND_SIGMA * streuung, 1),
        "band_oben": round(mittel + BAND_SIGMA * streuung, 1),
        "gruen_ab": round(mittel - GRUEN_SIGMA * streuung, 1),
        "rot_unter": round(mittel - ROT_SIGMA * streuung, 1),
    }


def thresholds_for(profile: AthleteProfile | None, baseline: dict | None) -> dict | None:
    """Die geltenden Grenzen.

    **Garmins Baseline hat unbedingten Vorrang** (`hrv_range_source ==
    "garmin"`, sonntags aus Garmin Connect aktualisiert, `services/garmin_hrv.py`).
    Sie kommt aus der Uhr, die über Monate und mit dem eigenen Messverfahren
    gelernt hat; die Rechnung hier sieht nur die Werte, die in dieser App
    gelandet sind.

    **Eine früher von Hand eingetragene Spanne (`"manual"`) gilt mit demselben
    Vorrang weiter.** Wer ein Band eingetragen hat und Garmin nicht verbindet,
    behält es. Neu setzen lässt sie sich über die Oberfläche nicht mehr: Die
    Spanne ist nicht von Hand änderbar, sie kommt aus Garmin.

    Hier wurden zuvor **beide** Werte verlangt, `hrv_green_min` und
    `hrv_red_below`. Fehlte die rote Grenze, fiel die Funktion stillschweigend
    auf die berechnete Spanne zurück — die eingetragene galt dann nicht, ohne
    dass irgendwo etwas davon stand. Jetzt genügt die untere Bandgrenze; die
    rote wird daraus abgeleitet, so wie beim Eintragen auch.
    """
    quelle = getattr(profile, "hrv_range_source", None) if profile is not None else None
    if quelle in VORRANG_QUELLEN and profile.hrv_green_min:
        rot = profile.hrv_red_below
        if not rot:
            rot = (
                red_from_band(profile.hrv_green_min, profile.hrv_band_high)
                if profile.hrv_band_high
                else round(profile.hrv_green_min * 0.9, 1)
            )
        return {
            "gruen_ab": profile.hrv_green_min,
            "gruen_bis": profile.hrv_band_high,
            "rot_unter": rot,
            "quelle": quelle,
        }
    if baseline and baseline.get("status") == "ok":
        return {
            "gruen_ab": baseline["gruen_ab"],
            "gruen_bis": baseline["band_oben"],
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


def ueber_band(rmssd: float | None, grenzen: dict | None) -> bool:
    """Liegt der Wert über der eigenen Normalspanne?

    Keine eigene Ampelfarbe: Über der Spanne ist nicht besser als grün, es ist
    grün — nur eben nachweislich, nicht innerhalb des Rauschens. Als Aussage ist
    das etwas anderes und gehört deshalb getrennt gemeldet, nicht in den Status
    hineingemischt. Ein vierter Statuswert hätte dagegen jede Stelle berührt,
    die heute drei kennt.
    """
    oben = (grenzen or {}).get("gruen_bis")
    return bool(oben and rmssd is not None and rmssd > oben)


def evaluate(db: Session, rmssd: float, user: User | None = None) -> tuple[str | None, dict]:
    """Ampel für einen Messwert samt der Begründung."""
    from core.deps import get_profile

    profile = get_profile(db, user)
    baseline = compute_baseline(db, user)
    grenzen = thresholds_for(profile, baseline)
    return status_for(rmssd, grenzen), {
        "baseline": baseline,
        "grenzen": grenzen,
        "ueber_band": ueber_band(rmssd, grenzen),
    }


def recompute_all(db: Session, user: User | None = None) -> int:
    """Alle gespeicherten Messungen neu bewerten.

    Nötig, wenn sich die Grundlinie verschiebt oder Garmin eine neue Spanne
    liefert — sonst tragen alte Messungen weiter die Farbe von gestern.

    **Eine Spanne aus der Uhr (Garmin oder früher eingetragen) gilt für alle
    Messungen** — sie hat unbedingten Vorrang (siehe `thresholds_for`).

    Ohne sie bekommt jede Messung die Farbe nach der Spanne **ihres** Tages:
    dieselbe Rechnung wie `compute_baseline` (bis zu 30 Messungen aus den
    letzten 180 Tagen davor), wie das Diagramm sie als Fläche zeichnet. Vorher
    wurde die ganze Historie gegen die heutige Spanne gefärbt — ein Punkt lag
    sichtbar in seiner gezeichneten Spanne und war trotzdem rot.

    Gibt es für eine Messung keine Spanne (zu wenige Werte), verliert sie ihre
    Farbe. Vorher blieb sie stehen, etwa nachdem die eingetragene Spanne
    gelöscht wurde — gefärbt nach Grenzen, die es nicht mehr gab.
    """
    from core.deps import get_profile

    profile = get_profile(db, user)
    vorrang = thresholds_for(profile, None)

    query = db.query(HrvMeasurement)
    if user is not None:
        query = query.filter(HrvMeasurement.user_id == user.id)
    messungen = query.order_by(HrvMeasurement.measured_at.asc(), HrvMeasurement.id.asc()).all()

    geaendert = 0
    for i, messung in enumerate(messungen):
        if vorrang is not None:
            grenzen = vorrang
        else:
            grenze = messung.measured_at - timedelta(days=FENSTER_TAGE)
            fenster = [
                m.rmssd for m in messungen[: i + 1]
                if m.rmssd and m.measured_at >= grenze
            ][-MAX_MESSUNGEN:]
            if len(fenster) < MIN_MESSUNGEN:
                grenzen = None
            else:
                mittel = statistics.fmean(fenster)
                streuung = statistics.pstdev(fenster)
                grenzen = {
                    "gruen_ab": round(mittel - GRUEN_SIGMA * streuung, 1),
                    "rot_unter": round(mittel - ROT_SIGMA * streuung, 1),
                }
        neu = status_for(messung.rmssd, grenzen)
        if messung.hrv_status != neu:
            messung.hrv_status = neu
            geaendert += 1
    db.commit()
    return geaendert
