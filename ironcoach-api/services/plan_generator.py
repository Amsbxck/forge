from datetime import date, timedelta
from sqlalchemy.orm import Session
from models import AthleteProfile, TrainingSession, HrvMeasurement, WeeklyPlan
from services.claude_service import generate_weekly_plan
from core.prompt_templates import get_phase, get_week_dates


def get_current_week(profile: AthleteProfile) -> int:
    today = date.today()
    delta = (today - profile.plan_start_date).days
    return max(1, min(33, delta // 7 + 1))


def build_athlete_dict(profile: AthleteProfile) -> dict:
    return {
        "ftp_watts": profile.ftp_watts,
        "max_hr": profile.max_hr,
        "z1_hr_max": profile.z1_hr_max,
        "z2_hr_min": profile.z2_hr_min,
        "z2_hr_max": profile.z2_hr_max,
        "z3_hr_min": profile.z3_hr_min,
        "z3_hr_max": profile.z3_hr_max,
        "z4_hr_min": profile.z4_hr_min,
        "z4_hr_max": profile.z4_hr_max,
        "race_date": str(profile.race_date),
        "race_goal": profile.race_goal,
    }


async def generate_and_save_plan(
    db: Session,
    special_requests: str = "",
) -> WeeklyPlan:
    profile = db.query(AthleteProfile).first()
    if not profile:
        raise ValueError("Kein Athletenprofil gefunden")

    current_week = get_current_week(profile)

    cutoff = date.today() - timedelta(days=14)
    sessions = db.query(TrainingSession).filter(
        TrainingSession.session_date >= cutoff
    ).order_by(TrainingSession.session_date.desc()).all()

    hrv_cutoff = date.today() - timedelta(days=7)
    hrv_records = db.query(HrvMeasurement).filter(
        HrvMeasurement.measured_at >= hrv_cutoff
    ).order_by(HrvMeasurement.measured_at.asc()).all()

    sessions_dicts = [
        {
            "session_date": str(s.session_date),
            "discipline": s.discipline,
            "duration_min": s.duration_min,
            "distance_km": s.distance_km,
            "avg_hr": s.avg_hr,
            "avg_watts": s.avg_watts,
            "normalized_power": s.normalized_power,
            "tss": s.tss,
            "hr_zones": s.hr_zones,
        }
        for s in sessions
    ]

    hrv_dicts = [
        {
            "measured_at": str(h.measured_at),
            "rmssd": h.rmssd,
            "hrv_status": h.hrv_status,
        }
        for h in hrv_records
    ]

    from models import SeasonContext
    season_items = db.query(SeasonContext).order_by(SeasonContext.created_at.asc()).all()
    season_context_text = ""
    if season_items:
        parts = [f"=== {item.label} ===\n{item.text}" for item in season_items]
        season_context_text = "\n\n".join(parts)

    plan_content = await generate_weekly_plan(
        athlete_profile=build_athlete_dict(profile),
        last_sessions=sessions_dicts,
        hrv_data=hrv_dicts,
        week_number=current_week,
        special_requests=special_requests,
        plan_start=profile.plan_start_date,
        season_context=season_context_text,
    )

    target_week = current_week + 1
    week_start, week_end = get_week_dates(target_week, profile.plan_start_date)

    plan_text_lines = [f"Wochenplan {target_week} ({week_start} – {week_end})", ""]
    for day in plan_content.get("days", []):
        plan_text_lines.append(
            f"{day['day']} ({day['date']}): {day['session_type'].upper()} "
            f"{day.get('duration_min', '')}min — {day.get('notes', '')}"
        )
    plan_text_lines.append("")
    plan_text_lines.append(plan_content.get("coaching_comment", ""))

    from core.prompt_templates import build_plan_prompt
    from datetime import date as _date

    prompt_used = build_plan_prompt(
        athlete_profile=build_athlete_dict(profile),
        sessions=sessions_dicts,
        hrv=hrv_dicts,
        week=current_week,
        requests=special_requests,
        plan_start=profile.plan_start_date,
    )

    db_plan = WeeklyPlan(
        week_number=target_week,
        week_start=week_start,
        week_end=week_end,
        plan_phase=plan_content.get("phase"),
        plan_content=plan_content,
        plan_text="\n".join(plan_text_lines),
        claude_prompt=prompt_used,
        adjustments_applied=plan_content.get("adjustments", []),
    )
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan
