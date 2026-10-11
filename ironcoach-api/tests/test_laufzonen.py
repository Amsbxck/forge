"""Die Laufbereiche müssen die Reize treffen, nach denen sie benannt sind.

„Z5 VO2max" lag bei 101–106 % der Schwellengeschwindigkeit und damit auf
5-Kilometer-Tempo. Bei einem Schwellenpace von 4:46/km hieß die Vorgabe
4:29–4:43/km, während echtes vVO2max bei 4:02–4:15/km liegt — eine als VO2max
geplante Einheit konnte den Reiz strukturell nicht erreichen. Für
Steigerungsläufe gab es überhaupt keinen Bereich.

Geprüft wird gegen die Prozentwerte aus `researched_training_structures/
running-training.md`, damit Code und Dokument nicht wieder auseinanderlaufen.
"""

import pytest

from services.session_quality import _zone_pace
from services.zones import LAUF_TEMPO_ZONEN, lauf_zonen

# Schwellenpace 4:46/km
SCHWELLE = 286


def test_tabelle_ist_lueckenlos():
    """Eine Lücke zwischen zwei Bändern verschiebt Werte stillschweigend.

    `_zone_pace` ordnet über eine Grenze je Zone zu. Läge zwischen Z3 und Z4
    eine Lücke, fiele ein Wert darin in die nächsthöhere Zone — genau der
    Fehler, der die Rad-Etiketten ein Band zu hart gemacht hat.
    """
    for (n1, _l1, schnell), (n2, langsam, _s2) in zip(
        LAUF_TEMPO_ZONEN, LAUF_TEMPO_ZONEN[1:]
    ):
        assert schnell == langsam, f"{n1} endet {schnell} %, {n2} beginnt {langsam} %"


def test_bereiche_folgen_dem_dokument():
    """Die Prozentwerte aus running-training.md, in Pace zurückgerechnet."""
    erwartet = {
        "Z1 Regeneration": (None, 70),
        "Z2 locker": (70, 81),
        "Z4 Schwelle": (95, 103),
        "Z6 vVO2max": (112, 120),
        "Z7 Steigerungen": (120, 130),
    }
    tatsaechlich = {name: (langsam, schnell) for name, langsam, schnell in LAUF_TEMPO_ZONEN}
    for name, grenzen in erwartet.items():
        assert tatsaechlich[name] == grenzen


def test_vvo2max_ist_schneller_als_5k_tempo():
    """Der Kern des Befunds: Z5 ist 5K, erst Z6 ist vVO2max."""
    nach_name = {z["name"]: z for z in lauf_zonen(SCHWELLE)}
    assert nach_name["Z5 5K / Tempo hart"]["text"] == "4:38–4:15/km"
    assert nach_name["Z6 vVO2max"]["text"] == "4:15–3:58/km"
    assert nach_name["Z7 Steigerungen"]["text"] == "3:58–3:40/km"


def test_schwelle_bleibt_schwelle():
    """Z1 bis Z4 behalten ihre Bedeutung, damit alte Notizen lesbar bleiben."""
    namen = [name for name, _l, _s in LAUF_TEMPO_ZONEN]
    assert namen[0].startswith("Z1")
    assert "Z4 Schwelle" in namen
    # Z4 muss die Schwellenpace selbst enthalten.
    assert _zone_pace(SCHWELLE, SCHWELLE) == "Z4"


@pytest.mark.parametrize("pace_s,erwartet", [
    (420, "Z1"),   # 7:00/km — deutlich langsamer als 70 %
    (380, "Z2"),   # 6:20/km — locker
    (330, "Z2"),   # 5:30/km — ruhig zügig, dieselbe Stufe
    (305, "Z3"),   # 5:05/km — Tempo
    (286, "Z4"),   # 4:46/km — Schwelle
    (265, "Z5"),   # 4:25/km — 5K-Tempo
    (245, "Z6"),   # 4:05/km — vVO2max
    (225, "Z7"),   # 3:45/km — Steigerung
])
def test_zuordnung_einer_pace(pace_s, erwartet):
    assert _zone_pace(pace_s, SCHWELLE) == erwartet


def test_steigerungslauf_ist_keine_spitzeneinheit():
    """Ein unbekanntes Zonenetikett ergab einen negativen Abstand.

    `ordnung.get(zone, 0)` lieferte für ein Z6 oder Z7 eine Null, und
    `0 − 2 = −2` erfüllte `abstand <= 1`: Ein Steigerungslauf gegen eine
    Z2-Vorgabe wäre als Spitzeneinheit gemeldet worden, also als Beleg für
    Reserve, obwohl er ein völlig anderes Training war.
    """
    from types import SimpleNamespace

    from services.session_quality import bewerte

    profil = SimpleNamespace(
        ftp_watts=264, threshold_pace_s_per_km=SCHWELLE, threshold_hr=188,
        z1_hr_max=130, z2_hr_max=155, z3_hr_max=172, z4_hr_max=188,
    )
    soll = SimpleNamespace(
        discipline="run", training_type="z2_endurance", duration_min=45,
        target_pace_low_s_per_km=330, target_pace_high_s_per_km=380,
        target_watts_low=None, target_watts_high=None, target_hr_zone="Z2",
    )
    ist = SimpleNamespace(
        discipline="run", session_date=None, duration_min=45,
        avg_pace_min_km=225 / 60, normalized_power=None, avg_watts=None,
        avg_hr=None, reflection=None,
    )
    urteil = bewerte(ist, soll, profil)
    assert urteil is not None
    assert urteil["urteil"] != "spitzeneinheit", urteil


def test_spitzeneinheit_ohne_pulsgegenprobe_wird_benannt():
    """Über der Schwelle gibt es keine Pulsobergrenze — das muss dastehen.

    Das Profil kennt Obergrenzen nur bis Z4; Z5 ist als "über dem
    Schwellenpuls" definiert, nach oben offen. `grenzen.get()` lieferte dort
    None, `puls_hinweis` blieb None, und im Urteil führte genau das in den
    letzten Zweig: Jede übertroffene Einheit über der Schwelle wurde zur
    Spitzeneinheit erklärt, ohne dass die Gegenprobe stattgefunden hätte —
    während die Legende dem Coach "Puls nicht erhöht" versicherte.

    Eine Pulsgrenze für vVO2max zu erfinden wäre falsch: bei kurzen
    Intervallen hinkt der Puls hinterher und zeigte in einem Vergleich sogar
    das Gegenteil des tatsächlichen Reizes. Also wird die Lücke benannt, nicht
    gefüllt.
    """
    from types import SimpleNamespace

    from services.session_quality import bewerte

    profil = SimpleNamespace(
        ftp_watts=264, threshold_pace_s_per_km=SCHWELLE, threshold_hr=188,
        z1_hr_max=130, z2_hr_max=155, z3_hr_max=172, z4_hr_max=188,
    )

    def lauf(zone, ziel_schnell, ziel_langsam, gelaufen_s):
        soll = SimpleNamespace(
            discipline="run", training_type="vo2max", duration_min=45,
            target_pace_low_s_per_km=ziel_schnell,
            target_pace_high_s_per_km=ziel_langsam,
            target_watts_low=None, target_watts_high=None, target_hr_zone=zone,
        )
        ist = SimpleNamespace(
            discipline="run", session_date=None, duration_min=45,
            avg_pace_min_km=gelaufen_s / 60, normalized_power=None,
            avg_watts=None, avg_hr=170, reflection=None,
        )
        return bewerte(ist, soll, profil)

    # Zielzone Z4: die Gegenprobe ist möglich.
    z4 = lauf("Z4", 278, 295, 255)
    assert z4["puls_pruefbar"] is True

    # Zielzone Z6: keine Obergrenze im Profil, also nicht prüfbar. Deutlich
    # über der Vorgabe (215 gegen 240 s/km am schnellen Bandrand, also gut
    # 10 % und damit über SCHWELLE_PACE), sonst lautet das Urteil nur
    # "im_rahmen" und die Frage nach der Gegenprobe stellt sich nicht.
    z6 = lauf("Z6", 240, 255, 215)
    assert z6["puls_pruefbar"] is False
    assert z6["urteil"] == "spitzeneinheit"


def test_fehlende_gegenprobe_steht_im_prompt():
    """Der Hinweis muss beim Coach ankommen, nicht nur im Datensatz stehen."""
    import inspect

    from services import session_quality

    quelle = inspect.getsource(session_quality.prompt_block)
    assert "puls_pruefbar" in quelle
    assert "nicht beurteilbar" in quelle
