"""Schwimmen wird extern geplant — und darf das Progressionssignal nicht färben.

Der Athlet schwimmt nach einem Vereins- oder App-Plan. Der Coach setzt nur den
Termin. Also darf er auch nicht aus vergangenen Schwimmeinheiten ableiten, wie
die nächsten aussehen sollen: Er würde gegen einen Plan steuern, den er nicht
kennt — und die Korrektur landete bei Rad und Lauf.
"""

from datetime import date, timedelta

from core.training_types import EXTERN_GEPLANT
from models import PlannedSession, TrainingSession, WeeklyPlan
from services.season_summary import _belastbarkeit, _progression


def _einheit(tag, disziplin, minuten, km=None):
    return TrainingSession(
        session_date=tag, discipline=disziplin, duration_min=minuten, distance_km=km
    )


def test_schwimmen_gilt_als_extern_geplant():
    assert "swim" in EXTERN_GEPLANT


def test_progression_ohne_schwimmen():
    heute = date(2026, 5, 4)
    sessions = [
        _einheit(heute - timedelta(days=3), "run", 95, 18.0),
        _einheit(heute - timedelta(days=4), "swim", 75, 2.8),
        _einheit(heute - timedelta(days=5), "bike", 210, 85.0),
    ]
    reihen = _progression(sessions, heute)
    assert "run" in reihen
    assert "bike" in reihen
    assert "swim" not in reihen


def test_lange_schwimmeinheit_erzeugt_keine_reihe():
    """Auch eine auffällig lange Einheit bleibt draußen.

    Vorher wäre daraus "die lange Schwimmeinheit wächst" geworden — eine
    Auskunft über einen Plan, den der Coach nicht schreibt.
    """
    heute = date(2026, 5, 4)
    reihen = _progression([_einheit(heute - timedelta(days=1), "swim", 120, 4.0)], heute)
    assert reihen == {}


def test_belastbarkeit_zaehlt_schwimmen_nicht(db):
    """Ein 70-Minuten-Vereinstraining auf einem 45-Minuten-Termin ist keine
    Übererfüllung — der Inhalt kam aus dem externen Plan."""
    beginn, heute = date(2026, 4, 1), date(2026, 4, 30)
    plan = WeeklyPlan(
        week_number=15, week_start=date(2026, 4, 6), week_end=date(2026, 4, 12),
        plan_phase="Build", plan_content={},
    )
    db.add(plan)
    db.commit()

    soll = PlannedSession(
        plan_id=plan.id, week_number=15, planned_date=date(2026, 4, 8),
        day_index=2, day_name="Mittwoch", discipline="swim", duration_min=45,
    )
    db.add(soll)
    db.commit()

    ist = TrainingSession(
        session_date=date(2026, 4, 8), discipline="swim", duration_min=70, week_number=15,
        planned_session_id=soll.id,
    )
    db.add(ist)
    db.commit()

    ergebnis = _belastbarkeit(db, beginn, heute)
    assert ergebnis["mehr"] == 0
    assert ergebnis["weniger"] == 0

    db.delete(ist)
    db.delete(soll)
    db.delete(plan)
    db.commit()


def test_prompt_nennt_css_und_schwellenpuls_als_orientierung():
    """Ohne die Werte im Prompt konnte der Coach sie nicht weitergeben —
    und sie sind das Einzige, was er zum Schwimmen beizutragen hat."""
    from core.prompt_templates import build_plan_prompt

    profil = {
        "name": "Amir", "ftp_watts": 238, "max_hr": 212, "z1_hr_max": 138,
        "z2_hr_min": 139, "z2_hr_max": 173, "z3_hr_min": 174, "z3_hr_max": 189,
        "z4_hr_min": 190, "z4_hr_max": 210, "race_date": "2026-08-31",
        "race_goal": "sub 5:30h", "total_weeks": 33,
        "css_pace_s_per_100m": 124.0, "swim_threshold_hr": 158,
    }
    prompt = build_plan_prompt(profil, [], [], week=12, plan_start=date(2025, 12, 22))
    assert "CSS 2:04/100m" in prompt
    assert "Schwellenpuls 158 bpm" in prompt


def test_prompt_erfindet_keine_schwimmwerte():
    from core.prompt_templates import build_plan_prompt

    profil = {
        "name": "Neu", "ftp_watts": 200, "max_hr": 190, "z1_hr_max": 120,
        "z2_hr_min": 121, "z2_hr_max": 150, "z3_hr_min": 151, "z3_hr_max": 165,
        "z4_hr_min": 166, "z4_hr_max": 185, "race_date": "2026-08-31",
        "race_goal": None, "total_weeks": 33,
    }
    prompt = build_plan_prompt(profil, [], [], week=12, plan_start=date(2025, 12, 22))
    assert "CSS unbekannt" in prompt
    assert "Schwellenpuls unbekannt" in prompt


def test_prompt_verbietet_schwimminhalte_und_kennt_freiwasser():
    from core.prompt_templates import build_plan_prompt

    profil = {
        "name": "Amir", "ftp_watts": 238, "max_hr": 212, "z1_hr_max": 138,
        "z2_hr_min": 139, "z2_hr_max": 173, "z3_hr_min": 174, "z3_hr_max": 189,
        "z4_hr_min": 190, "z4_hr_max": 210, "race_date": "2026-08-31",
        "race_goal": None, "total_weeks": 33,
    }
    prompt = build_plan_prompt(profil, [], [], week=12, plan_start=date(2025, 12, 22))
    assert "externen Trainingsplan" in prompt
    assert "Keine Technikübungen" in prompt
    assert "Freiwasser (ab Peak)" in prompt
