"""Die Formatbibliothek ersetzt die Zwift-Sammlung inhaltlich.

Die Zwift-Bibliothek lieferte im Prompt zwei Dinge: Struktur **und**
Prozentwerte. Sie aus dem Prompt zu nehmen, ohne die Prozente zu ersetzen,
hinterließ eine Lücke — „rotiere zwischen 30/15 und 4×8" sagt nicht, bei wie
viel Prozent. Die Werte hier kommen aus den Studientabellen in
`researched_training_structures/`.
"""

import re

from core.einheiten_bibliothek import LAUF_FORMATE, RAD_FORMATE
from core.phasenregeln import PHASENREGELN, prompt_block, regeln_fuer
from core.training_types import (
    TRAINING_TYPES,
    planbare_typen,
    planbare_typen_kurz,
    planbare_typen_tabelle,
)
from services.zones import LAUF_TEMPO_ZONEN, RAD_ZONEN


def test_jedes_format_nennt_ein_ziel():
    """Ein Format ohne Zielwert wäre genau die Lücke, die entstehen sollte."""
    for name, f in {**RAD_FORMATE, **LAUF_FORMATE}.items():
        assert f.get("ziel"), name
        assert f.get("struktur"), name
        assert f.get("beleg"), f"{name} ohne Beleg"
        # Jedes Ziel nennt eine Zahl — „zügig" ist keine Vorgabe. Renntempo
        # ist die begründete Ausnahme: es ergibt sich aus der Zielzeit und hat
        # keinen festen Prozentwert. Dann muss es das aber ausdrücklich sagen,
        # damit aus der Lücke kein Raten wird.
        hat_zahl = bool(re.search(r"\d", f["ziel"]))
        aus_zielzeit = "Zielzeit" in f["ziel"]
        assert hat_zahl or aus_zielzeit, name


def test_formate_nennen_nur_existierende_zonen():
    bekannt = {n.split()[0] for n, _l, _s in LAUF_TEMPO_ZONEN}
    bekannt |= {n.split()[0] for n, _u, _o in RAD_ZONEN}
    for name, f in {**RAD_FORMATE, **LAUF_FORMATE}.items():
        for zone in re.findall(r"\bZ\d\b", f["ziel"]):
            assert zone in bekannt, f"{name} nennt {zone}, das es nicht gibt"


def test_vo2max_intervalle_liegen_in_z5_nicht_z6():
    """Der Fehler, den ich selbst in den Prompt geschrieben hatte.

    „Eine VO2max-Einheit braucht Z6" war falsch: Die bestbelegte Einheit
    (4×4 min, +8,1 % VO2max bei Helgerud 2007) läuft bei 106–112 % der
    Schwellengeschwindigkeit und damit bei etwa **95 %** von vVO2max — das ist
    Z5. Z6 ist vVO2max selbst und nur für kurze Wiederholungen gedacht. Wer das
    verwechselt, verordnet durchweg zu schnelle Intervalle.
    """
    assert "(Z5)" in LAUF_FORMATE["4x4"]["ziel"]
    assert "95 %" in LAUF_FORMATE["4x4"]["ziel"]
    assert "Z6" in LAUF_FORMATE["15/15"]["ziel"]
    # Und die kurze Form trägt die Bedingung aus Billat 2001 mit.
    assert "klein" in LAUF_FORMATE["15/15"]["ziel"]


def test_z6_hat_ueberhaupt_ein_format():
    """Eine Zone, die nichts vorschreibt, wäre eine Zone zu viel."""
    ziele = " ".join(f["ziel"] for f in LAUF_FORMATE.values())
    assert "Z6" in ziele


def test_jede_phase_bringt_formate_mit():
    for familie, regeln in PHASENREGELN.items():
        assert regeln.get("rad") or regeln.get("lauf"), familie
        for schluessel in regeln.get("rad", ()):
            assert schluessel in RAD_FORMATE, f"{familie}: {schluessel}"
        for schluessel in regeln.get("lauf", ()):
            assert schluessel in LAUF_FORMATE, f"{familie}: {schluessel}"


def test_taper_bietet_keine_vo2max_formate():
    """Der Taper hält die Intensität, aber er baut keine Spitze mehr auf."""
    for familie in ("Taper", "Race Week"):
        for schluessel in PHASENREGELN[familie].get("rad", ()):
            assert schluessel not in ("30/15", "4-6x5", "4x8"), familie
        for schluessel in PHASENREGELN[familie].get("lauf", ()):
            assert schluessel not in ("4x4", "1000er", "15/15"), familie


def test_grundlage_hat_keine_vo2max_formate():
    """Höchstens eine Qualitätseinheit, und die nicht am Anschlag."""
    for schluessel in PHASENREGELN["Grundlage"].get("rad", ()):
        assert schluessel not in ("30/15", "4-6x5", "4x8")


def test_formattabelle_erscheint_im_block():
    text = prompt_block("Build 2")
    assert "Erlaubte Formate in dieser Phase" in text
    assert "% FTP" in text
    assert "30/15" in text


# --- Die Typentabelle stand an drei Stellen mit drei Inhalten ---------------

def test_typentabelle_kommt_aus_einer_quelle():
    tabelle = planbare_typen_tabelle()
    kurz = planbare_typen_kurz()
    for disziplin in ("bike", "run", "gym", "brick", "rest"):
        for typ in TRAINING_TYPES[disziplin]:
            assert typ in tabelle, f"{disziplin}/{typ} fehlt in der Tabelle"
            assert typ in kurz, f"{disziplin}/{typ} fehlt in der Kurzform"


def test_rad_tempo_erreicht_das_modell():
    """`classify_bike` vergibt `tempo` — der Coach muss es planen können.

    Sonst stünde über jeder Ausfahrt bei 80 % FTP dauerhaft „Typ: geplant
    sweet_spot, tatsächlich tempo".
    """
    assert "tempo" in planbare_typen("bike")
    assert "tempo" in planbare_typen_tabelle().split("| bike |")[1].split("|")[0]


def test_lauf_schwelle_und_vo2max_erreichen_das_modell():
    """Die Schemabeschreibung ließ beide beim Laufen weg."""
    for typ in ("threshold", "vo2max"):
        assert typ in planbare_typen("run")
        assert typ in planbare_typen_kurz()


def test_schwimmen_bleibt_absichtlich_enger():
    """Technik und Intervalle stehen im externen Plan, nicht beim Coach."""
    assert planbare_typen("swim") == ["endurance", "open_water"]
    assert "technique" not in planbare_typen_tabelle()


# --- Der Gym-Verweis zeigte ins Leere --------------------------------------

def test_gym_haeufigkeit_steht_auch_ohne_phasentabelle():
    """In Grundlage und Off Season gibt es keine Phasenvorgabe.

    Der Gym-Abschnitt sagte „siehe Phasenvorgabe oben" — in beiden Lagen ein
    Verweis auf einen Block, der dort nicht existiert.
    """
    from datetime import date

    from core.prompt_templates import build_plan_prompt

    profil = {
        "ftp_watts": 264, "threshold_hr": 188, "max_hr": 198, "weight_kg": 78,
        "age": 30, "z1_hr_max": 130, "z2_hr_min": 131, "z2_hr_max": 155,
        "z3_hr_min": 156, "z3_hr_max": 172, "z4_hr_min": 173, "z4_hr_max": 188,
        "name": "T", "total_weeks": 33, "threshold_pace_s_per_km": 286,
        "css_pace_s_per_100m": 117, "swim_threshold_hr": 153,
        "race_date": date(2026, 10, 18), "race_name": "T", "goal_label": "A",
    }
    for lage in ({"base_period": "## G\n"}, {"offseason": "## O\n"}):
        text = build_plan_prompt(
            athlete_profile=profil, sessions=[], hrv=[], week=-4,
            plan_start=date(2026, 3, 2), total_weeks=33, **lage,
        )
        assert "WOCHENVORGABE DIESER PHASE" not in text
        # Die Häufigkeit muss trotzdem dastehen.
        assert "zweimal** pro Woche" in text


def test_grundlage_und_offseason_ohne_phasentabelle():
    assert regeln_fuer("Off Season") is None


# --- Der Zähler muss die Qualitätseinheiten jeder Phase erkennen -----------

def test_wettkampftempo_zaehlt_als_qualitaetseinheit():
    """In der Peak-Phase SIND die Wettkampftempo-Blöcke die Qualitätseinheiten.

    Gezählt wurde zuerst über die Intensitätsstufe. Die ist zu grob:
    `sweet_spot`, `tempo` und `race_pace` fallen alle auf „sweet_spot". Damit
    meldete die Peak-Woche null Qualitätseinheiten gegen eine Vorgabe von
    zwei — und der Prompt verlangte zusätzliche Einheiten obendrauf, obwohl
    die Woche richtig war.
    """
    from types import SimpleNamespace

    from core.training_types import intensity_for_type
    from services.week_shape import _ist_hart

    def einheit(typ, disziplin="bike", zone=None):
        return SimpleNamespace(
            discipline=disziplin, training_type=typ, target_hr_zone=zone,
            intensity=intensity_for_type(disziplin, typ, zone),
        )

    assert _ist_hart(einheit("race_pace"))
    assert _ist_hart(einheit("threshold"))
    assert _ist_hart(einheit("vo2max"))
    # Sweet Spot und Tempo sind die Brot-und-Butter-Einheiten, keine Qualität.
    assert not _ist_hart(einheit("sweet_spot"))
    assert not _ist_hart(einheit("tempo"))
    assert not _ist_hart(einheit("long_ride"))
    # Ein Brick im Wettkampftempo zählt, ein lockerer nicht.
    assert _ist_hart(einheit("brick", "brick", "Z4"))
    assert not _ist_hart(einheit("brick", "brick", "Z2"))
    # Schwimmen wird extern geplant und nie eingestuft.
    assert not _ist_hart(einheit("intervals", "swim"))


def test_jede_phase_hat_zaehlbare_qualitaetseinheiten():
    """Jede Phasenvorgabe muss mit dem Zähler zusammenpassen.

    Sonst verlangt eine Phase zwei Qualitätseinheiten, deren Formate der
    Zähler nicht als solche erkennt.
    """
    from core.einheiten_bibliothek import LAUF_FORMATE, RAD_FORMATE
    from services.week_shape import QUALITAETS_TYPEN

    # Welche Formatschlüssel auf einen zählbaren Trainingstyp hinauslaufen.
    zaehlbar_rad = {"threshold_lang", "4x8", "4-6x5", "30/15",
                    "wettkampftempo_rad", "schaerfe"}
    zaehlbar_lauf = {"schwelle_intervalle", "1000er", "4x4", "15/15",
                     "wettkampftempo_lauf"}
    assert zaehlbar_rad <= set(RAD_FORMATE)
    assert zaehlbar_lauf <= set(LAUF_FORMATE)
    assert "race_pace" in QUALITAETS_TYPEN

    for familie, regeln in PHASENREGELN.items():
        von, _bis = regeln["qualitaet"]
        if von == 0:
            continue
        hat = (set(regeln.get("rad", ())) & zaehlbar_rad) or \
              (set(regeln.get("lauf", ())) & zaehlbar_lauf)
        assert hat, (
            f"{familie} verlangt {von} Qualitätseinheiten, bietet aber kein "
            f"Format, das der Zähler als solche erkennt"
        )
