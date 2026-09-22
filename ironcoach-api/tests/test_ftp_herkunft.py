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

from services.benchmark import MAX_ANSTIEG_IM_TEST, SCHWELLEN_FAKTOR
from services.segments import best_effort_power


class _Einheit:
    def __init__(self, watts, duration_min):
        self.streams = {"watts": watts}
        self.duration_min = duration_min


def test_gleichmaessiger_test_gilt_als_gleichmaessig():
    # 20 Minuten um 250 W, leichte Schwankung wie auf der Strasse.
    watts = [10] * 10 + [245, 255, 250, 248, 252] * 4 + [10] * 10
    ergebnis = best_effort_power(_Einheit(watts, 40), seconds=1200)

    assert ergebnis["avg_watts"] == 250
    assert ergebnis["anstieg"] <= MAX_ANSTIEG_IM_TEST


def test_negativsplit_bleibt_unter_der_grenze():
    """Wer hinten anzieht, soll nicht als Stufentest gelten."""
    watts = [10] * 5 + [240] * 10 + [250] * 5 + [262] * 5 + [10] * 5
    ergebnis = best_effort_power(_Einheit(watts, 30), seconds=1200)
    assert 1.0 < ergebnis["anstieg"] <= MAX_ANSTIEG_IM_TEST


def test_rampe_wird_erkannt():
    # Stufentest: alle 2 Minuten 20 W mehr, bis zum Abbruch.
    watts = []
    for stufe in range(12):
        watts += [120 + stufe * 20] * 2
    ergebnis = best_effort_power(_Einheit(watts, 24), seconds=1200)
    assert ergebnis["anstieg"] > MAX_ANSTIEG_IM_TEST


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
