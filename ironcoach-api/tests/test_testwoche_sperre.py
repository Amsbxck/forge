"""Ab wann die Testwoche nach einem Wettkampf wieder erlaubt ist.

Die Sperre soll verhindern, dass ein Maximaltest die Restermüdung eines
Rennens misst — die Werte gälten anschließend monatelang als Vorgabe.

Entscheidend ist dabei der Tag, an dem *getestet* wird, nicht der Tag, an
dem jemand auf den Knopf drückt. Die Testwoche beginnt immer am kommenden
Montag. Wer am 16. Tag nach seinem Rennen steht und dessen Montag der
22. Tag ist, hat die Frist zum Testzeitpunkt voll — ihn zu sperren
verschiebt den Test grundlos um eine weitere Woche.
"""

from datetime import date, timedelta

import pytest

from models import RaceResult
from services.benchmark_timing import SPERRE_NACH_RENNEN, montag_ab, naechster_montag, pruefe


@pytest.fixture(autouse=True)
def ohne_altlasten(db):
    db.query(RaceResult).delete()
    db.commit()
    yield
    db.query(RaceResult).delete()
    db.commit()


def _rennen(db, tag):
    from models import AthleteProfile
    profil = db.query(AthleteProfile).first()
    db.add(RaceResult(user_id=profil.user_id, race_date=tag,
                      sport="triathlon", distance="middle", race_name="Test"))
    db.commit()


def test_montag_ab_nimmt_den_tag_selbst():
    montag = date(2026, 9, 21)
    assert montag.weekday() == 0
    assert montag_ab(montag) == montag              # schon Montag -> bleibt
    assert naechster_montag(montag) == montag + timedelta(days=7)
    assert montag_ab(date(2026, 9, 22)) == date(2026, 9, 28)


@pytest.mark.parametrize("tage_her", [0, 5, 10])
def test_kurz_nach_dem_rennen_bleibt_gesperrt(client, db, tage_her):
    """Der kommende Montag liegt dann noch klar innerhalb der Frist."""
    heute = date(2026, 9, 19)                        # Samstag
    _rennen(db, heute - timedelta(days=tage_her))

    lage = pruefe(db, None, heute=heute)
    assert lage["moeglich"] is False
    assert lage["gruende"]


def test_wenn_die_frist_bis_zum_montag_ablaeuft_ist_es_erlaubt(client, db):
    """Der Fall, der vorher fälschlich gesperrt wurde.

    Samstag, 16 Tage nach dem Rennen. Der kommende Montag ist Tag 18 —
    noch zu früh. Eine Woche später wäre er Tag 25.
    """
    heute = date(2026, 9, 19)                        # Samstag
    montag = naechster_montag(heute)                 # 21.09., Tag X
    # Rennen so legen, dass der Montag genau der 21. Tag ist.
    _rennen(db, montag - timedelta(days=SPERRE_NACH_RENNEN))

    lage = pruefe(db, None, heute=heute)
    assert lage["moeglich"] is True, "am Testtermin ist die Frist voll"
    assert lage["start"] == montag
    # Heute sind es erst 19 Tage — nach der alten Rechnung wäre gesperrt.
    assert (heute - (montag - timedelta(days=SPERRE_NACH_RENNEN))).days < SPERRE_NACH_RENNEN


def test_ein_tag_zu_frueh_bleibt_gesperrt(client, db):
    heute = date(2026, 9, 19)
    montag = naechster_montag(heute)
    _rennen(db, montag - timedelta(days=SPERRE_NACH_RENNEN - 1))

    lage = pruefe(db, None, heute=heute)
    assert lage["moeglich"] is False
    # Der Ersatztermin ist der Montag darauf, nicht zwei Wochen später.
    assert lage["frueheste"] == montag + timedelta(days=7)
