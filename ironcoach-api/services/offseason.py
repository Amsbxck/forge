"""Off Season: Übergang und Formerhalt.

Nach dem Saisonziel hört das Training nicht auf, aber es ändert seinen Zweck.
Ohne eigene Regeln plant der Coach hier weiter wie im Aufbau — mit Watt- und
Pacevorgaben für eine Phase, in der genau das schadet: Wer nach der Saison
Zahlen hinterherläuft, erholt sich nicht und startet den nächsten Aufbau
müde.

Zwei Abschnitte:

* **Übergang** — die ersten zwei Wochen nach dem Wettkampf. Wenig, locker,
  gern etwas anderes. Der Körper hat einen Wettkampf hinter sich, und die
  Erholung davon ist die eigentliche Aufgabe.
* **Formerhalt** — danach, bis ein neues Ziel steht. Die Grundlage halten,
  statt sie zu verlieren: wenige, regelmäßige Einheiten in Z1/Z2, eine
  kurze harte Einheit als Erhalt der Spitze, mehr Kraft als in der Saison.

Warum Formerhalt überhaupt Struktur braucht: Die Ausdauerleistung fällt
messbar schon nach zwei bis drei Wochen ohne Reiz, während sie sich mit
zwei bis drei Einheiten je Disziplin fast vollständig halten lässt. Die
Alternative wäre, im Frühjahr wieder bei null anzufangen.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import User

logger = logging.getLogger(__name__)

# Wie lange nach dem Wettkampf der Übergang dauert.
UEBERGANG_WOCHEN = 2


def phase_label(race_date: date | None, today: date | None = None) -> str:
    """Bezeichnung der Off-Season-Phase für Anzeige und Plan."""
    today = today or date.today()
    if race_date is None:
        return "Formerhalt"
    tage = (today - race_date).days
    return "Übergang" if tage < UEBERGANG_WOCHEN * 7 else "Formerhalt"


def weeks_since(race_date: date | None, today: date | None = None) -> int | None:
    if race_date is None:
        return None
    today = today or date.today()
    return max(0, (today - race_date).days // 7)


def prompt_block(
    db: Session,
    race_date: date | None,
    user: User | None = None,
    today: date | None = None,
) -> str:
    """Vorgaben für eine Woche ohne Saisonziel.

    `db` und `user` werden noch nicht ausgewertet; sie stehen in der Signatur,
    damit später etwa der Umfang der letzten Saisonwochen einfließen kann,
    ohne die Aufrufer zu ändern.
    """
    today = today or date.today()
    phase = phase_label(race_date, today)
    seit = weeks_since(race_date, today)

    kopf = [
        f"OFF SEASON — {phase.upper()}."
        + (f" Der letzte Wettkampf liegt {seit} Woche{'n' if seit != 1 else ''} zurück."
           if seit is not None else " Es ist kein Wettkampf gesetzt."),
        "Es gibt aktuell kein Saisonziel. Plane keine Vorbereitung und keine "
        "Progression auf ein Datum hin.",
    ]

    if phase == "Übergang":
        regeln = [
            "Höchstens vier Einheiten in der Woche, alle locker. Zwei bis drei "
            "vollständig freie Tage sind ausdrücklich Teil des Plans.",
            "Keine Intervalle, keine Schwelle, kein Wettkampftempo, keine langen "
            "Einheiten. Nichts, was am nächsten Tag noch spürbar ist.",
            "Andere Bewegung ist willkommen und ausdrücklich zu nennen: Wandern, "
            "lockeres Radfahren im Gelände, Schwimmen als Technik, Spielsportarten.",
            "Ziel dieser Wochen ist Erholung vom Wettkampf, nicht Formaufbau.",
        ]
    else:
        regeln = [
            "Zwei bis drei Einheiten je Hauptdisziplin pro Woche, Umfang etwa "
            "60–70 % einer Saisonwoche. Regelmäßigkeit zählt mehr als Länge — "
            "die Ausdauer fällt schon nach zwei bis drei reizfreien Wochen messbar ab.",
            "Überwiegend Z1/Z2. Genau eine kurze harte Einheit pro Woche genügt, "
            "um die Spitze zu halten (etwa 6 × 1 Minute hart mit voller Pause). "
            "Sie ist optional — wer keine Lust hat, lässt sie weg.",
            "Krafttraining zweimal pro Woche, jetzt mit höherem Stellenwert als "
            "in der Saison — nur als Termin mit Dauer, ohne Übungen zu nennen.",
            "Schwimmen als Technikeinheit statt als Umfangseinheit.",
            "Keine langen Einheiten über zwei Stunden, kein Aufbau von Wochenumfang.",
        ]

    # Der wichtigste Teil: keine Zahlenvorgaben.
    vorgaben = [
        "KEINE WATT- UND PACEVORGABEN. Steuere ausschließlich über Herzfrequenzzone "
        "und Gefühl. Im `targets`-Objekt nur `hr_zone` setzen; `watts_low`, "
        "`watts_high`, `pace_low_s_per_km` und `pace_high_s_per_km` weglassen.",
        "Formuliere die Einheiten entsprechend — „locker, Unterhaltung möglich“ "
        "statt einer Zahl. Wer in der Off Season Zahlen hinterherläuft, erholt "
        "sich nicht und startet den nächsten Aufbau müde.",
        "Erwähne im coaching_comment, dass es um Erhalt geht und wann ein neues "
        "Ziel sinnvoll wäre.",
    ]

    zeilen = kopf + regeln + vorgaben
    aufzaehlung = "\n".join(f"- {z}" for z in zeilen)
    return (
        "## OFF SEASON (KRITISCH — ersetzt Phasenvorgabe und Zielwerte)\n\n"
        f"{aufzaehlung}\n\n---"
    )
