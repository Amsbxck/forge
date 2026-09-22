"""Fitness, Ermüdung und Form — und wann welcher Wert gilt.

Die Form (TSB) ist definiert als Fitness minus Ermüdung **vom Vortag**,
also vor dem Training des betrachteten Tages. Sie beantwortet "wie gehe
ich in diesen Tag hinein".

Gebildet wurde sie nach der Aktualisierung, also einschliesslich der
Einheit dieses Tages. Damit zog jedes Training die eigene Form herunter:
Nach einer harten Einheit stand dort ein tief negativer Wert, obwohl der
Athlet ausgeruht angetreten war — und der Coach hätte auf eine Ermüdung
reagiert, die erst durch dieses Training entstand.
"""

from datetime import date, timedelta

import pytest

from services.season_summary import K_ATL, K_CTL, _pmc


class _Einheit:
    def __init__(self, tag, tss):
        self.session_date, self.tss = tag, tss


START = date(2026, 9, 1)


def test_die_zeitkonstanten_stimmen():
    """7 Tage für die Ermüdung, 42 für die Fitness — die übliche Wahl."""
    import math
    assert K_ATL == pytest.approx(1 - math.exp(-1 / 7))
    assert K_CTL == pytest.approx(1 - math.exp(-1 / 42))
    assert K_ATL > K_CTL, "Ermüdung reagiert schneller als Fitness"


def test_form_stammt_vom_vortag():
    ruhig = [_Einheit(START + timedelta(days=i), 50) for i in range(14)]
    hart = _Einheit(START + timedelta(days=14), 250)
    verlauf = _pmc(ruhig + [hart], START + timedelta(days=15))

    je_tag = {z["datum"]: z for z in verlauf}
    vortag = je_tag[START + timedelta(days=13)]
    harter_tag = je_tag[START + timedelta(days=14)]

    # Die Form des harten Tages ist der Stand vom Vorabend.
    assert harter_tag["tsb"] == pytest.approx(vortag["ctl"] - vortag["atl"])
    # Und nicht der Stand nach der Einheit — der liegt deutlich tiefer.
    assert harter_tag["tsb"] > harter_tag["ctl"] - harter_tag["atl"]


def test_die_einheit_wirkt_sich_erst_am_folgetag_auf_die_form_aus():
    ruhig = [_Einheit(START + timedelta(days=i), 50) for i in range(14)]
    hart = _Einheit(START + timedelta(days=14), 250)
    je_tag = {z["datum"]: z for z in _pmc(ruhig + [hart], START + timedelta(days=15))}

    vorher = je_tag[START + timedelta(days=14)]["tsb"]
    danach = je_tag[START + timedelta(days=15)]["tsb"]
    assert danach < vorher - 15, "die harte Einheit schlägt am Folgetag durch"


def test_fitness_und_ermuedung_bleiben_tagesende_werte():
    """Nur die Form ist verschoben, CTL und ATL nicht."""
    einheiten = [_Einheit(START, 100)]
    erster = _pmc(einheiten, START)[0]

    assert erster["ctl"] == pytest.approx(100 * K_CTL)
    assert erster["atl"] == pytest.approx(100 * K_ATL)
    # Am allerersten Tag gibt es keinen Vortag — die Form startet bei null.
    assert erster["tsb"] == 0.0


def test_ohne_einheiten_kein_verlauf():
    assert _pmc([], START) == []
