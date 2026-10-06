"""Harte Minuten innerhalb einer Einheit — neben dem Etikett, nicht statt ihm.

Der Gesamt-IF kann einen harten Block in einer langen leichten Ausfahrt nicht
sehen. Gemessen an Amirs Historie ist das kein Randfall: 20 von 48 Radeinheiten
trugen ein weiches Etikett und enthielten dabei mindestens fünfzehn Minuten über
88 % FTP. Eine 534-Minuten-Ausfahrt stand als `long_ride` und hatte 88 Minuten
über 88 %, davon 47 über der Schwelle — an Anstiegen, die nun einmal
Schwellenarbeit sind. Eine 353-Minuten-Fahrt stand als `recovery` mit 19 Minuten
über der Schwelle.

Das Etikett bleibt. Eine neunstündige Ausfahrt als "threshold" zu führen wäre
genauso falsch wie "base" — sie war eine lange Ausfahrt **mit** harten
Abschnitten. Diese Zahlen sagen den zweiten Teil, damit der Coach nicht
Intensität obendrauf plant, die am Berg längst stattgefunden hat.
"""

import pytest

from services.segments import HARTE_SCHWELLEN, harte_minuten

FTP = 264


class Einheit:
    def __init__(self, watts, dauer=320, disziplin="bike"):
        self.discipline = disziplin
        self.duration_min = dauer
        self.streams = {"watts": watts} if watts is not None else {}


def _strom(leicht, sst, schwelle, vo2=0):
    """Leistungsstrom im 10-Sekunden-Takt, nach Bändern zusammengesetzt."""
    return [100] * leicht + [240] * sst + [260] * schwelle + [290] * vo2


def test_kumulativ_nicht_additiv():
    """Die Schwellenminuten stecken in den Sweetspot-Minuten.

    Sonst läse man sie als Summe und zählte die harte Arbeit doppelt.
    """
    # 36 Werte à 10 s = 6 min bei 240 W, 120 Werte = 20 min bei 260 W
    werte = harte_minuten(Einheit(_strom(1770, 36, 120)), FTP)
    assert werte["sst"] == 26, "6 min Sweetspot + 20 min Schwelle"
    assert werte["threshold"] == 20
    assert werte["sst"] > werte["threshold"]


def test_die_drei_schwellen_entsprechen_der_einstufung():
    """Zwei verschiedene Grenzen für dieselbe Sache wären eine Einladung zum
    Auseinanderdriften."""
    from services.classification import IF_SWEET_SPOT, IF_THRESHOLD

    grenzen = dict(HARTE_SCHWELLEN)
    assert grenzen["sst"] == IF_SWEET_SPOT
    assert grenzen["threshold"] == IF_THRESHOLD


def test_vo2max_wird_getrennt_ausgewiesen():
    werte = harte_minuten(Einheit(_strom(1700, 36, 100, 90)), FTP)
    assert werte["vo2max"] == 15
    assert werte["threshold"] >= werte["vo2max"]


def test_ohne_harte_minuten_kommt_nichts():
    """Drei Nullen in jeder Notiz wären Lärm, im Prompt kosten sie Token ohne
    Aussage."""
    assert harte_minuten(Einheit([100] * 1920), FTP) is None


def test_nur_rad_und_brick():
    """Beim Laufen fehlt eine gemeinsame Bezugsgrösse für Watt."""
    strom = _strom(1770, 36, 120)
    assert harte_minuten(Einheit(strom, disziplin="run"), FTP) is None
    assert harte_minuten(Einheit(strom, disziplin="brick"), FTP) is not None


def test_ohne_ftp_oder_strom_kommt_nichts():
    assert harte_minuten(Einheit(_strom(1770, 36, 120)), None) is None
    assert harte_minuten(Einheit(None), FTP) is None


# --- Wo es ankommt -----------------------------------------------------------

def test_der_prompt_nennt_sie():
    from core.prompt_templates import format_sessions

    text = format_sessions([{
        "session_date": "2026-10-03", "discipline": "bike", "duration_min": 320,
        "actual_type": "long_ride", "tss": 169.9,
        "harte_minuten": {"sst": 26, "threshold": 20},
    }])
    assert "26 min über 88 % FTP" in text
    assert "davon 20 min über der Schwelle" in text


def test_die_notiz_nennt_sie():
    from services.obsidian.notes import render_new_note

    text = render_new_note({
        "session_date": "2026-10-03", "discipline": "bike", "actual_type": "long_ride",
        "intensity": "base", "duration_min": 320, "tss": 169.9,
        "harte_minuten": {"sst": 26, "threshold": 20},
    }, None)
    assert "**Harte Arbeit:** 26 min über 88 % FTP, davon 20 min über der Schwelle" in text


def test_das_etikett_bleibt_unberuehrt():
    """Die Zahlen treten neben die Einstufung, nicht an ihre Stelle."""
    from services.classification import classify_bike, intensity_from_session

    class Lang:
        discipline = "bike"
        duration_min = 320
        normalized_power = 149
        avg_watts = 112
        hr_zones = {"z1": 90.0, "z2": 9.7, "z3": 0.2, "z4": 0.0, "z5": 0.0}
        actual_type = None
        streams = {"watts": _strom(1770, 36, 120)}

    assert classify_bike(Lang(), FTP) == "long_ride"
    assert intensity_from_session(Lang(), FTP) == "base"
    assert harte_minuten(Lang(), FTP) == {"sst": 26, "threshold": 20}
