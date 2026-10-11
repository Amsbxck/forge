"""Der Zwift-Katalog ist Nachschlagewerk, nicht Vorgabe.

Er stand als Pflichtbibliothek im Prompt („Verwende für jede Bike-Session EINE
dieser Strukturen als Basis") und belegte dort rund 27 % des Platzes. Die
studienbelegten Formatregeln hatten dagegen keine Chance. Dazu griff der
Notfilter innerhalb jeder Kategorie, sodass **jede** Woche ein VO2max-Menü
bekam — auch der Taper und die Grundlage.
"""

from datetime import date

from core.prompt_templates import build_plan_prompt
from core.race_types import is_deload, phase_family, phase_for_week
from services.intervall_format import Struktur, aus_text, aus_vorgabe, zwift_name


PROFIL = {
    "ftp_watts": 264, "threshold_hr": 188, "max_hr": 198, "weight_kg": 78,
    "age": 30, "z1_hr_max": 130, "z2_hr_min": 131, "z2_hr_max": 155,
    "z3_hr_min": 156, "z3_hr_max": 172, "z4_hr_min": 173, "z4_hr_max": 188,
    "name": "Test", "total_weeks": 33, "threshold_pace_s_per_km": 286,
    "css_pace_s_per_100m": 117, "swim_threshold_hr": 153,
    "race_date": date(2026, 10, 18), "race_name": "Test", "goal_label": "A",
}


def _prompt(week: int, total_weeks: int = 33) -> str:
    return build_plan_prompt(
        athlete_profile={**PROFIL, "total_weeks": total_weeks},
        sessions=[], hrv=[], week=week,
        plan_start=date(2026, 3, 2), total_weeks=total_weeks,
    )


def test_kein_workoutname_mehr_im_prompt():
    """Kein Katalogeintrag und keine Kategorieüberschrift im Prompt."""
    from core.zwift_catalog import ALL_CATALOGS

    # Nur unterscheidbare Namen prüfen: „Sweet Spot" und „Tempo" sind auch
    # Katalognamen, stehen im Prompt aber als Zonenvokabular — ein Treffer
    # darauf wäre eine Teilstring-Täuschung, kein Befund.
    namen = [
        w["name"] for c in ALL_CATALOGS.values() for w in c
        if any(z.isdigit() for z in w["name"]) or len(w["name"].split()) >= 3
    ]
    assert len(namen) > 30, "Prüfmenge zu klein, der Test würde nichts zeigen"
    text = _prompt(20)
    gefunden = [n for n in namen if n in text]
    assert not gefunden, f"Katalognamen noch im Prompt: {gefunden[:5]}"
    for eigenname in ("Pounding Sand", "Kirizuma", "Get It Done", "Halvfems"):
        assert eigenname not in text
    for ueberschrift in ("Zwift Workout Bibliothek", "VO2max & Anaerob",
                         "Verwende für jede Bike-Session"):
        assert ueberschrift not in text


def test_keine_persoenlichen_hrv_schwellen_im_prompt():
    """Die Millisekundenwerte eines einzelnen Athleten sind raus."""
    text = _prompt(20)
    for zahl in ("58-93ms", ">80ms", "70-80ms", "65-70ms", "<65ms"):
        assert zahl not in text, f"{zahl} steht noch im gemeinsamen Prompt"


def test_wettkampfwoche_ist_nie_deload():
    """`week % 4 == 0` erklärte die Rennwoche jedes 12/16/24/40-Wochen-Plans
    zur Entlastungswoche."""
    for wochen in (10, 12, 14, 16, 18, 24, 33, 40):
        assert not is_deload(wochen, wochen), f"{wochen}-Wochen-Plan"
        assert "DELOAD" not in _prompt(wochen, wochen)


def test_deload_stimmt_mit_der_saisontabelle():
    """Vorgabe und Übersicht im selben Prompt müssen dasselbe sagen."""
    for wochen in (12, 16, 33, 40):
        text = _prompt(1, wochen)
        aus_tabelle = {
            int(teil.split("|")[0].strip())
            for zeile in text.splitlines() if "Deload W" in zeile
            for teil in [zeile.split("Deload W", 1)[1]]
        }
        berechnet = {w for w in range(1, wochen + 1) if is_deload(w, wochen)}
        assert aus_tabelle == berechnet, f"{wochen} Wochen: {aus_tabelle} != {berechnet}"


def test_phasenfamilie_greift_auch_in_kurzen_plaenen():
    """Regeln wie „ab Build" müssen in jeder Planlänge greifen."""
    for wochen in (12, 14, 16, 33):
        familien = {phase_family(phase_for_week(w, wochen)) for w in range(1, wochen + 1)}
        assert {"Base", "Build", "Peak"} <= familien, f"{wochen} Wochen: {familien}"


def test_name_nur_bei_enger_uebereinstimmung():
    """Eine frei gebaute Struktur bekommt keinen Namen angehängt."""
    # 4×8min bei ~85 % FTP über 60 min ist der Katalogeintrag "Tempo".
    getroffen = zwift_name(
        Struktur(wdh=4, dauer_s=480, prozent_min=84, prozent_max=86),
        "sweet_spot", 60,
    )
    assert getroffen == "Tempo"

    # 7×6min gibt es im Katalog nicht.
    assert zwift_name(Struktur(wdh=7, dauer_s=360), "threshold", 70) is None
    # Gleiches Format, aber ganz andere Intensität: kein Treffer.
    assert zwift_name(
        Struktur(wdh=4, dauer_s=480, prozent_min=105, prozent_max=110),
        "sweet_spot", 60,
    ) is None
    # Dauer weit daneben: kein Treffer.
    assert zwift_name(Struktur(wdh=4, dauer_s=480), "sweet_spot", 120) is None


def test_pyramide_ist_kein_format():
    """2→4→6min ist keine „3×6" — ungleichförmige Serien ergeben nichts."""
    pyramide = {"blocks": [
        {"block": "1", "dauer": "2 min", "watt": "210 W"},
        {"block": "2", "dauer": "4 min", "watt": "210 W"},
        {"block": "3", "dauer": "6 min", "watt": "210 W"},
    ]}
    assert aus_vorgabe(pyramide, 264).kennung is None


def test_erholungsbloecke_zaehlen_nicht_als_intervall():
    """Eine 3×8-Einheit mit Pausen hat drei Arbeitsblöcke, nicht fünf."""
    vorgabe = {"blocks": [
        {"block": "1", "dauer": "8 min", "watt": "212-222 W"},
        {"block": "Erholung", "dauer": "2 min", "watt": "120-130 W"},
        {"block": "2", "dauer": "8 min", "watt": "212-222 W"},
        {"block": "Erholung", "dauer": "2 min", "watt": "120-130 W"},
        {"block": "3", "dauer": "8 min", "watt": "212-222 W"},
    ]}
    struktur = aus_vorgabe(vorgabe, 264)
    assert struktur.kennung == "3x8"
    assert struktur.prozent_min == 80 and struktur.prozent_max == 84


def test_wechselformat_auch_aus_dem_namen():
    """Bei einigen Einträgen steht das Format nur im Namen."""
    assert aus_text("40/20's #1").kennung == "40/20"
    assert aus_text("30/30 Anaerobic #1").kennung == "30/30"
    assert zwift_name(Struktur(wechsel=(40, 20)), "vo2max", 51) == "40/20's #1"
