"""Rad-Zonen, Phasenvorgabe und der Schutz historischer Notizen.

Es gab **zwei** Rad-Zonentabellen mit verschiedenen Grenzen, die beide im
selben Prompt landeten: `services/zones.py RAD_ZONEN` zog die Schwelle bei
91 % FTP, `services/classification.py` bei 96 %. Bei 92 % hieß dieselbe
Ausfahrt gleichzeitig „Z4 Schwelle" und `sweet_spot`.
"""

from types import SimpleNamespace

import pytest

from core.phasenregeln import MIN_ABSTAND_TAGE, PHASENREGELN, prompt_block, regeln_fuer
from services.classification import (
    IF_ENDURANCE,
    IF_RECOVERY,
    IF_SWEET_SPOT,
    IF_THRESHOLD,
    IF_VO2MAX,
    classify_bike,
)
from services.zones import RAD_SWEET_SPOT, RAD_ZONEN


def test_eine_grenze_nicht_zwei():
    """Zonentabelle und Einstufung müssen dieselben Zahlen benutzen."""
    nach_name = {name: (unten, oben) for name, unten, oben in RAD_ZONEN}
    assert nach_name["Z4 Schwelle"][0] == IF_THRESHOLD
    assert nach_name["Z5 VO2max"][0] == IF_VO2MAX
    assert nach_name["Z2 Grundlage"][0] == IF_RECOVERY
    assert nach_name["Z3 Tempo"][0] == IF_ENDURANCE
    # Sweet Spot ist das obere Ende von Z3, keine eigene Zone.
    assert RAD_SWEET_SPOT[0] == IF_SWEET_SPOT
    assert nach_name["Z3 Tempo"][1] == RAD_SWEET_SPOT[1]


def test_radzonen_sind_lueckenlos():
    """Die Zuordnung greift über die Obergrenze — eine Lücke verschiebt Werte."""
    for (n1, _u1, oben), (n2, unten, _o2) in zip(RAD_ZONEN, RAD_ZONEN[1:]):
        assert round(unten - oben, 2) == 0.01, f"{n1} endet {oben}, {n2} beginnt {unten}"


def _ausfahrt(np: int, dauer: int = 75):
    return SimpleNamespace(
        discipline="bike", duration_min=dauer, normalized_power=np,
        avg_watts=np - 10, hr_zones=None, actual_type=None,
    )


@pytest.mark.parametrize("anteil,erwartet", [
    (0.50, "recovery"),
    (0.70, "z2_endurance"),
    # 80–86 % hieß vorher `sweet_spot` — nach Coggan ist das Tempo.
    (0.80, "tempo"),
    (0.86, "tempo"),
    # 90–94 % hieß vorher `threshold` — das ist der Sweet Spot.
    (0.90, "sweet_spot"),
    (0.94, "sweet_spot"),
    # 98–102 % hieß vorher `vo2max` — die Schwelle reicht bis 105 %.
    (0.98, "threshold"),
    (1.02, "threshold"),
    # Erst ab 106 % ist es VO2max.
    (1.10, "vo2max"),
])
def test_coggan_baender(anteil, erwartet):
    ftp = 264
    assert classify_bike(_ausfahrt(round(ftp * anteil)), ftp) == erwartet


def test_tempo_ist_ein_gueltiger_radtyp():
    """Ohne das wäre das neue Etikett sofort wieder verworfen worden."""
    from core.training_types import is_valid_training_type

    assert is_valid_training_type("bike", "tempo")


def test_phasenvorgabe_gibt_es_fuer_jede_phase():
    """Vorher existierte genau eine Wochenvorlage, und zwar für „Build 2"."""
    from core.race_types import phase_family, phase_for_week

    for wochen in (12, 16, 33):
        for w in range(1, wochen + 1):
            phase = phase_for_week(w, wochen)
            if phase_family(phase) == "Off Season":
                continue
            assert regeln_fuer(phase), f"{wochen} Wochen, Woche {w}: {phase}"


def test_qualitaetseinheiten_folgen_den_dokumenten():
    assert PHASENREGELN["Base"]["qualitaet"] == (1, 1)
    assert PHASENREGELN["Build"]["qualitaet"] == (2, 2)
    assert PHASENREGELN["Peak"]["qualitaet"] == (2, 2)
    assert PHASENREGELN["Taper"]["qualitaet"] == (1, 2)
    assert MIN_ABSTAND_TAGE == 2  # 48 Stunden


def test_taper_behaelt_intensitaet():
    """Umfang runter, Intensität und Frequenz halten — vorher nicht ausdrückbar."""
    text = prompt_block("Taper")
    assert "Intensität und Frequenz halten" in text
    assert "kürzer, nicht gestrichen" in text


def test_build_verlangt_formatwechsel():
    text = prompt_block("Build 2")
    assert "wechseln" in text
    assert "30/15" in text and "4×8" in text
    # Beim Laufen gilt das Gegenteil: lange Wiederholungen sind besser.
    assert "drei Minuten" in text


def test_wettkampfwoche_ohne_schweres_gym():
    assert PHASENREGELN["Race Week"]["gym"] == 0
    assert "Kein schweres Krafttraining" in prompt_block("Race Week")


def test_grundlage_und_offseason_haben_eigene_bloecke():
    """Zwei Quellen für dieselbe Vorgabe wären der nächste Widerspruch."""
    assert regeln_fuer("Off Season") is None


def test_historische_notiz_wird_nicht_ueberschrieben(db):
    """Der Weg, auf dem sechs Notizen verloren gingen, ist jetzt zu."""
    from datetime import date

    from models import TrainingSession, User
    from services.classification import classify_session

    nutzer = db.query(User).first()
    einheit = TrainingSession(
        user_id=nutzer.id, session_date=date(2026, 5, 1), discipline="bike",
        duration_min=90, normalized_power=200, week_number=18,
        deviation_note="von Hand geschrieben, nicht ersetzen",
    )
    db.add(einheit)
    db.commit()
    db.refresh(einheit)
    try:
        ergebnis = classify_session(db, einheit, rewrite_notes=False)
        db.refresh(einheit)
        assert einheit.deviation_note == "von Hand geschrieben, nicht ersetzen"
        # Der Unterschied wird gemeldet, nicht verschwiegen.
        assert ergebnis.get("deviation_behalten")
        assert "deviation_vorschlag" in ergebnis

        # Mit ausdrücklicher Erlaubnis schreibt es.
        classify_session(db, einheit, rewrite_notes=True)
        db.refresh(einheit)
        assert einheit.deviation_note != "von Hand geschrieben, nicht ersetzen"
    finally:
        db.delete(einheit)
        db.commit()


def test_massenlauf_schreibt_notizen_standardmaessig_nicht():
    """`classify_all` ist die gefährliche Stelle — dort ist der Schutz an."""
    import inspect

    from services.classification import classify_all

    standard = inspect.signature(classify_all).parameters["rewrite_notes"].default
    assert standard is False
