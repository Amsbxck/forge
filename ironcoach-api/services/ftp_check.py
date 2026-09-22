"""Bemerken, wenn eine normale Ausfahrt die hinterlegte FTP in Frage stellt.

Die FTP wird ausschliesslich aus der Testwoche abgeleitet oder von Hand
eingetragen — eine gewöhnliche Fahrt ändert sie nie. Das ist Absicht: Ein
einzelner harter Anstieg oder ein Gruppenantritt zöge den Wert nach oben,
und danach wäre jede Wattvorgabe der Folgemonate zu hart.

Dieses Modul ändert deshalb nichts. Es schaut nur hin und meldet, wenn die
Leistung in einer normalen Fahrt nicht mehr zur hinterlegten FTP passt —
mit Datum und Zahlen, damit der Athlet selbst entscheiden kann. Ein Beleg
statt einer Schätzung.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import AthleteProfile, TrainingSession
from services.segments import best_effort_power, erkenne_stufentest

logger = logging.getLogger(__name__)

# Zeitraum, in dem gesucht wird. Kürzer als die 90 Tage bis zum Neutest:
# Der Hinweis soll auf die aktuelle Form zeigen, nicht auf den Frühling.
ZEITRAUM_TAGE = 60
# Mindestdauer einer Fahrt, damit ein 20-Minuten-Fenster überhaupt hineinpasst.
MIN_DAUER_MIN = 25
# Ab welcher Abweichung gemeldet wird. Darunter ist es Tagesform: Ein
# Unterschied von zwei Prozent sagt nichts über die Schwelle aus, und ein
# Hinweis, der ständig erscheint, wird nicht mehr gelesen.
MELDESCHWELLE = 1.04


def ftp_ueberpruefung(db: Session, profile: AthleteProfile | None,
                      tage: int = ZEITRAUM_TAGE) -> dict | None:
    """Passt die hinterlegte FTP noch zu dem, was gefahren wird?

    Gibt None zurück, wenn es nichts zu sagen gibt — kein Hinweis ist
    besser als einer, der bei jedem Öffnen dasteht.
    """
    from services.benchmark import SCHWELLEN_FAKTOR

    if profile is None or not profile.ftp_watts:
        return None

    seit = date.today() - timedelta(days=tage)
    fahrten = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.discipline == "bike",
            TrainingSession.session_date >= seit,
            TrainingSession.deleted_at == None,  # noqa: E711
            TrainingSession.duration_min >= MIN_DAUER_MIN,
        )
        .order_by(TrainingSession.session_date.desc())
        .all()
    )

    beste = None
    for fahrt in fahrten:
        # Stufentests überspringen: Ihr bestes 20-Minuten-Fenster enthält
        # die leichten Anfangsstufen und liegt systematisch zu niedrig — als
        # Beleg für eine zu niedrige FTP taugt es nicht.
        if erkenne_stufentest(fahrt):
            continue
        leistung = best_effort_power(fahrt, seconds=1200)
        if not leistung:
            continue
        if beste is None or leistung["avg_watts"] > beste[0]["avg_watts"]:
            beste = (leistung, fahrt)

    if beste is None:
        return None

    leistung, fahrt = beste
    hergeleitet = round(leistung["avg_watts"] * SCHWELLEN_FAKTOR)
    if hergeleitet < profile.ftp_watts * MELDESCHWELLE:
        return None

    return {
        "hinterlegt_watt": profile.ftp_watts,
        "hergeleitet_watt": hergeleitet,
        "best_20min_watts": leistung["avg_watts"],
        "differenz_watt": hergeleitet - profile.ftp_watts,
        "datum": str(fahrt.session_date),
        "session_id": fahrt.id,
        "quelle": profile.ftp_source,
        "text": (
            f"Am {fahrt.session_date.strftime('%d.%m.')} bist du 20 Minuten mit "
            f"{leistung['avg_watts']} W gefahren. Das entspräche einer FTP von "
            f"{hergeleitet} W — hinterlegt sind {profile.ftp_watts} W."
        ),
    }


def prompt_block(db: Session, profile: AthleteProfile | None) -> str:
    """Derselbe Befund für den Coach. Leer, wenn es nichts zu melden gibt."""
    befund = ftp_ueberpruefung(db, profile)
    if not befund:
        return ""
    return (
        "## HINWEIS ZUR FTP\n\n"
        f"{befund['text']} Die Wattvorgaben beruhen auf dem hinterlegten Wert und "
        "sind damit möglicherweise zu niedrig. Ändere ihn nicht selbst — schlage "
        "eine Testwoche vor, sobald die Phase es zulässt.\n\n---"
    )
