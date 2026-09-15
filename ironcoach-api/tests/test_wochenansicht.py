"""Was "diese Woche" auf dem Dashboard bedeutet.

Die Kachel zählte über `TrainingSession.week_number`, also über die
Planwoche. `get_week_for_date` gibt `max(1, …)` zurück — jedes Datum vor dem
Beginn des Aufbaus wird damit zu Woche 1, und die aktuelle Woche ist dann
ebenfalls 1. Für jeden Athleten, dessen Aufbau noch nicht begonnen hat,
galten dadurch sämtliche jemals absolvierten Einheiten als "diese Woche".

Bei einem Athleten mitten im Aufbau fällt das nicht auf: Dort verteilen sich
die Nummern korrekt. Genau deshalb braucht es einen Test, der den anderen
Fall festhält.
"""

from datetime import date, timedelta

import pytest

from models import AthleteProfile, TrainingSession
from routers.metrics import kalenderwoche


def test_kalenderwoche_laeuft_von_montag_bis_sonntag():
    montag, sonntag = kalenderwoche(date(2026, 9, 15))   # ein Dienstag
    assert montag == date(2026, 9, 14)
    assert sonntag == date(2026, 9, 20)
    assert montag.weekday() == 0 and sonntag.weekday() == 6

    # Ein Montag gehört in seine eigene Woche, nicht in die vorige.
    assert kalenderwoche(date(2026, 9, 14))[0] == date(2026, 9, 14)
    # Ein Sonntag ebenso in seine.
    assert kalenderwoche(date(2026, 9, 20))[1] == date(2026, 9, 20)


@pytest.fixture(autouse=True)
def leere_einheiten(db):
    """Vor jedem Test ein leerer Tisch.

    Die Testumgebung setzt das Schema nur einmal je Lauf auf. Ohne dieses
    Aufräumen zählt jeder Test die Einheiten der vorherigen mit — und die
    Zahlen wären von der Reihenfolge abhängig statt vom geprüften Verhalten.
    """
    db.query(TrainingSession).delete()
    db.commit()
    yield
    db.query(TrainingSession).delete()
    db.commit()


def _einheit(db, tag: date, *, week_number: int, tss: float = 50.0):
    profil = db.query(AthleteProfile).first()
    s = TrainingSession(
        user_id=profil.user_id,
        session_date=tag,
        week_number=week_number,
        discipline="run",
        duration_min=60,
        tss=tss,
    )
    db.add(s)
    db.commit()
    return s


@pytest.fixture
def aufbau_beginnt_spaeter(db):
    """Der Fall aus dem Fehlerbericht: Ziel weit weg, Aufbau noch nicht los."""
    profil = db.query(AthleteProfile).first()
    profil.plan_start_date = date.today() + timedelta(days=90)
    profil.race_date = date.today() + timedelta(days=90 + 7 * 33)
    db.commit()
    return profil


def test_nur_die_laufende_kalenderwoche_zaehlt(client, db, aufbau_beginnt_spaeter):
    heute = date.today()
    montag, _ = kalenderwoche(heute)

    # Alle bekommen Woche 1, weil der Aufbau noch nicht begonnen hat — genau
    # so schreibt der Ingest sie auch in die Datenbank.
    _einheit(db, montag, week_number=1, tss=40)                     # diese Woche
    _einheit(db, montag + timedelta(days=2), week_number=1, tss=60) # diese Woche
    _einheit(db, montag - timedelta(days=7), week_number=1, tss=90) # letzte Woche
    _einheit(db, montag - timedelta(days=40), week_number=1, tss=90)

    daten = client.get("/api/metrics/week").json()

    assert daten["sessions_count"] == 2, "nur die beiden Einheiten dieser Woche"
    assert daten["total_tss"] == pytest.approx(100.0)
    assert daten["total_duration_min"] == 120


def test_gelöschte_einheiten_zaehlen_nicht_mit(client, db, aufbau_beginnt_spaeter):
    from datetime import datetime

    montag, _ = kalenderwoche(date.today())
    _einheit(db, montag, week_number=1, tss=40)
    weg = _einheit(db, montag + timedelta(days=1), week_number=1, tss=40)
    weg.deleted_at = datetime.utcnow()
    db.commit()

    assert client.get("/api/metrics/week").json()["sessions_count"] == 1


def test_trend_buendelt_nach_kalenderwoche(client, db, aufbau_beginnt_spaeter):
    """Vorher fiel alles auf einen Balken; die übrigen blieben leer."""
    montag, _ = kalenderwoche(date.today())
    _einheit(db, montag, week_number=1, tss=30)
    _einheit(db, montag - timedelta(days=7), week_number=1, tss=70)
    _einheit(db, montag - timedelta(days=14), week_number=1, tss=110)

    punkte = client.get("/api/metrics/trends?weeks=4").json()

    assert len(punkte) == 4
    # Aufsteigend nach Datum, die laufende Woche zuletzt.
    assert [p["week_start"] for p in punkte] == [
        str(montag - timedelta(days=21)),
        str(montag - timedelta(days=14)),
        str(montag - timedelta(days=7)),
        str(montag),
    ]
    assert [p["total_tss"] for p in punkte] == [0.0, 110.0, 70.0, 30.0]


def test_athlet_im_aufbau_sieht_weiterhin_seine_woche(client, db):
    """Der Fall, der schon vorher stimmte, muss weiter stimmen."""
    profil = db.query(AthleteProfile).first()
    profil.plan_start_date = date.today() - timedelta(days=7 * 30)
    db.commit()

    montag, _ = kalenderwoche(date.today())
    _einheit(db, montag + timedelta(days=1), week_number=31, tss=55)
    _einheit(db, montag - timedelta(days=3), week_number=30, tss=55)

    daten = client.get("/api/metrics/week").json()
    assert daten["sessions_count"] == 1
    assert daten["total_tss"] == pytest.approx(55.0)
