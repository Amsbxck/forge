"""Schwellenpuls und Schwellenpace müssen denselben Abschnitt meinen.

Die Pace kommt aus dem schnellsten 20-Minuten-Fenster der Testeinheit. Der
Puls kam dagegen aus `session.avg_hr` — dem Mittel über die ganze Einheit,
also einschliesslich Ein- und Auslaufen.

An echten Einheiten gemessen lagen dazwischen bis zu 22 Schläge. Der
Fehler bleibt anschliessend monatelang wirksam: Der Schwellenpuls ist der
Bezugswert jeder pulsbasierten TSS, und die Intensität geht quadratisch
ein — 16 Schläge zu wenig ergeben rund 19 Prozent zu viel Belastung.
"""

import pytest

from services.segments import best_effort_pace


class _Einheit:
    """Ein Test mit Ein- und Auslaufen, wie er tatsächlich aufgezeichnet wird."""

    def __init__(self, streams, duration_min):
        self.streams = streams
        self.duration_min = duration_min


def _testlauf():
    # 45 Minuten bei 60 s Abtastung: 15 ein, 20 hart, 10 aus.
    ein = [10.0] * 15 + [15.0] * 20 + [10.0] * 10          # km/h
    hf  = [130] * 15 + [180] * 20 + [120] * 10
    return _Einheit({"speed": ein, "hr": hf}, duration_min=45)


def test_puls_kommt_aus_dem_schnellsten_fenster():
    ergebnis = best_effort_pace(_testlauf(), seconds=1200)

    assert ergebnis["avg_hr"] == 180, "der Puls der harten 20 Minuten"
    # Das Mittel über die ganze Einheit läge deutlich darunter:
    alle = [130] * 15 + [180] * 20 + [120] * 10
    assert round(sum(alle) / len(alle)) == 150
    assert ergebnis["avg_hr"] - 150 == 30, "genau der Fehler, um den es geht"


def test_das_fenster_liegt_auf_dem_harten_teil():
    ergebnis = best_effort_pace(_testlauf(), seconds=1200)
    assert ergebnis["start_s"] == 15 * 60
    assert ergebnis["seconds"] == 1200
    # 15 km/h -> 4:00/km
    assert ergebnis["pace_s_per_km"] == 240


def test_ohne_pulsstream_bleibt_der_wert_leer():
    """Dann soll der Aufrufer wissen, dass er nichts Belastbares hat."""
    ohne = _Einheit({"speed": [12.0] * 45}, duration_min=45)
    ergebnis = best_effort_pace(ohne, seconds=1200)
    assert ergebnis is not None
    assert ergebnis["avg_hr"] is None


def test_luecken_im_stream_stoeren_nicht():
    """Aussetzer des Brustgurts kommen vor und sind als None gespeichert."""
    ein = [10.0] * 15 + [15.0] * 20 + [10.0] * 10
    hf = [130] * 15 + ([180, None] * 10) + [120] * 10
    ergebnis = best_effort_pace(_Einheit({"speed": ein, "hr": hf}, 45), seconds=1200)
    assert ergebnis["avg_hr"] == 180, "nur die vorhandenen Werte zählen"


def test_plateau_ignoriert_die_anlaufphase():
    """Der Puls braucht Minuten, bis er die Belastung abbildet.

    Ein Testlauf mit ansteigendem Puls in den ersten Minuten: Über das
    ganze Fenster gemittelt zieht der Anstieg den Wert nach unten, das
    Plateau der zweiten Hälfte bildet die tatsächliche Belastung ab.
    """
    ein = [10.0] * 5 + [15.0] * 20 + [10.0] * 5
    # Puls steigt über die ersten zehn Minuten des harten Teils von 160 auf 190.
    anstieg = [160, 166, 172, 178, 184, 190, 190, 190, 190, 190]
    hf = [120] * 5 + anstieg + [192] * 10 + [120] * 5
    ergebnis = best_effort_pace(_Einheit({"speed": ein, "hr": hf}, 30), seconds=1200)

    assert ergebnis["avg_hr"] == 186, "das Mittel über die ganzen 20 Minuten"
    assert ergebnis["avg_hr_plateau"] == 192, "die zweite Hälfte für sich"


def test_ohne_pulsstream_bleibt_auch_das_plateau_leer():
    ohne = _Einheit({"speed": [12.0] * 45}, duration_min=45)
    assert best_effort_pace(ohne, seconds=1200)["avg_hr_plateau"] is None


def test_die_korrektur_geht_nach_unten():
    """Die Richtung, nicht die Zahl.

    Ein 20-Minuten-Test wird oberhalb der Schwelle gelaufen — deshalb ist
    die FTP auch nur 95 % der 20-Minuten-Leistung. Der Puls dabei liegt
    entsprechend über dem Stundenwert: Man zieht ab, um auf die Schwelle
    zu kommen.
    """
    from services.benchmark import LTHR_FACTOR
    assert LTHR_FACTOR < 1.0

    from services.benchmark import FTP_FACTOR
    # Beim Puls fällt der Abschlag kleiner aus als bei der Leistung: Der
    # Puls flacht zur Maximalherzfrequenz hin ab, statt proportional
    # mitzusteigen.
    assert FTP_FACTOR < LTHR_FACTOR < 1.0
