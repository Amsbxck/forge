"""Was ein Wettkampf je nach Art mit der Saison macht.

Nur das A-Rennen verankert die Saison. B und C liegen darin: Sie werden
beim Planen berücksichtigt, ändern aber weder Planlänge noch Startdatum
noch die Wochenzählung.

Der Test steht hier, weil die Oberfläche das lange anders dargestellt hat:
Die Distanzauswahl zeigte bei jeder Art "· 33 Wochen" — auch bei einem
Trainingswettkampf, für den keine einzige Woche geplant wird.
"""

from datetime import date, timedelta

import pytest


def _ziel(client, prioritaet, tage_voraus, name):
    return client.post("/api/goals", json={
        "sport": "triathlon",
        "distance": "middle",
        "race_date": str(date.today() + timedelta(days=tage_voraus)),
        "race_name": name,
        "priority": prioritaet,
    }).json()


def test_saisonziel_traegt_planlaenge_und_start(client):
    ziel = _ziel(client, "A", 300, "Saisonziel")
    assert ziel["priority"] == "A"
    assert ziel["plan_weeks"], "ein A-Rennen spannt den Aufbau auf"
    assert ziel["plan_start_date"], "und trägt dessen Startdatum"


@pytest.mark.parametrize("prioritaet", ["B", "C"])
def test_zwischen_und_trainingswettkampf_tragen_keine(client, prioritaet):
    """Genau der Punkt, den die Oberfläche falsch anzeigte."""
    _ziel(client, "A", 300, "Saisonziel")
    rennen = _ziel(client, prioritaet, 60, "unterwegs")

    assert rennen["priority"] == prioritaet
    assert rennen["plan_weeks"] is None
    assert rennen["plan_start_date"] is None


def test_ein_zwischenwettkampf_loest_das_saisonziel_nicht_ab(client):
    ziel = _ziel(client, "A", 300, "Saisonziel")
    _ziel(client, "C", 60, "Trainingswettkampf")

    aktiv = client.get("/api/goals/active").json()
    assert aktiv["id"] == ziel["id"]
    assert aktiv["priority"] == "A"
    assert aktiv["plan_start_date"] == ziel["plan_start_date"]


def test_ein_zweites_saisonziel_loest_das_erste_ab(client):
    erstes = _ziel(client, "A", 300, "altes Ziel")
    zweites = _ziel(client, "A", 400, "neues Ziel")

    aktiv = client.get("/api/goals/active").json()
    assert aktiv["id"] == zweites["id"] != erstes["id"]
