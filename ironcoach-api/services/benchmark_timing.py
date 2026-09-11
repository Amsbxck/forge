"""Wann darf eine Testwoche liegen — und wann nicht.

Die Testwoche lag bisher fest auf Woche 1 am Startdatum des Plans. Für einen
neuen Athleten stimmt das; für jeden anderen liegt dieses Datum in der
Vergangenheit, und der Test landete in einer längst vergangenen Woche.

Richtig ist die **kommende** Woche — mit drei Ausnahmen, in denen ein
Maximaltest schadet statt zu messen:

* **Kurz nach einem Wettkampf.** Ein Rennen hinterlässt zwei bis drei Wochen
  Restermüdung. Ein Test misst dann die Erholung, nicht die Leistung — und
  weil die Werte anschließend als Vorgabe gelten, wäre jede Einheit der
  Folgemonate zu leicht. Genau die Situation, aus der Amir gerade kommt.
* **Bei laufender Krankheit oder Verletzung.** Braucht keine Begründung.
* **Unmittelbar vor dem Saisonziel.** In Taper und Wettkampfwoche gibt es
  nichts zu messen, was sich noch auswirken könnte.

Die Off Season ist ausdrücklich **kein** Ausschlussgrund. Sie ist im
Gegenteil der beste Zeitpunkt: kein Wettkampfdruck, kein Formaufbau, der
gestört würde. Damit dabei keine Überlastung entsteht, wird die Testwoche
dort entzerrt — siehe `entzerren()`.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import HealthEvent, RaceResult

logger = logging.getLogger(__name__)

# Erholungsfenster nach einem Wettkampf, in Tagen. Nach einer Langdistanz
# eher mehr, nach einem Sprint weniger — die längere Frist ist die sichere
# Annahme, weil ein zu früh gemessener Wert monatelang nachwirkt.
SPERRE_NACH_RENNEN = 21
# Wie nah vor dem Saisonziel kein Test mehr sinnvoll ist.
SPERRE_VOR_ZIEL = 21


def naechster_montag(ab: date | None = None) -> date:
    """Der Montag der kommenden Woche.

    Ausdrücklich der nächste, nie der laufende: Eine Testwoche mitten in der
    Woche zu beginnen, würde die bereits absolvierten Einheiten dieser Woche
    zur Vorermüdung des Tests machen.
    """
    ab = ab or date.today()
    return ab + timedelta(days=7 - ab.weekday())


def pruefe(db: Session, ziel_datum: date | None = None,
           heute: date | None = None) -> dict:
    """Kann die Testwoche in der kommenden Woche liegen?

    Gibt immer einen Termin zurück, auch bei einer Sperre — dann den frühesten
    sinnvollen. Ein blosses „geht nicht" ließe den Athleten ohne nächsten
    Schritt zurück.
    """
    heute = heute or date.today()
    start = naechster_montag(heute)
    gruende: list[str] = []
    frueheste = start

    # --- Zurückliegender Wettkampf ---
    letztes = (
        db.query(RaceResult)
        .filter(RaceResult.race_date <= heute)
        .order_by(RaceResult.race_date.desc())
        .first()
    )
    if letztes is not None:
        seit = (heute - letztes.race_date).days
        if seit < SPERRE_NACH_RENNEN:
            frei = naechster_montag(letztes.race_date + timedelta(days=SPERRE_NACH_RENNEN))
            frueheste = max(frueheste, frei)
            gruende.append(
                f"Dein Wettkampf ist erst {seit} Tage her. Ein Maximaltest misst "
                f"jetzt vor allem die Restermüdung — und die zu niedrigen Werte "
                f"würden anschließend monatelang als Vorgabe gelten."
            )

    # --- Laufende Krankheit oder Verletzung ---
    offen = db.query(HealthEvent).filter(HealthEvent.end_date.is_(None)).first()
    if offen is not None:
        bezeichnung = "Verletzung" if offen.kind == "injury" else "Krankheit"
        gruende.append(f"Es ist eine {bezeichnung} als laufend gemeldet.")
        # Kein Ersatztermin: Wann das vorbei ist, weiß nur der Athlet.
        frueheste = None

    # --- Kurz vor dem Saisonziel ---
    # Gemessen ab **heute**, nicht ab dem Start der Testwoche. Vom Start aus
    # gerechnet lag ein Wettkampf, der noch vor dem kommenden Montag liegt,
    # bereits in der Vergangenheit — die Sperre griff ausgerechnet in der
    # Woche unmittelbar vor dem Rennen nicht.
    if ziel_datum is not None and frueheste is not None:
        tage_bis = (ziel_datum - heute).days
        if 0 <= tage_bis < SPERRE_VOR_ZIEL:
            gruende.append(
                f"Bis zum Wettkampf sind es nur noch {tage_bis} Tage. So kurz "
                f"davor gibt es nichts mehr zu messen, was sich noch auswirkt — "
                f"und ein harter Test kostet Frische."
            )
            frueheste = naechster_montag(ziel_datum + timedelta(days=SPERRE_NACH_RENNEN))

    return {
        "moeglich": not gruende,
        "start": start if not gruende else None,
        "frueheste": frueheste,
        "gruende": gruende,
    }


def entzerren(tage: list[dict]) -> list[dict]:
    """Testwoche für die Off Season entschärfen.

    In der Off Season fehlt die Grundlage, auf der ein Maximaltest normal
    verkraftet wird — zwei harte Tests in einer Woche führen dort schnell zu
    Überlastung. Statt sie zu streichen, bekommt die Woche nur **einen**
    Maximaltest; die übrigen werden zu lockeren Einheiten, und der zweite Test
    wandert in die Folgewoche.

    Ausdrücklich kein Verzicht auf Messung: Ohne Werte plant der Coach die
    ganze Off Season nach Gefühl, und das ist die schlechtere Alternative.
    """
    entschaerft = []
    harte_gesehen = False
    for tag in tage:
        ist_test = "BENCHMARK" in (tag.get("notes") or "")
        if ist_test and tag.get("training_type") == "threshold":
            if harte_gesehen:
                # Zweiter Maximaltest → lockere Einheit, Test später.
                entschaerft.append({
                    **tag,
                    "training_type": "z2_endurance",
                    "duration_min": min(tag.get("duration_min") or 45, 45),
                    "notes": (
                        "Locker nach Gefühl. Der zweite Maximaltest wurde in die "
                        "Folgewoche verschoben — zwei harte Tests in einer Woche "
                        "sind ohne Grundlagenumfang zu viel."
                    ),
                    "details": None,
                })
                continue
            harte_gesehen = True
        entschaerft.append(tag)
    return entschaerft
