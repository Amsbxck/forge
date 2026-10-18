"""Ein Doppeltag sind zwei Einträge mit demselben Datum.

Warum das eine eigene Prüfung braucht: Das Tagesschema trägt **eine** Sportart
je Eintrag (`services/claude_service.DAY_SCHEMA`). Ein Doppeltag lässt sich
darin nur als zwei Einträge mit gleichem Datum ausdrücken — alles andere
versteckt die zweite Einheit in einer Notiz, wo kein Zähler und kein
Soll/Ist-Abgleich sie findet.

`merge_days` hatte dafür eine Annahme eingebaut, die genau das verhinderte: ein
Index je Datum (`{datum: i}`). Von zwei Einträgen überlebte nur der letzte, und
eine Änderung an diesem Tag ersetzte stillschweigend die falsche Hälfte. Die
Tests hier halten die neue Semantik fest: **ein geliefertes Datum ersetzt alle
Einträge dieses Datums.**

Diese Vollersetzung ist bewusst so gewählt und nicht „(Datum, Sportart)":
Letzteres hätte das Ändern der Sportart eines Tages zerstört — aus „Lauf wird
Rad" wäre „Lauf **und** Rad" geworden.
"""

from datetime import date

from services.plan_merge import merge_days

# Dienstag trägt einen Doppeltag: Schwimmen und Kraft. Genau der Fall, für den
# die Grundbasis den Doppeltag als Mittel vorsieht — Schwimmen erzeugt keine
# Stoßbelastung und beansprucht andere Muskeln als Kraft.
WOCHE = {
    "week": 12,
    "days": [
        {"date": "2026-09-28", "day": "Montag", "session_type": "rest"},
        {"date": "2026-09-29", "day": "Dienstag", "session_type": "swim", "duration_min": 45},
        {"date": "2026-09-29", "day": "Dienstag", "session_type": "gym", "duration_min": 50},
        {"date": "2026-09-30", "day": "Mittwoch", "session_type": "run", "duration_min": 60},
        {"date": "2026-10-01", "day": "Donnerstag", "session_type": "bike", "duration_min": 90},
        {"date": "2026-10-02", "day": "Freitag", "session_type": "rest"},
        {"date": "2026-10-03", "day": "Samstag", "session_type": "brick", "duration_min": 150},
        {"date": "2026-10-04", "day": "Sonntag", "session_type": "run", "duration_min": 75},
    ],
}

MONTAG = date(2026, 9, 28)


def _am(inhalt, tag):
    return [d for d in inhalt["days"] if d["date"] == tag]


def test_doppeltag_ueberlebt_eine_aenderung_an_einem_anderen_tag():
    """Der Regressionsfall: Donnerstag ändern, Dienstag behält beide Hälften."""
    inhalt, ok, weg = merge_days(
        WOCHE,
        [{"date": "2026-10-01", "day": "Donnerstag", "session_type": "swim"}],
        heute=MONTAG,
    )
    assert ok == ["2026-10-01"]
    assert weg == []

    dienstag = _am(inhalt, "2026-09-29")
    assert len(dienstag) == 2
    assert {d["session_type"] for d in dienstag} == {"swim", "gym"}
    # Wortgleich: die unberührten Einträge wurden nicht neu erzeugt.
    assert dienstag == [WOCHE["days"][1], WOCHE["days"][2]]
    assert len(inhalt["days"]) == 8


def test_ein_doppeltag_laesst_sich_neu_anlegen():
    """Aus einem einzelnen Tag zwei machen — das, was der Coach selbst tun soll.

    Der Freitag ist ein Ruhetag; er darf nicht zum Doppeltag werden. Also
    bekommt der Mittwoch die zweite Einheit: Lauf plus Kraft.
    """
    inhalt, ok, weg = merge_days(
        WOCHE,
        [
            {"date": "2026-09-30", "day": "Mittwoch", "session_type": "run", "duration_min": 60},
            {"date": "2026-09-30", "day": "Mittwoch", "session_type": "gym", "duration_min": 40},
        ],
        heute=MONTAG,
    )
    # Ein geändertes Datum, nicht zwei — es ist ein Tag.
    assert ok == ["2026-09-30"]
    assert weg == []

    mittwoch = _am(inhalt, "2026-09-30")
    assert len(mittwoch) == 2
    assert [d["session_type"] for d in mittwoch] == ["run", "gym"]
    assert len(inhalt["days"]) == 9


def test_ein_doppeltag_laesst_sich_auf_eine_einheit_zusammenziehen():
    """Die Gegenrichtung: ein geliefertes Datum ersetzt alles an diesem Datum."""
    inhalt, ok, _ = merge_days(
        WOCHE,
        [{"date": "2026-09-29", "day": "Dienstag", "session_type": "swim", "duration_min": 60}],
        heute=MONTAG,
    )
    assert ok == ["2026-09-29"]
    dienstag = _am(inhalt, "2026-09-29")
    assert len(dienstag) == 1
    assert dienstag[0]["duration_min"] == 60
    assert len(inhalt["days"]) == 7


def test_sportart_eines_tages_aendern_erzeugt_keinen_doppeltag():
    """Die Falle der Alternative „(Datum, Sportart)" — hier bewusst ausgeschlossen.

    Hätte `merge_days` auf Datum **und** Sportart geschlüsselt, wäre aus
    „Mittwoch statt Lauf lieber Rad" ein Doppeltag Lauf + Rad geworden.
    """
    inhalt, ok, _ = merge_days(
        WOCHE,
        [{"date": "2026-09-30", "day": "Mittwoch", "session_type": "bike", "duration_min": 90}],
        heute=MONTAG,
    )
    assert ok == ["2026-09-30"]
    mittwoch = _am(inhalt, "2026-09-30")
    assert len(mittwoch) == 1
    assert mittwoch[0]["session_type"] == "bike"


def test_die_reihenfolge_der_tage_bleibt():
    """Nach dem Einsetzen stehen die Tage weiter in Wochenreihenfolge.

    Der Wochenplan wird in dieser Reihenfolge angezeigt; eine nach hinten
    gerutschte Mittwochseinheit wäre für den Athleten ein anderer Plan.
    """
    inhalt, _, _ = merge_days(
        WOCHE,
        [
            {"date": "2026-09-30", "day": "Mittwoch", "session_type": "run"},
            {"date": "2026-09-30", "day": "Mittwoch", "session_type": "gym"},
            {"date": "2026-10-04", "day": "Sonntag", "session_type": "rest"},
        ],
        heute=MONTAG,
    )
    daten = [d["date"] for d in inhalt["days"]]
    assert daten == sorted(daten)


def test_vergangene_und_gesperrte_doppeltage_bleiben_unberuehrt():
    """Die beiden unverhandelbaren Grenzen gelten für den ganzen Tag."""
    inhalt, ok, weg = merge_days(
        WOCHE,
        [{"date": "2026-09-29", "day": "Dienstag", "session_type": "run"}],
        heute=date(2026, 9, 30),
    )
    assert ok == []
    assert weg == ["2026-09-29 (vergangen)"]
    # Beide Hälften stehen noch, unverändert.
    assert _am(inhalt, "2026-09-29") == [WOCHE["days"][1], WOCHE["days"][2]]

    inhalt, ok, weg = merge_days(
        WOCHE,
        [{"date": "2026-09-29", "day": "Dienstag", "session_type": "run"}],
        gesperrte_daten={date(2026, 9, 29)},
        heute=MONTAG,
    )
    assert ok == []
    assert weg == ["2026-09-29 (bereits absolviert)"]
    assert _am(inhalt, "2026-09-29") == [WOCHE["days"][1], WOCHE["days"][2]]


def test_der_ganze_weg_vom_plan_bis_zur_zaehlung(db):
    """Plan-JSON → Projektion → Grundbasis. Der Weg, auf dem es zählen muss.

    Die Prüfungen oben betreffen nur das Einsetzen, und `test_grundbasis.py`
    legt die Zeilen direkt an. Dazwischen liegt `plan_projection.project_plan`
    — und wenn die zwei Einträge dort zu **einer** Zeile würden, wäre die
    zweite Krafteinheit für jeden Zähler unsichtbar, ohne dass ein Test es
    merkt.
    """
    from datetime import timedelta

    from models import User, WeeklyPlan
    from services.plan_projection import project_plan
    from services.week_shape import grundbasis

    nutzer = db.query(User).order_by(User.id.asc()).first()
    montag = date(2026, 5, 4)  # ein Montag
    tage = []
    for i in range(7):
        tag = montag + timedelta(days=i)
        if i == 1:
            # Der Doppeltag: Schwimmen und Kraft am selben Datum.
            tage.append({"day": "Dienstag", "date": str(tag),
                         "session_type": "swim", "training_type": "technique",
                         "duration_min": 45})
            tage.append({"day": "Dienstag", "date": str(tag),
                         "session_type": "gym", "training_type": "strength",
                         "duration_min": 50})
        elif i == 3:
            tage.append({"day": "Donnerstag", "date": str(tag),
                         "session_type": "gym", "training_type": "strength",
                         "duration_min": 50})
        elif i == 4:
            tage.append({"day": "Freitag", "date": str(tag),
                         "session_type": "rest", "training_type": "rest",
                         "duration_min": 0})
        else:
            tage.append({"day": "Tag", "date": str(tag),
                         "session_type": "bike", "training_type": "z2_endurance",
                         "duration_min": 90})

    plan = WeeklyPlan(
        user_id=nutzer.id, week_number=79, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase="Grundlage",
        plan_content={"days": tage},
    )
    db.add(plan)
    db.commit()
    try:
        geschrieben = project_plan(db, plan)
        # Acht Einträge, acht Zeilen — der Doppeltag wird nicht zusammengefasst.
        assert geschrieben == 8, geschrieben

        gb = grundbasis(db, montag, montag + timedelta(days=6),
                        user_id=nutzer.id, phase="Grundlage")
        # Beide Krafteinheiten gefunden, obwohl eine auf einem Doppeltag liegt.
        assert gb["gym"] == 2
        assert gb["gym_soll"] == 2
        # Sechs belegte Tage, ein Ruhetag — die Vorgabe ist erfüllt, obwohl nur
        # sechs Tage zur Verfügung standen. Genau der Zweck des Doppeltags.
        assert gb["trainingstage"] == 6
        assert gb["ruhetage"] == 1
        assert gb["einheiten"] == 7

        from services.week_shape import _kraftluecke
        assert _kraftluecke(gb) is None
    finally:
        from models import PlannedSession
        db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
        db.delete(plan)
        db.commit()


def test_fremdes_datum_wird_weiter_abgewiesen():
    """Die Woche bekommt keinen achten Tag — nur zweite Einheiten an ihren Tagen."""
    inhalt, ok, weg = merge_days(
        WOCHE,
        [{"date": "2026-10-05", "day": "Montag", "session_type": "run"}],
        heute=MONTAG,
    )
    assert ok == []
    assert weg == ["2026-10-05 (liegt nicht in dieser Woche)"]
    assert {d["date"] for d in inhalt["days"]} == {d["date"] for d in WOCHE["days"]}
