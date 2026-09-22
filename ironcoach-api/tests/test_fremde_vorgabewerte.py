"""Vorgabewerte, die die Zahlen eines einzelnen Athleten waren.

Zwei Stellen trugen solche Werte als Standard: die Zonengrenzen
138/173/189/210 und eine FTP von 238 W. Beide sahen im Ergebnis plausibel
aus — und genau das macht sie gefährlich. Ein zweiter Athlet bekam seine
Zeit auf fremde Bereiche verteilt und seine Belastung gegen eine fremde
Schwelle gerechnet, ohne dass irgendwo ein Fehler auftauchte.
"""

import inspect

import pytest

from services.fit_parser import calculate_hr_zones, parse_fit_file, parse_gpx_file


def test_ohne_grenzen_wird_nicht_gerechnet():
    """Lieber kein Ergebnis als eines auf fremder Grundlage."""
    assert calculate_hr_zones([150, 160, 170]) is None


def test_mit_grenzen_wird_verteilt():
    zonen = calculate_hr_zones(
        [100, 150, 180, 195, 205],
        {"z1_max": 138, "z2_max": 173, "z3_max": 189, "z4_max": 200},
    )
    assert zonen is not None
    assert sum(zonen.values()) == pytest.approx(100, abs=0.5)


def test_die_grenzen_entscheiden_ueber_das_ergebnis():
    """Derselbe Puls fällt je nach Athlet in eine andere Zone."""
    puls = [175] * 10
    eng = calculate_hr_zones(puls, {"z1_max": 120, "z2_max": 150, "z3_max": 165, "z4_max": 180})
    weit = calculate_hr_zones(puls, {"z1_max": 138, "z2_max": 178, "z3_max": 190, "z4_max": 205})
    assert eng["z4"] == 100 and weit["z2"] == 100


def test_keine_fremde_ftp_als_vorgabe():
    ftp = inspect.signature(parse_fit_file).parameters["ftp"]
    assert ftp.default is None, "eine fremde Schwelle als Vorgabe ist eine Falle"


def test_gpx_nimmt_die_grenzen_des_athleten_entgegen():
    """Vorher war das der einzige Weg, auf dem fremde Zonen durchkamen."""
    assert "hr_zone_bounds" in inspect.signature(parse_gpx_file).parameters


def test_der_upload_gibt_sie_auch_weiter():
    import pathlib
    quelle = pathlib.Path(__file__).parent.parent / "routers" / "upload.py"
    text = quelle.read_text()
    assert "parse_gpx_file(file_path, hr_zone_bounds=zones_from_profile(profile))" in text
