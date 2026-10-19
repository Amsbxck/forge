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
