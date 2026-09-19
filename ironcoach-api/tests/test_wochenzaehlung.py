"""Wochen vor dem Beginn der Vorbereitung bekommen negative Nummern.

Woche 1 ist die Woche, in der `plan_start_date` liegt. Davor wird
weitergezählt: 0 ist die Woche unmittelbar davor, -1 die davor, -7 die
achte davor.

Vorher stand dort `max(1, …)`. Die Absicht war nachvollziehbar — "Woche
minus sieben" klingt zunächst nach Unsinn. Der Preis war, dass *jedes*
Datum vor dem Beginn dieselbe Nummer trug: als Beschriftung falsch, als
Kennung unbrauchbar.
"""

from datetime import date, timedelta

import pytest

from core.race_types import phase_for_week
from services.plan_generator import get_week_for_date


class _Anker:
    def __init__(self, start):
        self.plan_start_date = start


START = date(2026, 11, 15)


@pytest.mark.parametrize("tag, erwartet", [
    (START, 1),                              # erster Tag der Vorbereitung
    (START + timedelta(days=6), 1),          # letzter Tag von Woche 1
    (START + timedelta(days=7), 2),
    (START - timedelta(days=1), 0),          # Woche unmittelbar davor
    (START - timedelta(days=7), 0),
    (START - timedelta(days=8), -1),
    (START - timedelta(days=55), -7),        # der Fall aus dem Bericht
])
def test_zaehlung_laeuft_ueber_den_start_hinaus_zurueck(tag, erwartet):
    assert get_week_for_date(_Anker(START), tag) == erwartet


def test_jede_woche_davor_hat_eine_eigene_nummer():
    """Der eigentliche Gewinn: keine Kollisionen mehr.

    Über `max(1, …)` trugen alle diese Wochen die 1 — daran scheiterten
    Wochenbreakdown, Testwoche und Blättern gleichermassen.
    """
    anker = _Anker(START)
    nummern = {
        get_week_for_date(anker, START - timedelta(weeks=n))
        for n in range(1, 12)
    }
    assert len(nummern) == 11


def test_ohne_startdatum_bleibt_es_bei_eins():
    class Ohne:
        plan_start_date = None
    assert get_week_for_date(Ohne(), date.today()) == 1


@pytest.mark.parametrize("woche", [-7, -1, 0])
def test_vor_dem_aufbau_gilt_grundlage(woche):
    """Ohne eigenen Zweig fiel eine negative Woche auf 'Base' durch."""
    assert phase_for_week(woche, 33) == "Grundlage"


def test_die_phasen_ab_woche_eins_bleiben_unveraendert():
    assert phase_for_week(1, 33) == "Base 1"
    assert phase_for_week(13, 33) == "Build 1"
    assert phase_for_week(25, 33) == "Peak 1"
    assert phase_for_week(31, 33) == "Taper"
    assert phase_for_week(33, 33) == "Race Week"
    assert phase_for_week(34, 33) == "Off Season"
