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

# Wie viele Tage nach einer Messung wieder getestet wird. Dieselbe Zahl, die
# `services/zones.py` benutzt, um die Werte als überholt zu melden — sie
# stammt von dort und wird importiert, damit nicht zwei Fristen nebeneinander
# stehen und auseinanderlaufen.
#
# Ein Maximaltest kostet eine Woche Training und zwei bis drei Tage
# Erholung. Ihn zu wiederholen, solange die Werte frisch sind, bringt keine
# neue Auskunft und nimmt dem Aufbau eine Woche.
from services.zones import TAGE_BIS_NEUTEST

# Wie lange vorher angekündigt wird, dass ein Test ansteht. Eine Woche:
# genug, um die Woche freizuhalten, und nah genug, dass es nicht in
# Vergessenheit gerät.
VORWARNUNG_TAGE = 7


def naechster_montag(ab: date | None = None) -> date:
    """Der Montag der kommenden Woche.

    Ausdrücklich der nächste, nie der laufende: Eine Testwoche mitten in der
    Woche zu beginnen, würde die bereits absolvierten Einheiten dieser Woche
    zur Vorermüdung des Tests machen.
    """
    ab = ab or date.today()
    return ab + timedelta(days=7 - ab.weekday())


def montag_ab(tag: date) -> date:
    """Der erste Montag an oder nach `tag`.

    Unterschied zu `naechster_montag`: Fällt `tag` selbst auf einen Montag,
    ist das die Antwort. Für den frühesten erlaubten Termin ist das richtig —
    `naechster_montag` hätte dort eine ganze Woche draufgelegt, weil es
    ausdrücklich nie den laufenden Montag zurückgibt.
    """
    return tag + timedelta(days=(7 - tag.weekday()) % 7)


def pruefe(db: Session, ziel_datum: date | None = None,
           heute: date | None = None, gemessen_am: date | None = None) -> dict:
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
        # Gemessen ab dem Montag der Testwoche, nicht ab heute: Getestet wird
        # nicht heute, sondern in der kommenden Woche. Wer am 16. Tag nach
        # seinem Rennen steht und dessen kommender Montag der 22. Tag ist, hat
        # die Erholungsfrist zum Testzeitpunkt voll. Ihn trotzdem zu sperren
        # verschiebt den Test grundlos um eine weitere Woche — und die
        # Begründung ("dein Wettkampf ist erst 16 Tage her") beschreibt einen
        # Tag, an dem gar nicht getestet wird.
        abstand_bei_start = (start - letztes.race_date).days
        if abstand_bei_start < SPERRE_NACH_RENNEN:
            frei = montag_ab(letztes.race_date + timedelta(days=SPERRE_NACH_RENNEN))
            frueheste = max(frueheste, frei)
            gruende.append(
                f"Beim Start der Testwoche am {start} liegt dein Wettkampf erst "
                f"{abstand_bei_start} Tage zurück. Ein Maximaltest misst dann vor "
                f"allem die Restermüdung — und die zu niedrigen Werte würden "
                f"anschließend monatelang als Vorgabe gelten."
            )

    # --- Werte noch frisch ---
    # Der Test misst, was sich seit der letzten Messung verändert hat. Nach
    # drei Wochen hat sich nichts verändert, was eine Woche Training und
    # zwei Tage Erholung wert wäre — die Zahlen kämen fast gleich heraus,
    # und die Woche fehlte im Aufbau.
    if gemessen_am is not None:
        faellig = gemessen_am + timedelta(days=TAGE_BIS_NEUTEST)
        if start < faellig:
            seit = (heute - gemessen_am).days
            frueheste = max(frueheste, montag_ab(faellig)) if frueheste else frueheste
            gruende.append(
                f"Deine Werte sind erst {seit} Tage alt. Ein neuer Maximaltest "
                f"misst dann fast dasselbe, kostet aber eine Trainingswoche und "
                f"zwei Tage Erholung. Fällig wird er am {faellig}."
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


def faelligkeit(gemessen_am: date | None, heute: date | None = None) -> dict:
    """Wann die nächste Testwoche ansteht — und ob es Zeit wird, das zu sagen.

    Der Test wiederholt sich alle drei Monate. Ohne Ankündigung fällt er
    entweder aus oder er fällt in eine Woche, die schon verplant ist: Wer am
    Montag erfährt, dass diese Woche gemessen wird, hat den Wettkampf am
    Sonntag bereits zugesagt.

    Eine Woche Vorlauf ist genug, um die Woche freizuhalten, und nah genug,
    dass es nicht wieder in Vergessenheit gerät.
    """
    heute = heute or date.today()

    if gemessen_am is None:
        # Nie gemessen: Die Testwoche steht aus, nicht an einem Datum,
        # sondern von Anfang an.
        return {
            "faellig_am": None,
            "tage_hin": None,
            "faellig": True,
            "vorwarnung": True,
            "text": (
                "Deine Werte wurden noch nie gemessen. Die Testwoche ist der "
                "erste Schritt — bis dahin plant der Coach mit Schätzungen."
            ),
        }

    faellig_am = gemessen_am + timedelta(days=TAGE_BIS_NEUTEST)
    tage_hin = (faellig_am - heute).days
    start = montag_ab(faellig_am)

    if tage_hin > VORWARNUNG_TAGE:
        return {"faellig_am": faellig_am, "tage_hin": tage_hin,
                "faellig": False, "vorwarnung": False, "text": None}

    if tage_hin > 0:
        text = (
            f"In {tage_hin} Tagen steht die nächste Testwoche an — deine Werte "
            f"sind dann drei Monate alt. Halte dir die Woche ab {start} frei."
        )
    else:
        text = (
            f"Deine Werte sind {(heute - gemessen_am).days} Tage alt. Die "
            f"Testwoche ist fällig; lege sie an, sobald die Phase es zulässt."
        )

    return {"faellig_am": faellig_am, "tage_hin": tage_hin,
            "faellig": tage_hin <= 0, "vorwarnung": True,
            "start": start, "text": text}


def prompt_block(gemessen_am: date | None, heute: date | None = None) -> str:
    """Derselbe Befund für den Coach. Leer, solange nichts ansteht."""
    stand = faelligkeit(gemessen_am, heute)
    if not stand["vorwarnung"]:
        return ""
    return (
        "## TESTWOCHE\n\n"
        f"{stand['text']} Plane sie nicht in eine Deload- oder Wettkampfwoche "
        "und nicht in die drei Wochen nach einem Rennen.\n\n---"
    )
