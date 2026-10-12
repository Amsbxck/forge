"""Die Grundbasis einer Woche — zählt überhaupt jemand die Krafteinheiten?

Bisher nicht. `PHASENREGELN[...]["gym"]` wurde an genau einer Stelle gelesen
und dort nur als Prompt-Text gerendert; kein Zähler im ganzen Code sah
Krafteinheiten an.

An acht echten geplanten Wochen gemessen verfehlten **sieben** die
Kraftvorgabe, und nur **eine** davon war wirklich voll. In den anderen gab es
freie Tage. Der Doppeltag löst also einen Fall; die übrigen sechs fielen
schlicht niemandem auf.

Die Formen aus dieser Messung sind hier als Vorgaben nachgebaut — die echten
Wochen liegen nicht in dieser Datenbank, und ein Test gegen Produktionsdaten
wäre auch keiner, sondern eine Momentaufnahme. Nachgebaut sind die beiden
Lagen, auf die es ankommt:

  * **6 Trainingstage, 1 Ruhetag, 0 Kraft** — wirklich voll. Hier ist der
    Doppeltag die Antwort.
  * **4 Trainingstage, 3 Ruhetage, 0 Kraft** — da war Platz. Hier ist der
    Doppeltag die falsche Antwort.

Dass **ein** freier Tag kein Platz ist, sondern der Ruhetag, ist die
Entscheidung aus `core/phasenregeln.vorrang_block` Stufe 2. Ohne sie hätte der
Bericht genau das vorgeschlagen, was die Rangordnung verbietet.
"""

from datetime import date, timedelta

import pytest

from services.week_shape import grundbasis, nach_anpassung

MONTAG = date(2026, 4, 6)  # ein Montag
SONNTAG = MONTAG + timedelta(days=6)


@pytest.fixture
def woche(db):
    """Eine Woche Vorgaben bauen. `tage` ist eine Liste von Disziplinlisten.

    Ein Tag mit zwei Disziplinen ist ein Doppeltag — zwei Zeilen mit demselben
    Datum, genau so, wie `plan_projection` sie aus zwei Tageseinträgen schreibt.
    """
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).first()
    angelegt = []

    def bauen(tage: list[list[str]], phase: str = "Grundlage", start: date = MONTAG):
        plan = WeeklyPlan(
            user_id=nutzer.id, week_number=77, week_start=start,
            week_end=start + timedelta(days=6), plan_phase=phase,
            plan_content={},
        )
        db.add(plan)
        db.commit()
        angelegt.append(plan)
        for i, disziplinen in enumerate(tage):
            for d in disziplinen:
                p = PlannedSession(
                    user_id=nutzer.id, plan_id=plan.id, week_number=77,
                    planned_date=start + timedelta(days=i), day_name="Tag",
                    discipline=d,
                    training_type="z2_endurance" if d != "gym" else "strength",
                    duration_min=60, day_index=i,
                )
                db.add(p)
                angelegt.append(p)
        db.commit()
        return nutzer.id

    yield bauen
    for o in reversed(angelegt):
        db.delete(o)
    db.commit()


# Die volle Woche: sechs Trainingstage, ein Ruhetag, keine Kraft.
VOLL = [["bike"], ["swim"], ["run"], ["bike"], ["rest"], ["run"], ["bike"]]

# Die Woche mit Platz: vier Trainingstage, drei Ruhetage, keine Kraft.
PLATZ = [["bike"], ["rest"], ["run"], ["rest"], ["rest"], ["bike"], ["run"]]


def test_volle_woche_ohne_kraft(woche, db):
    uid = woche(VOLL)
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage")
    assert gb["gym"] == 0
    assert gb["gym_soll"] == 2
    assert gb["trainingstage"] == 6
    assert gb["ruhetage"] == 1
    assert gb["einheiten"] == 6
    assert gb["vorhanden"] is True


def test_woche_mit_platz_ohne_kraft(woche, db):
    uid = woche(PLATZ)
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage")
    assert gb["gym"] == 0
    assert gb["trainingstage"] == 4
    assert gb["ruhetage"] == 3
    assert gb["einheiten"] == 4


def test_doppeltag_zaehlt_zwei_krafteinheiten(woche, db):
    """Der Kern: Kraft wird über Zeilen gezählt, nicht über Tage.

    Zwei Krafteinheiten an verschiedenen Tagen und zwei an einem Doppeltag
    müssen dieselbe Zahl ergeben. Über Tage gezählt wäre der Doppeltag eine
    Einheit — und der Zähler hätte das Mittel nicht gesehen, mit dem die
    Vorgabe gehalten werden soll.
    """
    uid = woche([
        ["bike"], ["swim", "gym"], ["run"], ["bike", "gym"], ["rest"],
        ["run"], ["bike"],
    ])
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage")
    assert gb["gym"] == 2
    assert gb["gym_soll"] == 2
    # Die Doppeltage belegen keinen zusätzlichen Tag.
    assert gb["trainingstage"] == 6
    assert gb["ruhetage"] == 1
    # Acht Einheiten auf sechs Tagen — das ist der Sinn der Sache.
    assert gb["einheiten"] == 8


def test_erfuellte_vorgabe_wird_nicht_gemeldet(woche, db):
    """Kein Rauschen, wenn alles passt — dasselbe Prinzip wie bei `bericht`."""
    from services.week_shape import _kraftluecke

    uid = woche([
        ["bike"], ["gym"], ["run"], ["gym"], ["rest"], ["run"], ["bike"],
    ])
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage")
    assert gb["gym"] == 2
    assert _kraftluecke(gb) is None


def test_der_satz_unterscheidet_die_beiden_lagen(woche, db):
    """Voll heißt Doppeltag, Platz heißt kein Doppeltag. Das ist der ganze Punkt."""
    from services.week_shape import _kraftluecke

    uid = woche(VOLL)
    satz = _kraftluecke(grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage"))
    assert satz is not None
    assert "0 von 2" in satz
    assert "Doppeltag" in satz
    assert "war Platz" not in satz


def test_der_satz_schlaegt_keinen_doppeltag_vor_wo_platz_war(woche, db):
    from services.week_shape import _kraftluecke

    uid = woche(PLATZ)
    satz = _kraftluecke(grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage"))
    assert satz is not None
    assert "0 von 2" in satz
    assert "war Platz" in satz
    assert "keinen Doppeltag" in satz


def test_ein_ruhetag_ist_kein_platz(woche, db):
    """Stufe 2 der Rangordnung: Der Ruhetag bleibt.

    Bei genau einem freien Tag darf der Bericht nicht „da war Platz" sagen —
    sonst schlägt er vor, den Ruhetag zu opfern, was zwei Abschnitte weiter
    oben im selben Prompt verboten ist.
    """
    from services.week_shape import _kraftluecke

    uid = woche(VOLL)
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Grundlage")
    assert gb["ruhetage"] == 1
    assert "Doppeltag" in _kraftluecke(gb)


def test_phase_ohne_kraftvorgabe_meldet_nichts(woche, db):
    """Taper und Wettkampfwoche haben `gym: 0` — „0 von 0" wäre Rauschen."""
    from services.week_shape import _kraftluecke

    uid = woche(VOLL, phase="Taper")
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid, phase="Taper")
    assert gb["gym_soll"] == 0
    assert gb["vorhanden"] is False
    assert _kraftluecke(gb) is None


def test_vorbereitungswochen_haben_eine_kraftvorgabe(woche, db):
    """Der Phasen-Alias: „Vorbereitung auf den Aufbau" löst auf die Grundlage auf.

    Ohne ihn gab `regeln_fuer` dort `None` — keine Kraftvorgabe, kein Bericht.
    Und genau in diesen Wochen lagen die gemessenen Fehltreffer.
    """
    uid = woche(VOLL, phase="Vorbereitung auf den Aufbau")
    gb = grundbasis(db, MONTAG, SONNTAG, user_id=uid,
                    phase="Vorbereitung auf den Aufbau")
    assert gb["gym_soll"] == 2
    assert gb["vorhanden"] is True


def test_leere_woche_meldet_nichts(db):
    """Ohne Vorgaben keine Auskunft — nicht „0 von 2"."""
    gb = grundbasis(db, date(2030, 1, 7), date(2030, 1, 13), phase="Grundlage")
    assert gb["vorhanden"] is False


def test_nach_anpassung_schweigt_in_einer_vergangenen_woche(woche, db):
    """Am Samstag ist an der Woche nichts mehr zu reparieren.

    `plan_merge` weist vergangene Tage ausdrücklich ab. Ein Befund über eine
    abgelaufene Woche wäre ein Vorwurf ohne Mittel.
    """
    uid = woche(VOLL)
    assert nach_anpassung(db, MONTAG, SONNTAG, "Grundlage", user_id=uid,
                          heute=SONNTAG + timedelta(days=1)) is None
    # Mitten in der Woche dagegen liegt noch etwas vor dem Athleten.
    befund = nach_anpassung(db, MONTAG, SONNTAG, "Grundlage", user_id=uid,
                            heute=MONTAG + timedelta(days=2))
    assert befund is not None
    assert "0 von 2" in befund
