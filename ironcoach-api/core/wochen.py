"""Die Kalenderwoche als gemeinsame Grösse.

Eine Trainingswoche hat in dieser Anwendung zwei Namen: die Planwoche
("Woche 12 von 33") und die Kalenderwoche (Montag bis Sonntag). Die
Planwoche ist eine Beschriftung — sie wird über `max(1, …)` gebildet und
fällt vor dem Beginn des Aufbaus für jedes Datum auf 1 zusammen.

Zum Auswählen taugt sie deshalb nicht. Alles, was "diese Woche" meint,
rechnet mit dem Datumsbereich hier.
"""

from datetime import date, timedelta


def kalenderwoche(tag: date | None = None) -> tuple[date, date]:
    """Montag und Sonntag der Woche, in der `tag` liegt."""
    tag = tag or date.today()
    montag = tag - timedelta(days=tag.weekday())
    return montag, montag + timedelta(days=6)


def montag_von(tag: date | None = None) -> date:
    """Der Montag der Woche, in der `tag` liegt.

    Jeder Planstart muss auf einem Montag liegen. Die ganze Anwendung zählt
    Wochen von Montag bis Sonntag: die Wochenansicht sucht ihren Plan über
    `week_start == Montag der Kalenderwoche`, und `week_start` entsteht aus
    `plan_start_date + (Woche − 1) × 7`. Liegt der Planstart auf einem
    anderen Wochentag, laufen sämtliche Planwochen versetzt — und die Ansicht
    findet für keine einzige Woche einen Plan.

    Genau das ist passiert: `plan_start_for` zog die Aufbaudauer vom Renntag
    ab und übernahm damit dessen Wochentag. Rennen finden sonntags statt, also
    lagen die Planwochen praktisch aller Athleten auf Sonntag bis Samstag.
    Aufgefallen ist es nur deshalb spät, weil beim ersten Athleten der Renntag
    zufällig ein Montag war.
    """
    tag = tag or date.today()
    return tag - timedelta(days=tag.weekday())
