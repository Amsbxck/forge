"""Die Blockoption im Aufbau — und warum sie kein gespeichertes Kennzeichen braucht.

Das Raddokument nennt die Menge im Aufbau über **vier Wochen**: 2 pro Woche und
5+1+1+1 ergeben beide acht harte Einheiten, aber nur der Block brachte
VO2max +4,6 % (Rønnestad 2014). Der Zähler zählte dagegen pro Woche und hätte
eine Blockwoche als Verstoß gemeldet — der Prompt hätte dem Coach gesagt,
zurückzunehmen, gegen etwas, das absichtlich so geplant war.

Das Vierwochenfenster löst beides auf einmal: Es lässt den Block zu **und**
erzwingt die Nachführung, weil nach fünf Einheiten nur noch drei übrig sind.
Kein Schalter, kein neues Feld, keine Migration.
"""

from datetime import date, timedelta

import pytest

from core.phasenregeln import (
    BLOCK_FENSTER_WOCHEN,
    PHASENREGELN,
    doppel_block,
    prompt_block,
)
from services.week_shape import bericht, harte_einheiten

MONTAG = date(2026, 4, 6)  # ein Montag


@pytest.fixture
def aufbauwochen(db):
    """Vier Wochen Vorgaben, je Woche ein eigener Plan."""
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).order_by(User.id.asc()).first()
    angelegt = []

    def woche(start: date, harte: int, nummer: int):
        plan = WeeklyPlan(
            user_id=nutzer.id, week_number=nummer, week_start=start,
            week_end=start + timedelta(days=6), plan_phase="Build 1",
            plan_content={},
        )
        db.add(plan)
        db.commit()
        angelegt.append(plan)
        for i in range(7):
            p = PlannedSession(
                user_id=nutzer.id, plan_id=plan.id, week_number=nummer,
                planned_date=start + timedelta(days=i), day_name="Tag",
                discipline="bike",
                training_type="vo2max" if i < harte else "z2_endurance",
                duration_min=60, day_index=i,
            )
            db.add(p)
            angelegt.append(p)
        db.commit()

    yield woche
    for o in reversed(angelegt):
        db.delete(o)
    db.commit()


def test_vierwochenfenster_nur_im_aufbau():
    """In Taper oder Wettkampfwoche wäre es sinnlos — es reichte über die Phase."""
    assert PHASENREGELN["Build"].get("block_moeglich") is True
    for familie in ("Grundlage", "Base", "Peak", "Taper", "Race Week"):
        assert not PHASENREGELN[familie].get("block_moeglich"), familie


def test_phasentext_nennt_block_nur_im_aufbau():
    text = prompt_block("Build 2")
    assert "Oder als Block" in text
    assert "5" in text and "normaler HRV" in text
    # Das Budget steht als Zahl da, nicht nur als Regel.
    assert str(2 * BLOCK_FENSTER_WOCHEN) in text
    for phase in ("Base 1", "Peak 1", "Taper", "Race Week"):
        assert "Oder als Block" not in prompt_block(phase)


def test_mehrere_wochen_werden_vollstaendig_gezaehlt(db, aufbauwochen):
    """Der Zähler filterte auf den einen jüngsten Plan über den Zeitraum.

    Bei einer Woche richtig, über vier Wochen hätte er drei Wochen
    weggeworfen — jede Woche hat ihren eigenen Plan.
    """
    for i, harte in enumerate((2, 2, 2, 2)):
        aufbauwochen(MONTAG + timedelta(weeks=i), harte, i + 1)

    einzeln = harte_einheiten(db, MONTAG, MONTAG + timedelta(days=6))
    assert einzeln["anzahl"] == 2

    fenster = harte_einheiten(db, MONTAG, MONTAG + timedelta(weeks=4) - timedelta(days=1))
    assert fenster["anzahl"] == 8, "vier Wochen à 2 müssen 8 ergeben"


def test_blockwoche_ist_kein_verstoss(db, aufbauwochen):
    """5+1+1+1 ist dieselbe Summe wie 2+2+2+2 und darf nicht gerügt werden."""
    for i, harte in enumerate((5, 1, 1, 1)):
        aufbauwochen(MONTAG + timedelta(weeks=i), harte, i + 1)

    # Die Blockwoche selbst: über der Wochenzahl, aber im Fenster.
    satz = bericht(db, MONTAG, "Build 1")
    assert satz is not None
    assert "Blockwoche" in satz
    assert "Phasenvorgabe" not in satz, "kein Vorwurf für eine gewollte Blockwoche"

    # Über alle vier Wochen: genau das Budget, also kein Überzug.
    fenster = harte_einheiten(db, MONTAG, MONTAG + timedelta(weeks=4) - timedelta(days=1))
    assert fenster["anzahl"] == 8


def test_echter_ueberzug_wird_gemeldet(db, aufbauwochen):
    """Vier Wochen mit je drei harten Einheiten sind 12 statt 8."""
    for i in range(4):
        aufbauwochen(MONTAG + timedelta(weeks=i), 3, i + 1)
    satz = bericht(db, MONTAG + timedelta(weeks=3), "Build 1")
    assert satz is not None
    assert "Budget" in satz


def test_nach_dem_block_wird_zum_duennhalten_geraten(db, aufbauwochen):
    """Die Nachführung erzwingt sich über das Fenster, ohne gespeicherten Schalter."""
    aufbauwochen(MONTAG, 5, 1)
    # Der Prompt für die Woche direkt nach dem Block.
    text = prompt_block_wochenform(db, MONTAG + timedelta(weeks=1))
    assert "Block" in text
    assert "dünn" in text


def prompt_block_wochenform(db, woche_ab):
    from services.week_shape import prompt_block as p
    return p(db, woche_ab, "Build 1")


# --- Doppeltage: im Code gab es sie überhaupt nicht ------------------------

def test_doppelschwelle_nur_in_aufbau_und_peak():
    """Das Laufdokument sagt ausdrücklich „Aufbau/Peak only, HRV normal"."""
    from core.phasenregeln import PHASENREGELN

    for familie in ("Build", "Peak"):
        assert "doppelschwelle_leicht" in PHASENREGELN[familie]["doppel"], familie
    for familie in ("Grundlage", "Base", "Taper", "Race Week"):
        assert "doppelschwelle_leicht" not in PHASENREGELN[familie]["doppel"], familie


def test_keine_doppeltage_im_taper_und_in_der_rennwoche():
    from core.phasenregeln import PHASENREGELN

    assert PHASENREGELN["Taper"]["doppel"] == ()
    assert PHASENREGELN["Race Week"]["doppel"] == ()
    # Die Doppeltage stehen in einem eigenen Abschnitt, damit sie auch die
    # Grundlagenphase erreichen, in der die Phasenvorgabe unterdrückt wird.
    assert "In dieser Phase keine" in doppel_block("Taper")
    assert "In dieser Phase keine" in doppel_block("Race Week")


def test_jede_phase_nennt_nur_bekannte_doppelformen():
    from core.einheiten_bibliothek import DOPPEL_FORMATE
    from core.phasenregeln import PHASENREGELN

    for familie, regeln in PHASENREGELN.items():
        for schluessel in regeln["doppel"]:
            assert schluessel in DOPPEL_FORMATE, f"{familie}: {schluessel}"


def test_doppeltag_zaehlt_als_eine_qualitaetseinheit():
    """Sonst wäre ein geteilter Schwellentag doppelt im Budget."""
    text = doppel_block("Build 2")
    assert "als **eine** Qualitätseinheit" in text
    assert "6 h Abstand" in text or "6 Stunden" in text
    # Und der Hinweis, wann ein Doppeltag überhaupt das Mittel ist.
    assert "nicht auf einzelne Tage passen" in text


def test_jede_doppelform_nennt_ihren_beleg():
    from core.einheiten_bibliothek import DOPPEL_FORMATE

    for name, f in DOPPEL_FORMATE.items():
        assert f.get("beleg"), name
        assert f.get("struktur"), name
        assert f.get("ziel"), name


def test_glossar_deckt_sich_mit_den_regeln():
    """Das Glossar für den Athleten darf nichts versprechen, was der Code nicht tut."""
    import pathlib

    from core.phasenregeln import PHASENREGELN

    pfad = pathlib.Path(__file__).resolve().parent.parent.parent / "TRAININGSOPTIONEN.md"
    assert pfad.exists(), "Glossar fehlt"
    text = pfad.read_text(encoding="utf-8")

    # Die Blockwoche ist laut Glossar nur im Aufbau — so muss es im Code sein.
    assert "nur Aufbau" in text
    assert PHASENREGELN["Build"].get("block_moeglich")
    assert not PHASENREGELN["Peak"].get("block_moeglich")

    # Die Doppelschwelle laut Glossar nur Aufbau und Peak.
    assert "nur Aufbau und Peak" in text

    # Der Mindestabstand im Glossar muss der Konstante entsprechen.
    from core.einheiten_bibliothek import DOPPEL_MIN_ABSTAND_H
    assert f"**{DOPPEL_MIN_ABSTAND_H} Stunden**" in text


# --- Was als Qualitätseinheit zählt, hängt an der Phase -------------------

def test_sweet_spot_zaehlt_in_der_grundlage_aber_nicht_im_aufbau():
    """An einem echten Plan aufgefallen, nicht beim Lesen des Codes.

    Eine Grundlagenwoche mit genau einer Sweet-Spot-Einheit auf dem Rad wurde
    als "0 Qualitätseinheiten" gezählt — und der Prompt hätte der Folgewoche
    geraten, die fehlende Qualität nachzuholen. Eine zusätzliche harte Einheit
    auf eine Woche, die richtig war.

    In der Grundlage **ist** der Sweet Spot die eine Qualitätseinheit (das
    Dokument nennt dort "sweet spot / threshold long, or a light 30/15"); im
    Aufbau ist er die Brot-und-Butter-Einheit und zählt nicht.
    """
    from types import SimpleNamespace

    from core.phasenregeln import (
        PHASENREGELN,
        QUALITAET_MIT_SWEET_SPOT,
        QUALITAET_STRENG,
    )
    from services.week_shape import _ist_hart

    rad = SimpleNamespace(
        discipline="bike", training_type="sweet_spot",
        target_hr_zone="Z3", intensity="sweet_spot",
    )
    assert _ist_hart(rad, QUALITAET_MIT_SWEET_SPOT) is True
    assert _ist_hart(rad, QUALITAET_STRENG) is False

    for familie in ("Grundlage", "Base"):
        assert "sweet_spot" in PHASENREGELN[familie]["zaehlt_als_qualitaet"], familie
    for familie in ("Build", "Peak", "Taper", "Race Week"):
        assert "sweet_spot" not in PHASENREGELN[familie]["zaehlt_als_qualitaet"], familie


def test_ohne_phase_gilt_die_strenge_liste():
    """Ein fehlender Wert darf nicht die laxere Variante aktivieren."""
    from types import SimpleNamespace

    from services.week_shape import QUALITAETS_TYPEN, _ist_hart
    from core.phasenregeln import QUALITAET_STRENG

    assert QUALITAETS_TYPEN == QUALITAET_STRENG
    rad = SimpleNamespace(
        discipline="bike", training_type="sweet_spot",
        target_hr_zone="Z3", intensity="sweet_spot",
    )
    assert _ist_hart(rad) is False


def test_jede_phase_zaehlt_ihre_eigenen_formate_mit(db):
    """Die erlaubten Formate einer Phase müssen auch zählbar sein.

    Sonst verlangt eine Phase Qualitätseinheiten, deren eigene Formate der
    Zähler nicht als solche erkennt — genau der Fehler oben.
    """
    from core.phasenregeln import PHASENREGELN

    # Formatschlüssel → Trainingstyp, so wie der Coach sie plant.
    typ_je_format = {
        "sweet_spot": "sweet_spot", "threshold_lang": "threshold",
        "4x8": "vo2max", "4-6x5": "vo2max", "30/15": "vo2max",
        "wettkampftempo_rad": "race_pace", "schaerfe": "race_pace",
        "tempo": "tempo", "schwelle_intervalle": "threshold",
        "1000er": "vo2max", "4x4": "vo2max", "15/15": "vo2max",
        "wettkampftempo_lauf": "race_pace",
        "steigerungen": None, "langer_lauf": None,
    }
    for familie, regeln in PHASENREGELN.items():
        von, _bis = regeln["qualitaet"]
        if von == 0:
            continue
        zaehlbar = regeln["zaehlt_als_qualitaet"]
        formate = tuple(regeln.get("rad", ())) + tuple(regeln.get("lauf", ()))
        treffer = [
            f for f in formate
            if typ_je_format.get(f) and typ_je_format[f] in zaehlbar
        ]
        assert treffer, (
            f"{familie} verlangt {von} Qualitätseinheiten, aber keines seiner "
            f"Formate {formate} zählt als eine"
        )


def test_doppeltage_erreichen_auch_die_grundlagenphase():
    """Der Fehler, den ein echter Plan gezeigt hat.

    In der Grundlagenphase wird die Phasenvorgabe unterdrückt (dort gilt
    `services/base_period.py`), und die Doppeltage steckten darin. `base_period`
    erwähnt sie mit keinem Wort — der Coach wusste also nichts davon. Die Woche
    hatte alle sieben Tage belegt, für die zweite Krafteinheit war kein Tag
    frei, und sie fiel ersatzlos aus. Mit einem Doppeltag (Schwimmen + Kraft,
    ausdrücklich erlaubt) hätte sie gepasst.
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
    text = build_plan_prompt(
        athlete_profile=profil, sessions=[], hrv=[], week=-4,
        plan_start=date(2026, 11, 9), total_weeks=33,
        base_period="## GRUNDLAGENPHASE\n- Regel\n",
    )
    # Die Phasenvorgabe bleibt unterdrückt ...
    assert "WOCHENVORGABE DIESER PHASE" not in text
    # ... die Doppeltage stehen aber da.
    assert "## DOPPELTAGE" in text
    assert "schwimmen_als_zweite" in text
    assert "nicht auf einzelne Tage passen" in text
