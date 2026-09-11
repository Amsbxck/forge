"""Zwischenwettkämpfe: was ein B- oder C-Rennen mit der Woche macht.

Ein Athlet hat pro Saison ein Ziel und unterwegs oft mehrere kleinere
Wettkämpfe. Ohne diese Unterscheidung kapert jeder eingetragene Termin die
Vorbereitung — Planlänge, Phasen und Wochenzählung hängen am Ziel, und ein
Halbmarathon im Februar hätte den Triathlon im Juni verdrängt.

Die Einteilung ist trainingsmethodisch üblich:

* **A** — das Saisonziel. Bestimmt Planlänge, Phasen und Wochenzählung.
  Bekommt den vollen Taper.
* **B** — wird ernst genommen, aber nicht angesteuert. Drei bis vier Tage
  reduzierte Last davor, danach Erholung nach Renndauer. Die Saisonstruktur
  bleibt unverändert; der Wettkampf ersetzt die harte Einheit der Woche.
* **C** — wird mitgenommen wie eine Trainingseinheit. Kein Taper, ein
  ruhiger Tag danach.

Die Regeln stehen hier und nicht im Prompt: „im Februar ist ein
Halbmarathon" führt bei einem Sprachmodell mal zu einer kompletten
Taperwoche und mal zu gar nichts.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import RaceGoal, User

logger = logging.getLogger(__name__)

PRIORITIES = ("A", "B", "C")

PRIORITY_LABEL = {
    "A": "Saisonziel",
    "B": "Zwischenwettkampf",
    "C": "Trainingswettkampf",
}

PRIORITY_HINT = {
    "A": "Bestimmt Planlänge, Phasen und Wochenzählung. Voller Taper.",
    "B": "Wird ernst genommen, ändert aber die Saisonstruktur nicht. Kurze Entlastung davor.",
    "C": "Wird als harte Einheit mitgenommen. Keine Entlastung davor.",
}

# Wie viele Tage vor dem Rennen die Last zurückgenommen wird.
B_ENTLASTUNG_TAGE = 4
# Wie weit voraus ein Rennen im Prompt überhaupt erwähnt wird.
VORLAUF_TAGE = 21


def normalize_priority(wert: str | None) -> str:
    p = (wert or "A").strip().upper()
    return p if p in PRIORITIES else "A"


def secondary_races(
    db: Session,
    user: User | None = None,
    von: date | None = None,
    bis: date | None = None,
) -> list[RaceGoal]:
    """B- und C-Rennen in einem Zeitraum, aufsteigend nach Datum."""
    query = db.query(RaceGoal).filter(RaceGoal.priority.in_(("B", "C")))
    if user is not None:
        query = query.filter(RaceGoal.user_id == user.id)
    if von is not None:
        query = query.filter(RaceGoal.race_date >= von)
    if bis is not None:
        query = query.filter(RaceGoal.race_date <= bis)
    return query.order_by(RaceGoal.race_date.asc()).all()


def _tage(anzahl: int) -> str:
    return f"{anzahl} Tag" if anzahl == 1 else f"{anzahl} Tage"


def _erholung_tage(rennen: RaceGoal) -> int:
    """Ruhige Tage nach dem Rennen.

    Grobe Faustregel aus der Praxis: etwa ein leichter Tag je Rennstunde,
    bei kurzen Distanzen mindestens einer, gedeckelt bei fünf — darüber
    hinaus schadet die Pause mehr, als der Wettkampf gekostet hat.
    """
    stunden = {
        "sprint": 1, "olympic": 3, "middle": 6, "full": 12,
        "10k": 1, "half_marathon": 2, "marathon": 4,
    }.get((rennen.distance or "").lower(), 2)
    return max(1, min(5, round(stunden)))


def week_block(
    db: Session,
    week_start: date,
    week_end: date,
    user: User | None = None,
) -> str:
    """Vorgaben für die geplante Woche. Leer, wenn nichts ansteht."""
    horizont = week_end + timedelta(days=VORLAUF_TAGE)
    rennen = secondary_races(db, user, von=week_start - timedelta(days=7), bis=horizont)
    if not rennen:
        return ""

    zeilen: list[str] = []

    for r in rennen:
        label = r.race_name or r.label
        wochentag = r.race_date.strftime("%A")
        deutsch = {
            "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
            "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag",
            "Sunday": "Sonntag",
        }.get(wochentag, wochentag)

        in_woche = week_start <= r.race_date <= week_end
        davor = week_start <= r.race_date - timedelta(days=B_ENTLASTUNG_TAGE) <= week_end
        danach = r.race_date < week_start

        if in_woche and r.priority == "B":
            erholung = _erholung_tage(r)
            zeilen.append(
                f"WETTKAMPF IN DIESER WOCHE: {label} am {deutsch}, {r.race_date} (B-Rennen). "
                f"Der Wettkampf ersetzt die harte Einheit der Woche — plane keine zweite "
                f"Belastungseinheit. Die {_tage(3)} davor: Umfang etwa halbieren, am Vortag "
                f"nur 20–30 Minuten locker mit 3 × 1 Minute im Renntempo. Danach "
                f"{_tage(erholung)} ausschließlich Z1/Z2, keine Intervalle."
            )
        elif in_woche and r.priority == "C":
            zeilen.append(
                f"WETTKAMPF IN DIESER WOCHE: {label} am {deutsch}, {r.race_date} (C-Rennen). "
                "Wird als harte Einheit mitgenommen: kein Taper davor, den Wochenplan sonst "
                "unverändert lassen. Der Tag danach ist locker oder frei."
            )
        elif davor and r.priority == "B":
            zeilen.append(
                f"In der kommenden Woche steht {label} an ({r.race_date}, B-Rennen). "
                "Die letzten harten Einheiten dieser Woche früh legen, damit vor dem "
                "Wettkampf drei ruhige Tage bleiben."
            )
        elif danach and (week_start - r.race_date).days <= _erholung_tage(r):
            zeilen.append(
                f"{label} liegt {_tage((week_start - r.race_date).days)} zurück "
                f"({r.race_date}, {r.priority}-Rennen). Die Woche beginnt locker; "
                "die erste harte Einheit erst, wenn die Erholung abgeschlossen ist."
            )
        elif r.priority == "B" and (r.race_date - week_end).days <= VORLAUF_TAGE:
            tage_hin = (r.race_date - week_end).days
            zeilen.append(
                f"Ausblick: {label} am {r.race_date} (B-Rennen) — {_tage(tage_hin)} "
                "nach dieser Woche. Die Saisonstruktur bleibt unverändert; dieser "
                "Wettkampf ist kein Ziel, sondern ein Zwischenschritt."
            )

    if not zeilen:
        return ""

    aufzaehlung = "\n".join(f"- {z}" for z in zeilen)
    return (
        "## WETTKÄMPFE IN DER SAISON (nicht das Saisonziel)\n\n"
        f"{aufzaehlung}\n\n"
        "Diese Termine ändern weder Planlänge noch Phase. Das Saisonziel bleibt "
        "unverändert das A-Rennen.\n\n---"
    )
