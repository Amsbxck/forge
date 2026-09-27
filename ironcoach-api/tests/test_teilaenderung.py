"""Einzelne Tage ändern, statt die Woche neu zu schreiben.

`update_training_plan` verlangt alle sieben Tage mit Blocks, Watt- und
Pacewerten — rund 3000 Token Ausgabe. Wer am Mittwoch Donnerstag bis Sonntag
umstellen will, bezahlt drei unveränderte Tage mit, und das Modell schreibt sie
neu ab. Das kostet nicht nur Geld: Jede Wiederholung ist eine Gelegenheit, eine
Zahl zu verändern, die niemand ändern wollte.

Die unberührten Tage laufen jetzt gar nicht durch das Modell.
"""

from datetime import date

import pytest

from services.plan_merge import merge_days

WOCHE = {
    "week": 12,
    "coaching_comment": "unberührt",
    "days": [
        {"date": "2026-09-28", "day": "Montag", "session_type": "rest"},
        {"date": "2026-09-29", "day": "Dienstag", "session_type": "swim", "duration_min": 45},
        {"date": "2026-09-30", "day": "Mittwoch", "session_type": "run", "duration_min": 60},
        {"date": "2026-10-01", "day": "Donnerstag", "session_type": "bike", "duration_min": 90},
        {"date": "2026-10-02", "day": "Freitag", "session_type": "rest"},
        {"date": "2026-10-03", "day": "Samstag", "session_type": "brick", "duration_min": 150},
        {"date": "2026-10-04", "day": "Sonntag", "session_type": "run", "duration_min": 75},
    ],
}

MITTWOCH = date(2026, 9, 30)


def test_nur_die_gelieferten_tage_aendern_sich():
    """Der Kern: Donnerstag bis Sonntag umstellen, Montag bis Mittwoch bleibt."""
    inhalt, ok, weg = merge_days(
        WOCHE,
        [
            {"date": "2026-10-01", "day": "Donnerstag", "session_type": "swim", "duration_min": 40},
            {"date": "2026-10-04", "day": "Sonntag", "session_type": "rest"},
        ],
        heute=MITTWOCH,
    )
    assert ok == ["2026-10-01", "2026-10-04"]
    assert weg == []

    nach_datum = {d["date"]: d for d in inhalt["days"]}
    assert nach_datum["2026-10-01"]["session_type"] == "swim"
    assert nach_datum["2026-10-04"]["session_type"] == "rest"
    # Wortgleich, nicht nur inhaltlich gleich — sie wurden nicht neu erzeugt.
    assert nach_datum["2026-09-29"] == WOCHE["days"][1]
    assert nach_datum["2026-10-03"] == WOCHE["days"][5]


def test_die_woche_behaelt_sieben_tage():
    inhalt, _, _ = merge_days(
        WOCHE, [{"date": "2026-10-02", "session_type": "gym"}], heute=MITTWOCH
    )
    assert len(inhalt["days"]) == 7
    assert [d["date"] for d in inhalt["days"]] == [d["date"] for d in WOCHE["days"]]


def test_alles_ausser_den_tagen_bleibt_stehen():
    inhalt, _, _ = merge_days(
        WOCHE, [{"date": "2026-10-02", "session_type": "gym"}], heute=MITTWOCH
    )
    assert inhalt["coaching_comment"] == "unberührt"
    assert inhalt["week"] == 12


def test_vergangene_tage_werden_abgewiesen():
    """Ein Plan ist auch ein Protokoll dessen, was vorgesehen war.

    Rückwirkend geändert wäre jeder Soll/Ist-Vergleich wertlos.
    """
    inhalt, ok, weg = merge_days(
        WOCHE, [{"date": "2026-09-29", "session_type": "rest"}], heute=MITTWOCH
    )
    assert ok == []
    assert weg == ["2026-09-29 (vergangen)"]
    assert inhalt["days"][1]["session_type"] == "swim"


def test_absolvierte_tage_werden_abgewiesen():
    """Sonst entstünde eine Planerfüllung, die nie stattgefunden hat."""
    inhalt, ok, weg = merge_days(
        WOCHE,
        [{"date": "2026-10-01", "session_type": "rest"}],
        gesperrte_daten={date(2026, 10, 1)},
        heute=MITTWOCH,
    )
    assert ok == []
    assert weg == ["2026-10-01 (bereits absolviert)"]
    assert inhalt["days"][3]["session_type"] == "bike"


def test_fremdes_datum_haengt_keinen_achten_tag_an():
    inhalt, ok, weg = merge_days(
        WOCHE, [{"date": "2026-10-11", "session_type": "run"}], heute=MITTWOCH
    )
    assert ok == []
    assert weg == ["2026-10-11 (liegt nicht in dieser Woche)"]
    assert len(inhalt["days"]) == 7


def test_tag_ohne_datum_wird_abgewiesen():
    """Ohne Datum liesse sich nicht sagen, welcher Tag ersetzt werden soll."""
    _, ok, weg = merge_days(WOCHE, [{"day": "Freitag", "session_type": "gym"}], heute=MITTWOCH)
    assert ok == []
    assert weg == ["Freitag (kein gültiges Datum)"]


def test_der_ersetzte_tag_wird_ganz_ersetzt():
    """Kein Mischen Feld für Feld: Bliebe aus dem alten Tag ein Wattblock
    stehen, während der neue ein Lauf ist, trüge die Einheit Vorgaben aus
    zwei Sportarten."""
    inhalt, _, _ = merge_days(
        WOCHE,
        [{"date": "2026-10-01", "session_type": "run", "duration_min": 30}],
        heute=MITTWOCH,
    )
    donnerstag = inhalt["days"][3]
    assert donnerstag == {"date": "2026-10-01", "session_type": "run", "duration_min": 30}


def test_das_werkzeug_verlangt_nur_geaenderte_tage():
    """Die Beschreibung ist die einzige Stelle, an der das Modell es erfährt."""
    from services.claude_service import ADJUST_DAYS_TOOL

    assert ADJUST_DAYS_TOOL["name"] == "adjust_training_days"
    beschreibung = ADJUST_DAYS_TOOL["description"]
    assert "Nur die Tage" in beschreibung
    assert ADJUST_DAYS_TOOL["input_schema"]["required"] == ["days"]


def test_der_coach_kennt_beide_werkzeuge():
    """Ohne beide im Aufruf kann das Modell die Teiländerung nicht wählen."""
    import inspect

    from services import claude_service

    quelle = inspect.getsource(claude_service.chat_with_coach)
    assert "tools=[ADJUST_DAYS_TOOL, UPDATE_PLAN_TOOL]" in quelle
