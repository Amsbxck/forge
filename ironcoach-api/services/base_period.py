"""Die Zeit vor der spezifischen Vorbereitung.

Wer sich elf Monate vor einer Mitteldistanz anmeldet, hat rund sechs Monate
vor sich, für die der Aufbauplan noch nicht gilt. Das ist keine Lücke im
Training, sondern ein eigener Abschnitt: allgemeine Grundlage. Form lässt
sich nicht elf Monate lang aufbauen und halten — deshalb sind 24 Wochen die
Aufbaudauer und nicht die Wartezeit.

Bis hierher galt diese Zeit als „Woche 1 von 24". Der Wochenkalender zeigte
dann Datumsangaben aus dem nächsten Frühjahr als aktuelle Woche, und der
Athlet saß monatelang in derselben Woche fest.

Inhaltlich ist der Abschnitt dem Formerhalt der Off Season verwandt — Umfang
statt Intensität, keine Watt- und Pacevorgaben —, hat aber ein anderes
Vorzeichen: Hier wird auf etwas hingearbeitet, das noch kommt. Deshalb steht
der Countdown bis zum Aufbaubeginn im Prompt, und deshalb darf hier bereits
gezielt an Schwächen gearbeitet werden.
"""

from __future__ import annotations

from datetime import date

# Ab hier lohnt sich der Blick nach vorn: Wer nur noch wenige Wochen bis zum
# Aufbau hat, soll nicht mehr breit an Schwächen arbeiten, sondern die
# Grundlage stabilisieren, mit der er in Woche 1 startet.
UEBERGANG_WOCHEN = 6


def wochen_bis_aufbau(plan_start: date | None, heute: date | None = None) -> int | None:
    if plan_start is None:
        return None
    heute = heute or date.today()
    return max(0, (plan_start - heute).days // 7)


def phase_label(plan_start: date | None, heute: date | None = None) -> str:
    """Wie dieser Abschnitt heißt — abhängig davon, wie nah der Aufbau ist."""
    wochen = wochen_bis_aufbau(plan_start, heute)
    if wochen is None:
        return "Grundlage"
    return "Vorbereitung auf den Aufbau" if wochen <= UEBERGANG_WOCHEN else "Grundlage"


def prompt_block(
    plan_start: date | None,
    race_label: str | None = None,
    race_date: date | None = None,
    heute: date | None = None,
) -> str:
    """Der Abschnitt als Prompt-Baustein. Ersetzt die Phasenvorgabe."""
    if plan_start is None:
        return ""
    wochen = wochen_bis_aufbau(plan_start, heute)
    nah = wochen is not None and wochen <= UEBERGANG_WOCHEN

    ziel = race_label or "dein Saisonziel"
    kopf = (
        f"## GRUNDLAGENPHASE — der Aufbau beginnt erst am {plan_start}\n\n"
        f"Bis zum Start der spezifischen Vorbereitung auf {ziel}"
        + (f" am {race_date}" if race_date else "")
        + f" sind es noch **{wochen} Wochen**. "
    )

    if nah:
        kern = (
            "Der Aufbau steht kurz bevor. Ab jetzt geht es darum, mit einer "
            "belastbaren Grundlage in Woche 1 zu starten: Umfang halten, "
            "Trainingsrhythmus festigen, keine neuen Reize mehr ausprobieren. "
            "Wer hier noch etwas Grundlegendes umstellt, beginnt den Aufbau "
            "müde statt frisch."
        )
    else:
        kern = (
            "Das ist die Zeit für allgemeine Grundlage, nicht für "
            "Wettkampfvorbereitung. Nutze sie für das, wofür im Aufbau keine "
            "Zeit bleibt: Technik, Athletik, gleichmäßiger Umfang und die "
            "Schwäche, die den Athleten am meisten kostet."
        )

    return (
        kopf + kern + "\n\n"
        "### Regeln für diesen Abschnitt\n"
        "- **Keine Watt- und Pacevorgaben.** Gesteuert wird nach Gefühl und "
        "Puls. Zahlen aus einer Vorbereitung, die noch gar nicht läuft, "
        "erzeugen nur Druck ohne Zweck.\n"
        "- **Umfang vor Intensität.** Höchstens eine intensive Einheit pro "
        "Woche, und die aus Freude, nicht aus dem Plan.\n"
        "- **Keine Phasenlogik.** Es gibt hier kein Base 1, kein Build, keinen "
        "Deload-Rhythmus — die Woche steht für sich.\n"
        "- **Kein Wochenzähler.** Diese Wochen zählen nicht als Woche 1, 2, 3 "
        "der Vorbereitung. Die Zählung beginnt am Aufbaustart.\n"
        "- **Benenne den Zeitpunkt.** Schreibe in den coaching_comment, wie "
        f"viele Wochen es noch bis zum {plan_start} sind und worauf dieser "
        "Abschnitt hinarbeitet.\n\n---"
    )
