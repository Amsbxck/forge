"""Brick-Läufe sind Läufe — nicht das Schienbein-Protokoll für alle.

Die alten Brick-Regeln stammten aus einer Schienbein-Reha eines einzelnen
Athleten: Traben mit Gehpausen ("3×5 min jog + 2 min walk"), immer kürzer als
der eigenständige Lauf der Woche, keine Steigerungen, am Folgetag kein Lauf.
Sie galten danach unverändert für **jeden** Nutzer — auch für den, von dem sie
stammten, nachdem er geheilt war.

Nichts davon steht in den Studiendokumenten. `running-training.md` sagt:

  * Der Laufanteil **zählt als Lauf**: Einzellauf-Grenze und Wochenprogression
    gelten für ihn. Er soll sich also steigern wie jeder Lauf.
  * Beurteilt wird gegen die **Pace nach dem Rad** (6–9 % langsamer bei
    gleichem Empfinden), nicht gegen die Frischpace.
  * Geübt wird vor allem die **erste 5–10 min** nach dem Rad.
  * Das Rad davor mit **gleichmäßiger** Leistung.
  * Gestaffelt wird über die Intensität: Grundlage locker, Aufbau und Peak
    **Wettkampftempo**.

Gehpausen bleiben ein Werkzeug für Beschwerden — sie kommen über den
Gesundheitsabschnitt (`services/health.py`), nicht über die Brick-Tabelle.
"""

from datetime import date

import pytest

PROFIL = {
    "ftp_watts": 264, "threshold_hr": 188, "max_hr": 198, "weight_kg": 78,
    "age": 30, "z1_hr_max": 130, "z2_hr_min": 131, "z2_hr_max": 155,
    "z3_hr_min": 156, "z3_hr_max": 172, "z4_hr_min": 173, "z4_hr_max": 188,
    "name": "T", "total_weeks": 33, "threshold_pace_s_per_km": 286,
    "css_pace_s_per_100m": 117, "swim_threshold_hr": 153,
    "race_date": date(2026, 10, 18), "race_name": "T", "goal_label": "A",
}


@pytest.fixture(scope="module")
def brick_abschnitt():
    """Nur der Brick-Abschnitt — Treffer anderswo im Prompt zählen nicht."""
    from core.prompt_templates import build_plan_prompt

    text = build_plan_prompt(
        athlete_profile=PROFIL, sessions=[], hrv=[], week=12,
        plan_start=date(2026, 11, 9), total_weeks=33,
    )
    start = text.index("## BRICK-SESSIONS")
    ende = text.index("## RAD-LOGIK", start)
    return text[start:ende]


def test_kein_gehpausenformat_als_vorgabe(brick_abschnitt):
    """Die Progressionstabelle schreibt keine Gehpausen mehr vor."""
    for alt in ("jog + 2min walk", "jog + 90sec walk", "+ 2 min Gehen",
                "+ 90 s Gehen", "Trab +"):
        assert alt not in brick_abschnitt, alt


def test_keine_reha_regeln_fuer_alle(brick_abschnitt):
    """Die drei festen Regeln aus dem Schienbein-Protokoll sind weg."""
    assert "IMMER kürzer als Standalone-Lauf" not in brick_abschnitt
    assert "KEINE Strides in Brick-Läufen" not in brick_abschnitt
    assert "KEIN Standalone-Lauf" not in brick_abschnitt
    assert "NUR wenn 4 Wochen schmerzfrei" not in brick_abschnitt


def test_der_lauf_steigert_sich_wie_jeder_lauf(brick_abschnitt):
    """Die Einzellauf-Grenze gilt für den Brick-Lauf mit — sie begrenzt ihn,
    statt ihn auf „immer kürzer" festzunageln."""
    assert "Der Laufanteil ist ein Lauf" in brick_abschnitt
    assert "Einzellauf-Grenze" in brick_abschnitt
    assert "Wochenprogression" in brick_abschnitt


def test_gestaffelt_nach_intensitaet_bis_wettkampftempo(brick_abschnitt):
    """Grundlage locker, ab Aufbau Wettkampftempo — so die Studientabelle."""
    assert "durchgehend" in brick_abschnitt
    assert "Wettkampftempo" in brick_abschnitt
    assert "Mehrfachwechsel" in brick_abschnitt


def test_vo2max_nach_dem_rad_ist_nicht_vorgesehen(brick_abschnitt):
    """Die untersuchte Obergrenze ist das Wettkampftempo.

    Kein Dokument beschreibt einen VO2max-Lauf direkt nach dem Rad. Der Prompt
    soll das sagen, statt es offen zu lassen — sonst füllt das Modell die
    Lücke selbst.
    """
    assert "VO2max-Lauf direkt nach dem Rad" in brick_abschnitt
    assert "Keine Studie" in brick_abschnitt


def test_beurteilung_gegen_pace_nach_dem_rad(brick_abschnitt):
    assert "Pace nach dem Rad" in brick_abschnitt
    assert "6–9 %" in brick_abschnitt


def test_gehpausen_bleiben_fuer_beschwerden_moeglich(brick_abschnitt):
    """Kein Verbot — nur keine Grundeinstellung mehr."""
    assert "Gehpausen nur" in brick_abschnitt
    assert "Gesundheitsabschnitt" in brick_abschnitt


def test_schienbein_hinweis_bleibt_im_gesundheitsmodul():
    """Wer Schienbeinbeschwerden meldet, bekommt Gehpausen weiterhin — dort,
    wo sie hingehören: als Reaktion auf eine Meldung, nicht als Vorgabe."""
    from services.health import KOERPERSTELLEN

    assert "schienbein" in KOERPERSTELLEN
