"""TSS wird an einer Stelle gerechnet, nicht an zwei.

Gemeldet als Frage: "war die TSS-Rechnung für die Radeinheit am 03.10 richtig?"
Sie war es nicht — 228,3 statt 169,9, also 34 % zu hoch. Der Grund war ein
halber Fix: `tss_neu` nahm Stravas NP, der Import rechnete sie weiter selbst aus
dem gespeicherten Strom. Der ist heruntergerechnet, bei 320 Minuten ein Wert je
zehn Sekunden — das 30-Werte-Fenster der NP-Formel umspannt damit fünf Minuten
statt dreissig Sekunden.
"""

import inspect

import pytest

from services.tss_calculator import tss_aus_np, tss_aus_puls


def test_die_ausfahrt_vom_dritten_oktober():
    """Stravas NP 149, FTP 264, 320 Minuten."""
    assert tss_aus_np(149, 264, 320) == 169.9


def test_eine_stunde_an_der_schwelle_sind_hundert():
    """Die Definition — wenn die nicht stimmt, stimmt nichts."""
    assert tss_aus_np(264, 264, 60) == 100.0
    assert tss_aus_puls(181, 181, 60) == 100.0


def test_ohne_np_kommt_keine_zahl():
    """Kein Rückfall auf irgendetwas. Der Wattdurchschnitt wäre falsch, und
    eine geratene Zahl sieht in der Formkurve aus wie eine gemessene."""
    assert tss_aus_np(None, 264, 320) is None
    assert tss_aus_np(149, None, 320) is None
    assert tss_aus_np(149, 264, 0) is None


def _ohne_kommentare(quelle: str) -> str:
    """Kommentare wegschneiden, bevor im Quelltext gesucht wird.

    Die alte Zeile steht dort absichtlich als Erklärung. Ein Test, der darüber
    stolpert, prüft den Text statt das Verhalten — und schlägt an, obwohl alles
    richtig ist.
    """
    zeilen = [z.split("#")[0] for z in quelle.split("\n") if not z.strip().startswith("#")]
    return "\n".join(zeilen)


def test_der_import_nutzt_stravas_np():
    """Der eigentliche Fehler: Dort wurde die NP aus dem Strom selbst gerechnet."""
    from services import strava_service

    code = _ohne_kommentare(
        inspect.getsource(strava_service.StravaService.map_strava_to_session)
    )
    assert "tss_aus_np(np_watts, ftp, duration_min)" in code
    assert "calculate_tss(" not in code


def test_neurechnung_und_import_rechnen_gleich():
    """Zwei Wege waren der Fehler. Beide müssen dieselbe Funktion rufen."""
    from services import strava_service, tss_neu

    for modul in (strava_service, tss_neu):
        quelle = inspect.getsource(modul)
        assert "tss_aus_np" in quelle, modul.__name__
        assert "tss_aus_puls" in quelle, modul.__name__


def test_einstufung_ohne_wattdurchschnitt_als_np_ersatz():
    """Taminas Ausfahrt über 315 Minuten kam auf 95 W Schnitt, also 50 % ihrer
    FTP, und galt damit als "recovery" — fünf Stunden Erholung."""
    from services.classification import classify_bike, intensity_from_session

    class OhneNP:
        discipline = "bike"
        duration_min = 315
        normalized_power = None
        avg_watts = 95
        hr_zones = {"z1": 72.2, "z2": 27.6, "z3": 0.2, "z4": 0.0, "z5": 0.0}
        actual_type = None

    assert classify_bike(OhneNP(), 191) == "long_ride"
    assert intensity_from_session(OhneNP(), 191) == "base"


def test_mit_np_entscheidet_weiter_die_leistung():
    from services.classification import classify_bike

    class MitNP:
        discipline = "bike"
        duration_min = 75
        normalized_power = 250
        avg_watts = 240
        hr_zones = {"z1": 5.0, "z2": 15.0, "z3": 20.0, "z4": 45.0, "z5": 15.0}
        actual_type = None

    assert classify_bike(MitNP(), 264) == "threshold"
