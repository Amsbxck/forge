"""Ein Wettkampf, der nach dem Saisonziel liegt.

Der Saisonzustand meldet ab dem Tag nach dem A-Rennen `off_season`. Das ist
richtig und bleibt so — an seinem Ziel gemessen ist die Saison vorbei.

Daraus folgt aber nicht, dass nichts mehr ansteht. Wer sieben Tage nach
seiner Mitteldistanz einen Halbmarathon läuft, steht in einer
Wettkampfwoche, während der Rahmen „Off Season" sagt. Ohne einen Hinweis
darauf bekam der Coach zwei widersprechende Signale und musste raten.
"""

from datetime import date, timedelta

from core.race_types import season_state
from services.race_calendar import week_block

ZIEL = date(2027, 6, 27)          # Sonntag
HALBMARATHON = date(2027, 7, 4)   # Sonntag darauf


def _woche(tag):
    montag = tag - timedelta(days=tag.weekday())
    return montag, montag + timedelta(days=6)


def _anlegen(client, prioritaet, tag, name, sport="triathlon", distanz="middle"):
    return client.post("/api/goals", json={
        "sport": sport, "distance": distanz, "race_date": str(tag),
        "race_name": name, "priority": prioritaet,
    }).json()


def test_der_saisonzustand_bleibt_unveraendert():
    """Nicht angefasst — die Regel gilt weiter wie zuvor."""
    assert season_state(ZIEL, today=ZIEL - timedelta(days=3)) == "race_week"
    assert season_state(ZIEL, today=ZIEL + timedelta(days=1)) == "off_season"
    assert season_state(ZIEL, today=HALBMARATHON) == "off_season"


def test_wettkampf_nach_dem_ziel_wird_als_solcher_benannt(client, db):
    _anlegen(client, "A", ZIEL, "Saisonziel")
    _anlegen(client, "B", HALBMARATHON, "Halbmarathon",
             sport="running", distanz="half_marathon")

    text = week_block(db, *_woche(HALBMARATHON))

    # Die Anweisung zum Rennen selbst steht weiterhin da.
    assert "WETTKAMPF IN DIESER WOCHE" in text
    # Und der Widerspruch zum Saisonzustand wird ausdrücklich aufgelöst.
    assert "off_season" in text
    assert "keine Off-Season-Woche" in text
    assert str(HALBMARATHON) in text


def test_vor_dem_saisonziel_bleibt_der_hinweis_aus(client, db):
    """Solange das Ziel noch aussteht, gibt es keinen Widerspruch."""
    _anlegen(client, "A", ZIEL, "Saisonziel")
    _anlegen(client, "B", ZIEL - timedelta(days=21), "Vorbereitungsrennen",
             sport="running", distanz="half_marathon")

    text = week_block(db, *_woche(ZIEL - timedelta(days=21)))
    assert "WETTKAMPF IN DIESER WOCHE" in text
    assert "Off-Season" not in text
    assert "Das Saisonziel bleibt unverändert das A-Rennen." in text
