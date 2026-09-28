"""Die FTP wird automatisch übernommen — aber nur in einer Testwoche.

Zwei Anforderungen, die zusammengehören:

* Ein sauberer 20-Minuten-Test soll ins Profil wandern, ohne Abtippen. Dafür ist
  die Testwoche da, und sie kommt alle drei Monate.
* Ausserhalb einer Testwoche darf nichts geschrieben werden. Genau so kamen
  einmal 175 W statt 264 ins Profil: aus den stärksten zwanzig Minuten einer
  327-minütigen Grundlagenausfahrt, Monate vor dem Aufbau, nach einem ganz
  normalen Strava-Import. Der Weg dorthin war `maybe_autoderive`, dessen
  Wochenschranke (`> 2`) seit der vorzeichenbehafteten Zählung wirkungslos war:
  Woche -6 ist auch "nicht grösser als 2".
"""

import inspect
from datetime import date, timedelta

import pytest

import services.benchmark as benchmark
from models import AthleteProfile, PlannedSession, TrainingSession, User, WeeklyPlan
from services.benchmark import BENCHMARK_PHASE, derive_zones, ist_benchmark_woche

MONTAG = date.today() - timedelta(days=date.today().weekday())


def _woche(db, phase, start=MONTAG):
    nutzer = db.query(User).first()
    plan = WeeklyPlan(user_id=nutzer.id, week_number=1, week_start=start,
                      week_end=start + timedelta(days=6), plan_phase=phase,
                      plan_content={"days": []}, plan_text="")
    db.add(plan); db.commit()
    return plan


def _test_einheit(db, plan, watt=278):
    """Ein sauberer 20-Minuten-Test: gleichmässig, Puls an der Schwelle."""
    nutzer = db.query(User).first()
    geplant = PlannedSession(user_id=nutzer.id, plan_id=plan.id, week_number=1,
                             planned_date=plan.week_start, discipline="bike",
                             training_type="threshold", duration_min=75)
    db.add(geplant); db.commit()
    # 75 Minuten bei 10-Sekunden-Abtastung; der Test liegt ab Minute 18.
    werte = [120] * 108 + [watt] * 120 + [120] * 222
    puls = [130] * 108 + [186] * 120 + [130] * 222
    s = TrainingSession(
        user_id=nutzer.id, session_date=plan.week_start, week_number=1,
        discipline="bike", duration_min=75, planned_session_id=geplant.id,
        streams={"watts": werte, "hr": puls},
    )
    db.add(s); db.commit()
    return s


@pytest.fixture(autouse=True)
def sauber(db):
    for modell in (TrainingSession, PlannedSession, WeeklyPlan):
        db.query(modell).delete()
    db.commit()
    profil = db.query(AthleteProfile).first()
    # Vorher merken und danach zurücksetzen: Das Profil ist eine gemeinsame
    # Vorrichtung. Ohne das Zurücksetzen scheiterte test_upload, das die
    # Vorgabewerte erwartet — je nach Reihenfolge der Tests.
    vorher = (profil.ftp_watts, profil.ftp_source, profil.threshold_hr)
    profil.ftp_watts, profil.ftp_source = 264, "manual"
    profil.threshold_hr = 188
    db.commit()
    yield
    for modell in (TrainingSession, PlannedSession, WeeklyPlan):
        db.query(modell).delete()
    profil = db.query(AthleteProfile).first()
    profil.ftp_watts, profil.ftp_source, profil.threshold_hr = vorher
    db.commit()


# --- Die Schranke ------------------------------------------------------------

def test_erkennt_die_testwoche(db):
    _woche(db, BENCHMARK_PHASE)
    assert ist_benchmark_woche(db) is True


def test_erkennt_eine_normale_woche(db):
    _woche(db, "Build")
    assert ist_benchmark_woche(db) is False


def test_ohne_plan_keine_testwoche(db):
    assert ist_benchmark_woche(db) is False


# --- Übernehmen --------------------------------------------------------------

def test_in_der_testwoche_wird_geschrieben(db):
    plan = _woche(db, BENCHMARK_PHASE)
    _test_einheit(db, plan, watt=278)

    ergebnis = derive_zones(db, days=21, apply=True)
    assert "ftp_watts" in (ergebnis.get("applied") or []), ergebnis

    profil = db.query(AthleteProfile).first()
    assert profil.ftp_watts == round(278 * benchmark.FTP_FACTOR)
    assert profil.ftp_source == "benchmark"


def test_ausserhalb_der_testwoche_nur_ein_hinweis(db):
    """Die Einheit stammt aus einer Testwoche, die laufende ist keine.

    `_benchmark_sessions` nimmt Tests der letzten drei Wochen, damit ein
    Nachtrag nicht verfällt — geschrieben wird trotzdem nicht.
    """
    vorwoche = MONTAG - timedelta(days=7)
    plan = _woche(db, BENCHMARK_PHASE, start=vorwoche)
    _test_einheit(db, plan, watt=278)
    _woche(db, "Build")  # die laufende Woche

    ergebnis = derive_zones(db, days=21, apply=True)
    assert "ftp_watts" not in (ergebnis.get("applied") or [])
    assert "nur in einer Testwoche" in ergebnis["ftp_hinweis"]
    assert ergebnis["ftp_vorschlag"] == round(278 * benchmark.FTP_FACTOR)

    profil = db.query(AthleteProfile).first()
    assert profil.ftp_watts == 264, "unangetastet"


def test_die_pruefsteine_gelten_auch_in_der_testwoche(db):
    """Eine Grundlagenausfahrt bleibt eine Grundlagenausfahrt, auch in der
    Testwoche — genau das war Amirs Fall."""
    plan = _woche(db, BENCHMARK_PHASE)
    nutzer = db.query(User).first()
    geplant = PlannedSession(user_id=nutzer.id, plan_id=plan.id, week_number=1,
                             planned_date=plan.week_start, discipline="bike",
                             training_type="z2_endurance", duration_min=327)
    db.add(geplant); db.commit()
    # 327 Minuten, das stärkste Fenster spät und bei niedrigem Puls.
    werte = [120] * 1386 + [184] * 120 + [120] * 456
    puls = [130] * 1386 + [166] * 120 + [130] * 456
    db.add(TrainingSession(
        user_id=nutzer.id, session_date=plan.week_start, week_number=1,
        discipline="bike", duration_min=327, planned_session_id=geplant.id,
        streams={"watts": werte, "hr": puls},
    ))
    db.commit()

    ergebnis = derive_zones(db, days=21, apply=True)
    assert "ftp_watts" not in (ergebnis.get("applied") or [])
    assert "ftp_vorschlag" not in ergebnis
    assert "327 Minuten" in ergebnis["ftp_hinweis"]

    profil = db.query(AthleteProfile).first()
    assert profil.ftp_watts == 264


# --- Die Automatik nach dem Import -------------------------------------------

def test_automatik_laeuft_in_der_testwoche_und_sonst_nur_am_aufbaubeginn():
    """Die alte Schranke darf nicht mehr ausgeführt werden.

    Kommentare werden übersprungen: Die alte Bedingung steht dort absichtlich
    als Erklärung, und ein Test, der darüber stolpert, prüft den Text statt das
    Verhalten.
    """
    zeilen = [
        z.split("#")[0] for z in inspect.getsource(benchmark.maybe_autoderive).split("\n")
        if not z.strip().startswith("#")
    ]
    code = "\n".join(zeilen)
    assert "ist_benchmark_woche(db)" in code
    assert "1 <= get_current_week(anchor) <= 2" in code
    assert "get_current_week(anchor) > 2" not in code
