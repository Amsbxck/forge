"""Wann sind zwanzig Minuten ein FTP-Test — und wann nur die stärkste Stelle?

Der Fall, der das nötig gemacht hat: Die besten zwanzig Minuten einer
327-minütigen Grundlagenausfahrt ergaben 184 W, daraus eine FTP von 175 — bei
einer echten FTP von 264. Das Fenster begann nach 3 h 51 min, der Puls darin lag
bei 166 bpm gegen einen Schwellenpuls von 188. Die Rampenerkennung griff nicht,
weil eine gleichmässige Ausfahrt nun einmal gleichmässig ist (Anstieg 1,1).

Die Folge war nicht nur eine falsche Zahl: Jede Wattvorgabe lag ein Drittel zu
tief, die TSS wurde gegen die zu kleine Schwelle gerechnet — eine Fahrt kam auf
598 Punkte, also IF 1,05 über fünfeinhalb Stunden — und die Einstufung machte
aus 60 % FTP ein "threshold".

Überspringen ist sicher, ein falsch angenommener Test ist es nicht: Wer
übersprungen wird, trägt die Zahl selbst ein. Wer falsch übernommen wird, merkt
es wochenlang nicht.
"""

import pytest

from services.benchmark import (
    FTP_FACTOR,
    MAX_FTP_ABFALL,
    MAX_TESTDAUER_MIN,
    MAX_TESTSTART_MIN,
    MIN_HR_ANTEIL,
    _kein_test,
)


class Einheit:
    id = 1
    session_date = "2026-09-26"

    def __init__(self, duration_min):
        self.duration_min = duration_min


class Profil:
    def __init__(self, threshold_hr=188, ftp_watts=264, ftp_source="manual"):
        self.threshold_hr = threshold_hr
        self.ftp_watts = ftp_watts
        self.ftp_source = ftp_source


def fenster(watts=280, start_min=20, hr=185):
    return {"avg_watts": watts, "start_s": start_min * 60, "avg_hr": hr, "anstieg": 1.05}


# --- Der echte Fall ----------------------------------------------------------

def test_amirs_grundlagenausfahrt_wird_abgefangen():
    grund = _kein_test(fenster(184, 231, 166), Einheit(327), Profil())
    assert grund is not None
    assert grund["daten"]["grund"] == "Einheit zu lang"
    assert "327" in grund["hinweis"]


# --- Jede Prüfung einzeln ----------------------------------------------------

def test_zu_lange_einheit():
    assert _kein_test(fenster(), Einheit(MAX_TESTDAUER_MIN + 1), Profil()) is not None
    assert _kein_test(fenster(), Einheit(MAX_TESTDAUER_MIN), Profil()) is None


def test_fenster_liegt_zu_spaet():
    """Ein Test kommt nach dem Einfahren, nicht nach Stunden."""
    grund = _kein_test(fenster(start_min=MAX_TESTSTART_MIN + 5), Einheit(140), Profil())
    assert grund["daten"]["grund"] == "Fenster liegt zu spät"
    assert _kein_test(fenster(start_min=MAX_TESTSTART_MIN), Einheit(140), Profil()) is None


def test_puls_zu_niedrig():
    """Ein maximaler 20-Minuten-Test läuft nahe am Schwellenpuls."""
    knapp_drunter = int(188 * MIN_HR_ANTEIL) - 1
    grund = _kein_test(fenster(hr=knapp_drunter), Einheit(90), Profil())
    assert grund["daten"]["grund"] == "Puls zu niedrig für einen Test"
    assert grund["daten"]["fenster_hr"] == knapp_drunter
    assert _kein_test(fenster(hr=188), Einheit(90), Profil()) is None


def test_ohne_pulsdaten_entscheidet_der_puls_nicht_mit():
    """Kein Pulsgurt ist kein Grund, einen Test abzulehnen."""
    assert _kein_test(fenster(hr=None), Einheit(90), Profil()) is None


def test_ohne_schwellenpuls_entscheidet_der_puls_nicht_mit():
    assert _kein_test(fenster(hr=120), Einheit(90), Profil(threshold_hr=None)) is None


# --- Das letzte Netz ---------------------------------------------------------

def test_grosser_rueckgang_wird_nicht_uebernommen():
    """Formverlust geht langsam; ein Absturz heisst fast immer, dass die
    Grundlage der Rechnung nicht stimmte."""
    # Sauberes Fenster nach allen anderen Prüfungen, aber weit unter der
    # gespeicherten FTP.
    watts = int(264 * (1 - MAX_FTP_ABFALL - 0.1) / FTP_FACTOR)
    grund = _kein_test(fenster(watts=watts, hr=185), Einheit(90), Profil())
    assert grund["daten"]["grund"] == "Rückgang zu gross"
    assert grund["daten"]["alt"] == 264
    assert "bleiben stehen" in grund["hinweis"]


def test_kleiner_rueckgang_geht_durch():
    """Ein realistischer Rückgang muss ankommen — sonst friert die FTP ein."""
    watts = int(264 * 0.95 / FTP_FACTOR)
    assert _kein_test(fenster(watts=watts, hr=185), Einheit(90), Profil()) is None


def test_steigerung_geht_immer_durch():
    assert _kein_test(fenster(watts=320, hr=190), Einheit(90), Profil()) is None


def test_ohne_vorherigen_wert_kein_rueckgangsschutz():
    """Beim ersten Test gibt es nichts zu schützen."""
    assert _kein_test(fenster(watts=150, hr=185), Einheit(90),
                      Profil(ftp_watts=None, ftp_source=None)) is None


def test_vorbelegte_ftp_blockiert_nicht():
    """Nur gemessene Werte sind schützenswert. Die Voreinstellung ist geraten
    und darf von einem echten Test jederzeit ersetzt werden."""
    assert _kein_test(fenster(watts=150, hr=185), Einheit(90),
                      Profil(ftp_watts=264, ftp_source=None)) is None


# --- Ein sauberer Test bleibt ein Test ---------------------------------------

def test_sauberer_test_geht_durch():
    """Gegenprobe: 20 Minuten nach kurzem Einfahren, Puls an der Schwelle."""
    assert _kein_test(fenster(watts=278, start_min=18, hr=186), Einheit(75), Profil()) is None
