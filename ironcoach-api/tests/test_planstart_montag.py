"""Ein Planstart liegt immer auf einem Montag.

Aus `plan_start_date` entstehen alle `week_start`-Daten
(`plan_start + (Woche − 1) × 7`), und die Wochenansicht sucht ihren Plan über
`week_start == Montag der Kalenderwoche`. Liegt der Start auf einem anderen
Wochentag, laufen alle Planwochen versetzt und die Ansicht findet für keine
einzige Woche einen Plan.

Genau das war bei Tamina der Fall: `plan_start_for` zog die Aufbaudauer vom
Renntag ab und übernahm dessen Wochentag. Ihr Rennen ist an einem Sonntag,
also lagen ihre Planwochen Sonntag bis Samstag. Die Ansicht fiel auf den
einzigen Plan zurück, der zufällig auf einem Montag begann — einen alten mit
der Wochennummer 1, wo −15 hätte stehen müssen.

Aufgefallen ist es erst spät, weil beim ersten Athleten der Renntag zufällig
ein Montag war. Der Fehler traf also alle ausser einem.
"""

from datetime import date, timedelta

import pytest

from core.race_types import plan_start_for
from core.wochen import kalenderwoche, montag_von
from services.plan_generator import get_week_for_date

MONTAG = 0


class Anker:
    def __init__(self, plan_start_date):
        self.plan_start_date = plan_start_date


# --- Der Helfer --------------------------------------------------------------

def test_montag_von_zieht_auf_den_wochenanfang():
    assert montag_von(date(2027, 1, 17)) == date(2027, 1, 11)   # Sonntag
    assert montag_von(date(2027, 1, 11)) == date(2027, 1, 11)   # schon Montag
    assert montag_von(date(2027, 1, 13)) == date(2027, 1, 11)   # Mittwoch


def test_montag_von_deckt_sich_mit_der_kalenderwoche():
    """Zwei Funktionen, die dasselbe meinen, müssen dasselbe sagen."""
    tag = date(2026, 9, 27)
    assert montag_von(tag) == kalenderwoche(tag)[0]


# --- Die Ableitung aus dem Renntag ------------------------------------------

@pytest.mark.parametrize("renntag", [
    date(2027, 8, 29),   # Sonntag — der Normalfall bei Wettkämpfen
    date(2027, 8, 28),   # Samstag
    date(2026, 8, 31),   # Montag — der Zufall, der den Fehler verdeckt hat
    date(2027, 6, 27),
    date(2027, 4, 25),
])
def test_abgeleiteter_planstart_ist_immer_montag(renntag):
    for wochen in (12, 14, 33, 40):
        start = plan_start_for(renntag, wochen)
        assert start.weekday() == MONTAG, f"{renntag} / {wochen} Wochen -> {start}"


def test_renntag_bleibt_in_der_letzten_woche():
    """Die Zusage der Funktion — sie darf durch die Montagsbindung nicht kippen.

    Bei einem Rennen am Sonntag fällt es sogar auf den letzten Tag der letzten
    Woche, was genau richtig ist.
    """
    renntag, wochen = date(2027, 8, 29), 33
    start = plan_start_for(renntag, wochen)
    letzte_woche_beginn = start + timedelta(weeks=wochen - 1)
    letzte_woche_ende = letzte_woche_beginn + timedelta(days=6)
    assert letzte_woche_beginn <= renntag <= letzte_woche_ende
    assert renntag == letzte_woche_ende


def test_ein_sonntagsstart_haette_die_wochen_verschoben():
    """Der alte Rechenweg, als Gegenprobe festgehalten."""
    renntag, wochen = date(2027, 8, 29), 33
    alt = renntag - timedelta(weeks=wochen - 1)
    assert alt.weekday() != MONTAG
    assert plan_start_for(renntag, wochen).weekday() == MONTAG


# --- Was daraus folgt --------------------------------------------------------

def test_wochenbeginn_trifft_die_kalenderwoche():
    """Der Kern: jede Planwoche muss auf einem Montag beginnen, sonst findet
    `/plan/current` sie nicht."""
    start = plan_start_for(date(2027, 8, 29), 33)
    for woche in range(-20, 34):
        beginn = start + timedelta(weeks=woche - 1)
        assert beginn == kalenderwoche(beginn)[0]


def test_taminas_wochennummer_stimmt_jetzt():
    """Von heute (27.09.2026) bis zu ihrem Aufbaubeginn sind es 15 Wochen."""
    start = plan_start_for(date(2027, 8, 29), 33)
    assert start == date(2027, 1, 11)
    assert get_week_for_date(Anker(start), date(2026, 9, 27)) == -15
    # Und die Woche, in der der Aufbau beginnt, ist Woche 1.
    assert get_week_for_date(Anker(start), start) == 1
    assert get_week_for_date(Anker(start), start + timedelta(days=6)) == 1
    assert get_week_for_date(Anker(start), start + timedelta(days=7)) == 2
