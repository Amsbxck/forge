"""Ordnerstruktur im Vault: eine Saison, ein Ordner.

Flach unter `Plans/` ist `Woche-12.md` nach der zweiten Saison doppelt belegt,
und `run/base/` sammelt Jahre ohne erkennbare Zuordnung. Diese Tests halten
fest, wie der Saisonordner bestimmt wird und wo er im Pfad steht.
"""

from datetime import date, timedelta

from core.saison import fenster, ordnername, saison_name
from services.obsidian.notes import note_path
from services.obsidian.plan_note import plan_note_path


class Ziel:
    """Ein A-Rennen, so viel wie `saison_name` davon braucht."""

    def __init__(self, race_date, plan_start_date=None, race_name=None, total_weeks=33):
        self.race_date = race_date
        self.plan_start_date = plan_start_date
        self.race_name = race_name
        self.total_weeks = total_weeks


ZELL = Ziel(date(2026, 8, 31), date(2026, 1, 12), "Ironman 70.3 Zell am See")


def test_tag_im_vorbereitungsfenster_gehoert_zur_saison():
    assert saison_name(date(2026, 5, 4), [ZELL]) == "Ironman 70.3 Zell am See 2026"


def test_planbeginn_und_wettkampftag_gehoeren_dazu():
    # Die Grenzen selbst zählen mit: sonst läge die erste Planwoche in der
    # Offseason und der Wettkampftag im Ordner des Folgejahres.
    assert saison_name(date(2026, 1, 12), [ZELL]).startswith("Ironman")
    assert saison_name(date(2026, 8, 31), [ZELL]).startswith("Ironman")


def test_tag_ausserhalb_landet_in_der_offseason():
    assert saison_name(date(2026, 10, 5), [ZELL]) == "Offseason 2026"
    assert saison_name(date(2025, 11, 3), [ZELL]) == "Offseason 2025"


def test_ohne_ziele_immer_offseason():
    assert saison_name(date(2026, 3, 1), []) == "Offseason 2026"


def test_vorbereitung_ueber_den_jahreswechsel_bleibt_ein_ordner():
    """Das Jahr kommt vom Wettkampf, nicht vom Tag.

    Ein Aufbau, der im Dezember beginnt, läge sonst halb in "… 2025" und halb
    in "… 2026" — also genau die Zersplitterung, die der Ordner verhindert.
    """
    ziel = Ziel(date(2026, 6, 27), date(2025, 12, 22), "Roth")
    assert saison_name(date(2025, 12, 29), [ziel]) == "Roth 2026"
    assert saison_name(date(2026, 4, 1), [ziel]) == "Roth 2026"


def test_fenster_ohne_planbeginn_wird_zurueckgerechnet():
    """Wer kein Startdatum setzt, soll nicht in der Offseason landen."""
    ziel = Ziel(date(2026, 6, 27), None, "Roth", total_weeks=40)
    beginn, ende = fenster(ziel)
    assert ende == date(2026, 6, 27)
    assert beginn == date(2026, 6, 27) - timedelta(weeks=40)
    assert saison_name(date(2026, 1, 15), [ziel]) == "Roth 2026"


def test_ziel_ohne_namen_faellt_auf_die_distanz_zurueck():
    class Namenlos(Ziel):
        label = "Mitteldistanz (70.3)"

    ziel = Namenlos(date(2026, 8, 31), date(2026, 1, 12))
    assert saison_name(date(2026, 5, 4), [ziel]) == "Mitteldistanz (70.3) 2026"


def test_ordnername_entfernt_zeichen_die_obsidian_kapert():
    # `#`, `[`, `]` und `^` leiten in Obsidian Tags, Links und Blockverweise
    # ein — im Pfad hätte "Ironman 70.3 #1" einen Anker erzeugt.
    assert ordnername("Ironman 70.3 #1") == "Ironman 70.3 1"
    assert ordnername("Nizza / Frankreich") == "Nizza Frankreich"
    assert ordnername("  ") == "Unbenannt"


def test_frueheres_ziel_gewinnt_bei_ueberschneidung():
    a = Ziel(date(2026, 6, 27), date(2025, 12, 22), "Roth")
    b = Ziel(date(2026, 8, 31), date(2026, 3, 1), "Zell")
    # Sortiert nach Wettkampfdatum, wie `saison_ziele` liefert.
    assert saison_name(date(2026, 4, 1), [a, b]) == "Roth 2026"


# --- Pfade -------------------------------------------------------------------

def test_einheit_liegt_unter_sportart_saison_intensitaet():
    pfad = note_path(
        "run", date(2026, 5, 4), 12345, "Training",
        intensity="base", saison="Ironman 70.3 Zell am See 2026",
    )
    assert pfad == "Training/run/Ironman 70.3 Zell am See 2026/base/2026-05-04--12345.md"


def test_ohne_saison_bleibt_der_flache_aufbau():
    """Aufrufer ohne Datenbank — und die Vorlage für den Umzug."""
    assert note_path("run", date(2026, 5, 4), 12345, "Training", intensity="base") == (
        "Training/run/base/2026-05-04--12345.md"
    )


def test_wanderung_bekommt_keinen_intensitaetsordner():
    pfad = note_path("hike", date(2026, 10, 5), None, "Training",
                     session_id=7, saison="Offseason 2026")
    assert pfad == "Training/fun/Offseason 2026/2026-10-05--s7.md"


def test_plan_liegt_im_saisonordner():
    class Plan:
        week_number = 12

    assert plan_note_path(Plan(), "Training", "Ironman 70.3 Zell am See 2026") == (
        "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-12.md"
    )


def test_grundlagenwoche_landet_im_offseason_ordner():
    class Plan:
        week_number = -7

    assert plan_note_path(Plan(), "Training", "Offseason 2026") == (
        "Training/Plans/Offseason 2026/Vorlauf-07.md"
    )
