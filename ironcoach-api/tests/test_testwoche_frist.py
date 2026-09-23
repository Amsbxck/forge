"""Alle drei Monate, mit einer Woche Vorwarnung.

Ein Maximaltest kostet eine Trainingswoche und zwei bis drei Tage
Erholung. Ihn zu wiederholen, solange die Werte frisch sind, bringt keine
neue Auskunft — es misst dasselbe noch einmal und nimmt dem Aufbau eine
Woche.

Die Frist von 90 Tagen stand schon im Prompt, als Hinweis an den Coach.
Sie hinderte aber niemanden daran, jede Woche eine neue Testwoche
anzulegen.
"""

from datetime import date, timedelta

import pytest

from models import AthleteProfile, RaceResult
from services.benchmark_timing import (
    TAGE_BIS_NEUTEST, VORWARNUNG_TAGE, faelligkeit, prompt_block, pruefe,
)

HEUTE = date(2026, 9, 23)


@pytest.fixture(autouse=True)
def ohne_rennen(db):
    db.query(RaceResult).delete()
    db.commit()
    yield
    db.query(RaceResult).delete()
    db.commit()


def test_frische_werte_sperren_den_test(client, db):
    lage = pruefe(db, None, heute=HEUTE, gemessen_am=HEUTE - timedelta(days=3))
    assert lage["moeglich"] is False
    assert "erst 3 Tage alt" in lage["gruende"][0]
    # Und der Ersatztermin ist der Montag nach Ablauf der Frist.
    assert lage["frueheste"] >= HEUTE + timedelta(days=TAGE_BIS_NEUTEST - 3)


def test_nach_der_frist_ist_er_wieder_erlaubt(client, db):
    lage = pruefe(db, None, heute=HEUTE, gemessen_am=HEUTE - timedelta(days=TAGE_BIS_NEUTEST))
    assert lage["moeglich"] is True


def test_ohne_messung_gibt_es_keine_sperre(client, db):
    """Wer noch nie gemessen hat, soll nicht warten müssen."""
    lage = pruefe(db, None, heute=HEUTE, gemessen_am=None)
    assert lage["moeglich"] is True


def test_die_frist_zaehlt_ab_dem_testtermin_nicht_ab_heute(client, db):
    """Wie bei der Sperre nach einem Wettkampf: Getestet wird am Montag.

    Liegt der kommende Montag nach Ablauf der Frist, ist das Anlegen heute
    schon in Ordnung — der Test selbst findet ja später statt.
    """
    montag = HEUTE + timedelta(days=(7 - HEUTE.weekday()))
    gemessen = montag - timedelta(days=TAGE_BIS_NEUTEST)
    assert (HEUTE - gemessen).days < TAGE_BIS_NEUTEST, "heute noch innerhalb der Frist"

    lage = pruefe(db, None, heute=HEUTE, gemessen_am=gemessen)
    assert lage["moeglich"] is True


@pytest.mark.parametrize("tage_her, vorwarnung, faellig", [
    (0, False, False),
    (TAGE_BIS_NEUTEST - VORWARNUNG_TAGE - 1, False, False),
    (TAGE_BIS_NEUTEST - VORWARNUNG_TAGE + 1, True, False),
    (TAGE_BIS_NEUTEST, True, True),
    (TAGE_BIS_NEUTEST + 30, True, True),
])
def test_vorwarnung_kommt_eine_woche_vorher(tage_her, vorwarnung, faellig):
    stand = faelligkeit(HEUTE - timedelta(days=tage_her), HEUTE)
    assert stand["vorwarnung"] is vorwarnung
    assert stand["faellig"] is faellig


def test_die_vorwarnung_nennt_die_woche():
    stand = faelligkeit(HEUTE - timedelta(days=TAGE_BIS_NEUTEST - 6), HEUTE)
    assert "6 Tagen" in stand["text"]
    assert "frei" in stand["text"]
    assert stand["start"].weekday() == 0, "ein Montag"


def test_nie_gemessen_heisst_faellig():
    stand = faelligkeit(None, HEUTE)
    assert stand["faellig"] is True
    assert "noch nie gemessen" in stand["text"]


def test_der_coach_erfaehrt_es_ebenfalls():
    text = prompt_block(HEUTE - timedelta(days=TAGE_BIS_NEUTEST - 3), HEUTE)
    assert "TESTWOCHE" in text
    assert "Deload" in text, "und wohin sie nicht gehört"
    # Solange nichts ansteht, bleibt der Block leer.
    assert prompt_block(HEUTE, HEUTE) == ""
