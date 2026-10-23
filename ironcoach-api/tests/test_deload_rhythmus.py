"""Entlastung im 3:1-Takt.

Das Raddokument nennt „2–3 load weeks + 1 recovery week". Bisher gab es nur
am Ende jeder Phase eine Entlastung — bei 33 Wochen W12 und W24, mit elf
Belastungswochen dazwischen.
"""

import pytest

from core.race_types import RACE_TYPES, deload_wochen, is_deload, phase_boundaries

PLAENE = sorted({c["weeks"] for d in RACE_TYPES.values() for c in d.values()} | {33})


@pytest.mark.parametrize("wochen", PLAENE)
def test_hoechstens_drei_belastungswochen_am_stueck(wochen):
    taper = next(s for n, s, _e in phase_boundaries(wochen) if n == "Taper")
    entlastung = sorted(deload_wochen(wochen))
    vorher = 0
    for w in entlastung:
        assert w - vorher - 1 <= 3, f"{wochen} Wochen: {w - vorher - 1} Belastungswochen vor W{w}"
        vorher = w
    # Danach bis zum Taper: höchstens vier (die Woche vor dem Taper bleibt
    # bewusst ohne Entlastung).
    assert taper - vorher - 1 <= 4, f"{wochen} Wochen: Strecke vor dem Taper"


@pytest.mark.parametrize("wochen", PLAENE)
def test_keine_entlastung_im_taper_rennwoche_und_davor(wochen):
    taper = next(s for n, s, _e in phase_boundaries(wochen) if n == "Taper")
    for w in range(taper - 1, wochen + 1):
        assert not is_deload(w, wochen), f"{wochen} Wochen: W{w}"


def test_mitteldistanz_alle_vier_wochen():
    assert sorted(deload_wochen(33)) == [4, 8, 12, 16, 20, 24, 28]


# --- Phasen und Blöcke im Takt -------------------------------------------------
#
# Vorher folgten die Phasengrenzen nur den Anteilen, und die Blöcke waren
# gedrittelte Phasen. Bei 20 Wochen begann Build in W8 mit einem Deload, und
# der Strahl zeigte Blöcke von 2, 2, 3, 2, 2, 3 Wochen. Amir: „3 Wochen
# Belastung, 1 Woche Deload" — also enden Phasen und Blöcke mit dem Deload.

from core.race_types import phase_for_week  # noqa: E402


def _bloecke(wochen):
    """[(Name, von, bis)] Woche für Woche aus `phase_for_week`."""
    out = []
    for w in range(1, wochen + 1):
        name = phase_for_week(w, wochen)
        if out and out[-1][0] == name:
            out[-1][2] = w
        else:
            out.append([name, w, w])
    return out


@pytest.mark.parametrize("wochen", range(4, 53))
def test_taper_und_deload_bleiben_wie_vorher(wochen):
    """Der Umbau verschiebt nur Base/Build/Peak. Taperlänge und Deload-Wochen
    sind die Formel von vorher (9 %, 2–3 Wochen; jede 4. bis vor die Woche
    vor dem Taper)."""
    taper = min(3, max(2, round(wochen * 0.09)))
    taper_start = wochen - taper + 1
    assert [(n, s, e) for n, s, e in phase_boundaries(wochen) if n == "Taper"] == [
        ("Taper", taper_start, wochen)
    ]
    assert deload_wochen(wochen) == set(range(4, taper_start - 1, 4))


@pytest.mark.parametrize("wochen", [w for w in range(4, 53) if len(deload_wochen(w)) >= 2])
def test_phasen_enden_mit_dem_deload(wochen):
    grenzen = phase_boundaries(wochen)
    assert [n for n, _s, _e in grenzen] == ["Base", "Build", "Peak", "Taper"]
    for name, _s, ende in grenzen[:2]:
        assert ende in deload_wochen(wochen), f"{wochen} Wochen: {name} endet in W{ende}"
    # Keine Phase beginnt mit einem Deload.
    for name, start, _e in grenzen:
        assert start not in deload_wochen(wochen), f"{wochen} Wochen: {name} beginnt mit Deload"


@pytest.mark.parametrize("wochen", [w for w in range(4, 53) if len(deload_wochen(w)) >= 2])
def test_bloecke_drei_plus_eins(wochen):
    """Jeder Block in Base und Build ist genau 3 + 1. Nur der Rest im Peak
    nach dem letzten Deload hat keinen — vor dem Taper liegt nie einer."""
    deloads = deload_wochen(wochen)
    for name, von, bis in _bloecke(wochen):
        if name.startswith(("Base", "Build")):
            assert bis - von + 1 == 4 and bis in deloads, f"{wochen} Wochen: {name} W{von}–{bis}"
        # Ein geteilter Peak hat keinen Block aus nur einer Woche (die hängt am
        # Block davor). Ungeteilt darf er kurz sein: 11 Wochen hatten schon
        # vorher nur eine Peakwoche.
        if name.startswith("Peak "):
            assert bis - von + 1 >= 2, f"{wochen} Wochen: {name} nur eine Woche"


@pytest.mark.parametrize("wochen, erwartet", [
    (10, (3, 3, 2)),    # 10 km: zu kurz für den Takt, Anteile wie bisher
    (12, (4, 4, 2)),    # Sprint, Zeitfahren: lag schon im Takt
    (14, (4, 4, 4)),    # Halbmarathon, vorher 5/5/2
    (16, (8, 4, 2)),    # Radmarathon: Gleichstand Base/Build → Base länger
    (18, (8, 4, 4)),    # Marathon: ebenso
    (20, (8, 4, 6)),    # Olympisch: Gleichstand → Peak mindestens 4 Wochen
    (24, (8, 8, 6)),    # Rad-Ultra: ebenso
    (33, (12, 12, 6)),  # Mitteldistanz: unverändert
    (40, (16, 16, 5)),  # Langdistanz: Peak bleibt ≥ 4, dann Build länger
])
def test_phasenlaengen_wie_mit_amir_abgesprochen(wochen, erwartet):
    laengen = tuple(e - s + 1 for n, s, e in phase_boundaries(wochen) if n != "Taper")
    assert laengen == erwartet


def test_mitteldistanz_peak_in_vier_und_zwei():
    """Vorher Peak 1–3 zu je zwei Wochen, jetzt ein 3+1-Block und der Rest."""
    peak = [b for b in _bloecke(33) if b[0].startswith("Peak")]
    assert peak == [["Peak 1", 25, 28], ["Peak 2", 29, 30]]
