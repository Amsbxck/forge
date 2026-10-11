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

from core.phasenregeln import BLOCK_FENSTER_WOCHEN, PHASENREGELN, prompt_block
from services.week_shape import bericht, harte_einheiten

MONTAG = date(2026, 4, 6)  # ein Montag


@pytest.fixture
def aufbauwochen(db):
    """Vier Wochen Vorgaben, je Woche ein eigener Plan."""
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).first()
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
