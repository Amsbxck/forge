"""Die FTP wird eingetragen, nicht abgeleitet.

Begründung des Athleten: Die Benchmark-Woche kommt alle drei Monate, und ein
20-Minuten-Test auf dem Smart Trainer gibt die FTP am Ende selbst aus. Die
Ableitung aus den Runden ist bestenfalls eine Gegenprobe — automatisch
geschrieben hat sie einmal 175 W statt 264 eingetragen, und daran hingen jede
Wattvorgabe, die TSS und die Einstufung.

Der Weg dorthin war nicht die Bestätigungsansicht, sondern `maybe_autoderive`:
Die Funktion läuft nach **jedem** Import und rief `derive_zones(apply=True)`.
"""

import inspect

import services.benchmark as benchmark


def test_derive_zones_schreibt_keine_ftp():
    quelle = inspect.getsource(benchmark.derive_zones)
    assert "profile.ftp_watts =" not in quelle
    assert "ftp_source" not in quelle


def test_der_wert_kommt_als_vorschlag():
    """Nicht entfernt, nur entwaffnet: Als Gegenprobe zum Trainerwert ist er
    nützlich — er darf nur nichts schreiben."""
    quelle = inspect.getsource(benchmark.derive_zones)
    assert '"ftp_vorschlag"' in quelle


def test_der_schluessel_heisst_nicht_mehr_ftp_watts():
    """Damit keine Stelle ihn versehentlich übernimmt, auch keine künftige."""
    quelle = inspect.getsource(benchmark.derive_zones)
    zuweisungen = [z for z in quelle.split("\n") if 'result["ftp_watts"]' in z]
    assert zuweisungen == []


def test_automatik_gilt_nur_in_den_ersten_zwei_aufbauwochen():
    """Hier stand `> 2`. Mit der vorzeichenbehafteten Wochenzählung schloss das
    jede Vorlaufwoche ein — Woche -20 ist auch "nicht grösser als 2". Bei einem
    Athleten, dessen Aufbau erst in Monaten beginnt, lief die automatische
    Übernahme dadurch nach jedem Import.
    """
    quelle = inspect.getsource(benchmark.maybe_autoderive)
    assert "1 <= woche <= 2" in quelle
    assert "get_current_week(anchor) > 2" not in quelle


def test_die_pruefsteine_bleiben():
    """Sie schützen jetzt den Vorschlag statt den Profilwert: Eine unsinnige
    Zahl als Gegenprobe ist auch unsinnig."""
    from services.benchmark import MAX_FTP_ABFALL, MAX_TESTDAUER_MIN, MIN_HR_ANTEIL, _kein_test

    class Einheit:
        id = 1
        session_date = "2026-09-26"
        duration_min = 327

    class Profil:
        threshold_hr = 188
        ftp_watts = 264
        ftp_source = "manual"

    grund = _kein_test(
        {"avg_watts": 184, "start_s": 231 * 60, "avg_hr": 166, "anstieg": 1.1},
        Einheit(), Profil(),
    )
    assert grund is not None
    assert MAX_TESTDAUER_MIN and MIN_HR_ANTEIL and MAX_FTP_ABFALL
