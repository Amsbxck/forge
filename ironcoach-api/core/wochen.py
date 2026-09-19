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
