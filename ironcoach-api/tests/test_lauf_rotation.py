"""Formatwechsel beim Laufen — aber nicht gleichwertig wie beim Rad.

Beim Rad ist kein Intervallformat nachweislich besser (Norte 2023), also wird
gleichwertig gewechselt. Fürs Laufen stand in der Rotation bisher nur ein
Satz („variiere Streckenlänge und Gelände"), und die Bahnformate in Metern
waren für sie unsichtbar: Der Erkenner verstand „4×8 min" und „30/15", aber
nicht „10×1000 m".

`running-training.md` trennt zwei Töpfe:

  * **Schwelle** — 5×6 min, 6×1600 m, 10×1000 m, 20–25×400 m, Tempolauf.
    Gleichwertige Wege zur selben Arbeit (Casado 2022/2023): frei wechseln.
  * **VO2max** — Wiederholungen ab drei Minuten sind der Standard
    (Fleckenstein 2025: 328 s gegen 201 s über 90 % VO2max). 15/15 und 30/30
    nur „as variety". Im Peak lange Wiederholungen und 10-20-30.
"""

from datetime import date, timedelta

import pytest

from services.intervall_format import (
    LAUF_SCHWELLE,
    LAUF_VO2_KURZ,
    LAUF_VO2_LANG,
    aus_text,
    lauf_kanon,
    lauf_rotation,
)

T = date(2026, 5, 4)


def _f(typ, kennung, tage=0):
    """Ein Eintrag wie aus `letzte_formate`."""
    return (T + timedelta(days=tage), "run", typ, kennung)


# ── Erkennung ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,kennung", [
    ("10×1000 m @ 95–102 %, 45 s Pause", "10x1000m"),
    ("6 x 1600m bei Schwelle", "6x1600m"),
    ("20×400 m, 30 s Trab", "20x400m"),
    ("4–5×1200 m, 3 min Trab", "5x1200m"),
    ("5×6 min @ 95–102 %", "5x6"),
    ("4×4 min, 3 min Trab", "4x4"),
    ("2 × 10 min aus 15/15", "15/15"),
    ("3–4 × 5 min 10-20-30, 2 min Pause", "10-20-30"),
])
def test_laufformate_werden_erkannt(text, kennung):
    """Vorher blieben die Meterformate unerkannt — und damit die halbe Bahn."""
    assert aus_text(text).kennung == kennung


def test_minutenserie_schlaegt_streckenmuster():
    """Eine Einheit hat ein Arbeitsformat. „5×6 min" ist keine Strecke."""
    assert aus_text("5×6 min, danach 2×400 m locker").kennung == "5x6"


def test_keine_gesamtstrecke_als_format():
    """„1×10000 m" wäre ein Lauf, kein Intervallformat."""
    assert aus_text("1×10000 m locker").kennung is None


@pytest.mark.parametrize("kennung,kanon", [
    ("10x1000m", "1000er"), ("5x1000m", "1000er"), ("4x1200m", "1200er"),
    ("20x400m", "400er"), ("5x6", "6-min"), ("4x4", "4-min"),
    ("15/15", "15/15"), ("Tempo", "Tempo"), ("10-20-30", "10-20-30"),
])
def test_kanonische_schluessel(kennung, kanon):
    """10×1000 m und 5×1000 m sind beide 1000er — der Topf entscheidet den Rest."""
    assert lauf_kanon(kennung) == kanon


# ── Schwelle: frei wechseln ─────────────────────────────────────────────────

def test_schwelle_schlaegt_ein_anderes_format_vor():
    zeilen = "\n".join(lauf_rotation([_f("threshold", "5x6")], "Build 1"))
    assert "anderes Format als 5×6 min" in zeilen
    # Die Vorschläge kommen aus dem Schwellentopf, ohne das letzte Format.
    vorschlag = zeilen.split("anderes Format als 5×6 min")[1]
    assert "5×6 min" not in vorschlag.split(".")[0]
    assert "Casado" in zeilen


def test_tempolauf_gehoert_in_den_schwellentopf():
    zeilen = "\n".join(lauf_rotation([_f("tempo", "Tempo")], "Build 1"))
    assert "Lauf, Schwelle" in zeilen
    assert "anderes Format als Tempolauf" in zeilen


# ── VO2max: lang ist Standard, kurz nur Abwechslung ────────────────────────

def test_vo2max_schlaegt_nur_lange_formate_vor():
    zeilen = "\n".join(lauf_rotation([_f("vo2max", "4x4")], "Build 1"))
    assert "anderes langes Format als 4×4 min" in zeilen
    assert "5–6×1000 m" in zeilen and "4–5×1200 m" in zeilen
    assert "Fleckenstein" in zeilen


def test_1000er_heisst_je_topf_anders():
    """Dieselbe Strecke, eine andere Einheit — der Fehler, der beim Schreiben
    fast drin geblieben wäre: VO2max-1000er als „10×1000 m" bezeichnet."""
    schwelle = "\n".join(lauf_rotation([_f("threshold", "10x1000m")], "Build 1"))
    vo2 = "\n".join(lauf_rotation([_f("vo2max", "5x1000m")], "Build 1"))
    assert "anderes Format als 10×1000 m" in schwelle
    assert "anderes langes Format als 5–6×1000 m" in vo2
    assert "10×1000 m" not in vo2


def test_kurzes_format_nicht_zweimal_hintereinander():
    """Nach einem 15/15 verlangt die Rotation wieder ein langes Format."""
    zeilen = "\n".join(lauf_rotation(
        [_f("vo2max", "4x4", 0), _f("vo2max", "15/15", 7)], "Build 1",
    ))
    assert "diesmal wieder ein langes" in zeilen
    assert "gelegentliche Abwechslung" not in zeilen


def test_nach_kurzem_kein_anderes_langes_als_kurz():
    """„ein anderes langes Format als 15/15" ergäbe keinen Sinn — 15/15 ist
    nicht lang. Dann heißt es einfach: zurück zu den langen."""
    zeilen = "\n".join(lauf_rotation([_f("vo2max", "15/15")], "Build 1"))
    assert "anderes langes Format als 15/15" not in zeilen
    assert "diesmal wieder ein langes Format" in zeilen
    # Alle drei langen stehen zur Wahl, keines ist ausgeschlossen.
    for lang in LAUF_VO2_LANG.values():
        assert lang in zeilen
    # Und der Hinweis steht nur einmal.
    assert zeilen.count("wieder ein langes") == 1


def test_vorletzte_kurz_heisst_noch_keine_neue_kurze():
    zeilen = "\n".join(lauf_rotation(
        [_f("vo2max", "15/15", 0), _f("vo2max", "4x4", 7)], "Build 1",
    ))
    assert "anderes langes Format als 4×4 min" in zeilen
    assert "noch keine neue kurze" in zeilen
    assert "gelegentliche Abwechslung" not in zeilen


def test_schwelle_laesst_die_letzten_zwei_aus():
    """Fünf gleichwertige Formate — nur das letzte auszuschließen hieße, dass
    zwei sich abwechseln und drei nie drankommen."""
    zeilen = "\n".join(lauf_rotation(
        [_f("threshold", "10x1000m", 0), _f("threshold", "5x6", 7)], "Build 1",
    ))
    vorschlag = zeilen.split("anderes Format als 5×6 min** — etwa ")[1].split(".")[0]
    assert "10×1000 m" not in vorschlag
    assert "5×6 min" not in vorschlag
    assert "6×1600 m" in vorschlag


def test_nach_zwei_langen_ist_abwechslung_erlaubt():
    zeilen = "\n".join(lauf_rotation(
        [_f("vo2max", "4x4", 0), _f("vo2max", "5x1000m", 7)], "Build 1",
    ))
    assert "gelegentliche Abwechslung" in zeilen
    assert "kleinem" in zeilen  # Billat 2001: kleiner Tempounterschied


def test_im_peak_keine_kurzen_formate():
    zeilen = "\n".join(lauf_rotation([_f("vo2max", "4x4")], "Peak"))
    assert "keine** kurzen Formate" in zeilen
    assert "10-20-30" in zeilen
    assert "gelegentliche Abwechslung" not in zeilen


def test_wettkampftempo_wird_nicht_rotiert():
    """Renntempo ist kein Formatwechsel — es ist die Zielvorgabe."""
    assert lauf_rotation([_f("race_pace", "3x3000m")], "Peak") == []


def test_rad_bleibt_unberuehrt():
    """Die Laufzeilen kommen nicht aus Radeinträgen."""
    assert lauf_rotation([(T, "bike", "vo2max", "4x8")], "Build 1") == []


# ── Phasen und Bibliothek ───────────────────────────────────────────────────

def test_neue_formate_stehen_in_der_bibliothek():
    from core.einheiten_bibliothek import LAUF_FORMATE

    for schluessel in ("1200er", "30/30", "10-20-30"):
        assert schluessel in LAUF_FORMATE, schluessel
        assert LAUF_FORMATE[schluessel]["beleg"], schluessel


def test_peak_behaelt_lange_vo2max_laeufe():
    """Laufdokument: „track reps ≥ 3 min; 10-20-30 as a time-efficient
    option". Vorher hatte der Peak gar kein VO2max-Laufformat."""
    from core.phasenregeln import PHASENREGELN

    peak = PHASENREGELN["Peak"]["lauf"]
    for lang in ("1000er", "1200er", "4x4", "10-20-30"):
        assert lang in peak, lang
    for kurz in ("15/15", "30/30"):
        assert kurz not in peak, kurz


def test_taper_bleibt_ohne_vo2max_laeufe():
    """Auch die neuen VO2max-Formate kommen nicht in Taper und Wettkampfwoche."""
    from core.phasenregeln import PHASENREGELN

    vo2 = set(LAUF_VO2_LANG) | set(LAUF_VO2_KURZ) | {"4x4", "10-20-30"}
    for familie in ("Taper", "Race Week"):
        assert not (set(PHASENREGELN[familie]["lauf"]) & vo2), familie


def test_keine_laufrotation_in_der_grundlage(db):
    """Wie beim Rad: In der Grundlage steht höchstens eine Qualitätseinheit,
    und die soll stabil sein."""
    from services.intervall_format import rotation_block

    assert rotation_block(db, T, "Grundlage") == ""


# ── Der ganze Weg: Vorgabe in der Datenbank → Prompt-Text ──────────────────

@pytest.fixture
def laufwochen(db):
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).first()
    angelegt = []

    def einheit(tag: date, typ: str, struktur: str):
        plan = WeeklyPlan(
            user_id=nutzer.id, week_number=80, week_start=tag,
            week_end=tag + timedelta(days=6), plan_phase="Build 1",
            plan_content={},
        )
        db.add(plan)
        db.commit()
        p = PlannedSession(
            user_id=nutzer.id, plan_id=plan.id, week_number=80,
            planned_date=tag, day_name="Tag", discipline="run",
            training_type=typ, duration_min=60, day_index=0,
            details={"struktur": struktur},
        )
        db.add(p)
        db.commit()
        angelegt.extend([p, plan])
        return nutzer.id

    yield einheit
    for o in angelegt:
        db.delete(o)
    db.commit()


def test_der_ganze_weg(laufwochen, db):
    from services.intervall_format import rotation_block

    montag = date(2026, 6, 1)
    uid = laufwochen(montag - timedelta(days=13), "threshold", "10×1000 m @ 95–102 %, 45 s Pause")
    laufwochen(montag - timedelta(days=10), "vo2max", "4×4 min @ 106–112 %, 3 min Trab")
    laufwochen(montag - timedelta(days=6), "threshold", "5×6 min @ 95–102 %, 60 s Pause")
    laufwochen(montag - timedelta(days=3), "vo2max", "2 × 10 min aus 15/15")

    text = rotation_block(db, montag, "Build 1", user_id=uid)
    assert "Lauf, Schwelle): 10×1000 m · 5×6 min" in text
    assert "Lauf, VO2max): 4×4 min · 15/15" in text
    assert "anderes Format als 5×6 min" in text
    assert "diesmal wieder ein langes" in text
