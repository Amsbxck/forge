"""FTP aus dem 20-Minuten-Test — und was bei einem Stufentest passiert.

Der 20-Minuten-Test wird gleichmässig gefahren; seine FTP ist 95 % der
Durchschnittsleistung. Ein Stufentest am Smart Trainer steigert die
Leistung bis zum Abbruch und gibt die FTP am Ende selbst aus.

Beides durch dieselbe Rechnung zu schicken geht schief: Die besten zwanzig
Minuten einer Rampe enthalten die leichten Anfangsstufen, der Mittelwert
liegt weit unter der Schwelle — und würde beim Übernehmen die Zahl
ersetzen, die der Trainer ausgegeben hat.
"""

import pytest

from services.benchmark import SCHWELLEN_FAKTOR
from services.segments import best_effort_power, erkenne_stufentest


class _Einheit:
    def __init__(self, watts, duration_min):
        self.streams = {"watts": watts}
        self.duration_min = duration_min


def _rampe(start=100, schritt=20, stufen=12, je_minute=1):
    """Ein Stufenprotokoll, wie Zwift und Co. es fahren."""
    watts = []
    for i in range(stufen):
        watts += [start + i * schritt] * je_minute
    return _Einheit(watts, len(watts))


@pytest.mark.parametrize("bez, einheit, erwartet_min, erwartet_watt", [
    ("Zwift, 20 W je Minute",      _rampe(),                    1, 20),
    ("Trainer, 25 W je 2 Minuten", _rampe(120, 25, 10, 2),      2, 25),
    ("Trainer, 15 W je 3 Minuten", _rampe(150, 15, 9, 3),       3, 15),
])
def test_stufentests_werden_erkannt(bez, einheit, erwartet_min, erwartet_watt):
    treffer = erkenne_stufentest(einheit)
    assert treffer is not None, bez
    assert treffer["stufen_minuten"] == erwartet_min
    assert treffer["zuwachs_watt"] == erwartet_watt


def test_erkennung_haengt_am_zuwachs_nicht_am_verhaeltnis():
    """Der Punkt, an dem eine feste Verhältnisspanne scheitert.

    Bei konstanten 20 Watt je Stufe fällt das Verhältnis von 1,20
    (100→120) auf 1,07 (300→320). Eine Spanne von 1,1 bis 1,3 verpasste
    damit die oberen Stufen — und die sind bei einem Abbruch die letzten.
    """
    hoch = _rampe(start=280, schritt=20, stufen=8)       # Verhältnisse ~1,07
    treffer = erkenne_stufentest(hoch)
    assert treffer is not None
    assert treffer["zuwachs_watt"] == 20


@pytest.mark.parametrize("bez, einheit", [
    ("gleichmässiger Test", _Einheit([10]*8 + [248, 252, 250, 251, 249]*4 + [10]*8, 36)),
    ("Test mit Schlussspurt", _Einheit([10]*5 + [240]*8 + [250]*6 + [268]*6 + [10]*5, 30)),
    ("Intervalle 5x4 Minuten", _Einheit(([300]*4 + [120]*4)*5, 40)),
    ("zu kurz für ein Muster", _Einheit([150, 170, 190, 210], 4)),
])
def test_kein_stufentest(bez, einheit):
    assert erkenne_stufentest(einheit) is None, bez


def test_gleichmaessiger_test_liefert_die_ftp():
    watts = [10] * 10 + [245, 255, 250, 248, 252] * 4 + [10] * 10
    ergebnis = best_effort_power(_Einheit(watts, 40), seconds=1200)
    assert ergebnis["avg_watts"] == 250
    assert round(250 * SCHWELLEN_FAKTOR) == 238


def test_aus_einer_rampe_wird_keine_ftp_abgeleitet(client, db):
    """Statt einer zu niedrigen Zahl kommt eine Erklärung."""
    from datetime import date, timedelta
    from models import AthleteProfile, PlannedSession, TrainingSession, WeeklyPlan
    from services.benchmark import BENCHMARK_PHASE, derive_zones

    for modell in (TrainingSession, PlannedSession, WeeklyPlan):
        db.query(modell).delete()
    db.commit()

    profil = db.query(AthleteProfile).first()
    montag = date.today() - timedelta(days=3)
    plan = WeeklyPlan(user_id=profil.user_id, week_number=1, week_start=montag,
                      week_end=montag + timedelta(days=6), plan_phase=BENCHMARK_PHASE,
                      plan_content={"days": []}, plan_text="")
    db.add(plan); db.commit()
    geplant = PlannedSession(user_id=profil.user_id, plan_id=plan.id, week_number=1,
                             planned_date=montag, discipline="bike",
                             training_type="threshold", duration_min=30)
    db.add(geplant); db.commit()

    watts = []
    for stufe in range(12):
        watts += [120 + stufe * 20] * 2
    db.add(TrainingSession(
        user_id=profil.user_id, session_date=montag, week_number=1,
        discipline="bike", duration_min=24, planned_session_id=geplant.id,
        streams={"watts": watts},
    ))
    db.commit()

    ergebnis = derive_zones(db, days=21, apply=False)
    assert "ftp_watts" not in ergebnis, "kein Wert aus einem Rampenprofil"
    assert "Stufentest" in ergebnis["ftp_hinweis"]
    assert "ftp_uebersprungen" in ergebnis["sources"]


def test_von_hand_eingetragene_ftp_wird_als_solche_gefuehrt(client, db):
    from models import AthleteProfile

    profil = db.query(AthleteProfile).first()
    vorher, quelle_vorher = profil.ftp_watts, profil.ftp_source
    try:
        client.patch("/api/profile", json={"ftp_watts": 264})
        db.expire_all()
        profil = db.query(AthleteProfile).first()
        assert profil.ftp_watts == 264
        assert profil.ftp_source == "manual"
    finally:
        # Das Schema wird nur einmal je Lauf aufgesetzt; ein hier stehen
        # gelassener Wert verfälscht jeden späteren Test, der das Profil liest.
        profil.ftp_watts, profil.ftp_source = vorher, quelle_vorher
        db.commit()
