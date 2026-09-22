"""Bemerken, wenn eine normale Fahrt die hinterlegte FTP in Frage stellt.

Die FTP wird nie automatisch geändert — ein einzelner harter Anstieg zöge
sie nach oben, und danach wäre jede Wattvorgabe der Folgemonate zu hart.
Gemeldet wird nur der Befund mit Datum und Zahlen.
"""

from datetime import date, timedelta

import pytest

from models import AthleteProfile, TrainingSession
from services.ftp_check import MELDESCHWELLE, ftp_ueberpruefung, prompt_block


@pytest.fixture(autouse=True)
def leer(db):
    db.query(TrainingSession).delete()
    db.commit()
    yield
    db.query(TrainingSession).delete()
    db.commit()


@pytest.fixture
def profil(db):
    p = db.query(AthleteProfile).first()
    vorher = p.ftp_watts
    p.ftp_watts = 240
    db.commit()
    yield p
    p.ftp_watts = vorher
    db.commit()


def _fahrt(db, watt, tage_her=5, dauer=45):
    p = db.query(AthleteProfile).first()
    s = TrainingSession(
        user_id=p.user_id, session_date=date.today() - timedelta(days=tage_her),
        week_number=1, discipline="bike", duration_min=dauer,
        streams={"watts": [watt] * dauer},
    )
    db.add(s); db.commit()
    return s


def test_deutlich_staerkere_fahrt_wird_gemeldet(db, profil):
    # 20 Minuten mit 280 W -> hergeleitet 266 W gegen hinterlegte 240 W.
    _fahrt(db, 280)
    befund = ftp_ueberpruefung(db, profil)

    assert befund is not None
    assert befund["hergeleitet_watt"] == 266
    assert befund["hinterlegt_watt"] == 240
    assert befund["differenz_watt"] == 26
    assert "280 W" in befund["text"]


def test_passende_fahrt_meldet_nichts(db, profil):
    """Tagesform ist kein Befund."""
    _fahrt(db, 250)     # hergeleitet 238, also unter der hinterlegten
    assert ftp_ueberpruefung(db, profil) is None


def test_knapp_darueber_bleibt_still(db, profil):
    """Unterhalb der Meldeschwelle wird geschwiegen.

    Ein Hinweis, der bei jedem Öffnen dasteht, wird nicht mehr gelesen.
    """
    grenze = profil.ftp_watts * MELDESCHWELLE
    _fahrt(db, round((grenze - 2) / 0.95))
    assert ftp_ueberpruefung(db, profil) is None


def test_stufentest_zaehlt_nicht_als_beleg(db, profil):
    """Sein bestes Fenster liegt systematisch zu niedrig."""
    p = db.query(AthleteProfile).first()
    watts = []
    for stufe in range(14):
        watts += [120 + stufe * 20] * 2
    db.add(TrainingSession(
        user_id=p.user_id, session_date=date.today() - timedelta(days=3),
        week_number=1, discipline="bike", duration_min=len(watts),
        streams={"watts": watts},
    ))
    db.commit()
    assert ftp_ueberpruefung(db, profil) is None


def test_alte_fahrten_zaehlen_nicht(db, profil):
    _fahrt(db, 300, tage_her=200)
    assert ftp_ueberpruefung(db, profil) is None


def test_kurze_fahrten_zaehlen_nicht(db, profil):
    """Unter 25 Minuten passt kein 20-Minuten-Fenster sinnvoll hinein."""
    _fahrt(db, 320, dauer=20)
    assert ftp_ueberpruefung(db, profil) is None


def test_der_coach_bekommt_den_befund_ohne_aufforderung_zu_aendern(db, profil):
    _fahrt(db, 280)
    text = prompt_block(db, profil)
    assert "266 W" in text
    assert "Ändere ihn nicht selbst" in text
    assert "Testwoche" in text


def test_ohne_befund_bleibt_der_block_leer(db, profil):
    _fahrt(db, 250)
    assert prompt_block(db, profil) == ""
