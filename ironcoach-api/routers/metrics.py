from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import AthleteProfile, TrainingSession, HrvMeasurement
from schemas import WeekMetrics, TrendPoint
from services.plan_generator import get_current_week

router = APIRouter()


@router.get("/metrics/week", response_model=WeekMetrics)
def week_metrics(db: Session = Depends(get_db)):
    profile = db.query(AthleteProfile).first()
    current_week = get_current_week(profile) if profile else 1

    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.week_number == current_week)
        .filter(TrainingSession.deleted_at == None)
        .all()
    )

    total_tss = sum((s.tss or 0) for s in sessions)
    total_duration = sum((s.duration_min or 0) for s in sessions)
    disciplines: dict[str, int] = {}
    for s in sessions:
        disciplines[s.discipline] = disciplines.get(s.discipline, 0) + 1

    hr_values = [s.avg_hr for s in sessions if s.avg_hr]
    avg_hr = round(sum(hr_values) / len(hr_values)) if hr_values else None

    hr_zones_combined: dict[str, list] = {}
    for s in sessions:
        if s.hr_zones:
            for k, v in s.hr_zones.items():
                hr_zones_combined.setdefault(k, []).append(v)
    hr_zones_avg = (
        {k: round(sum(v) / len(v), 1) for k, v in hr_zones_combined.items()}
        if hr_zones_combined
        else None
    )

    latest_hrv = (
        db.query(HrvMeasurement)
        .order_by(HrvMeasurement.measured_at.desc())
        .first()
    )

    return WeekMetrics(
        week_number=current_week,
        total_tss=round(total_tss, 1),
        sessions_count=len(sessions),
        total_duration_min=total_duration,
        disciplines=disciplines,
        avg_hr=avg_hr,
        hr_zones_avg=hr_zones_avg,
        hrv_latest=latest_hrv.rmssd if latest_hrv else None,
        hrv_status=latest_hrv.hrv_status if latest_hrv else None,
    )


@router.get("/metrics/trends", response_model=list[TrendPoint])
def trends(weeks: int = 4, db: Session = Depends(get_db)):
    profile = db.query(AthleteProfile).first()
    current_week = get_current_week(profile) if profile else 1

    result = []
    for w in range(max(1, current_week - weeks + 1), current_week + 1):
        sessions = db.query(TrainingSession).filter(TrainingSession.week_number == w).all()
        total_tss = sum((s.tss or 0) for s in sessions)

        if profile:
            from core.prompt_templates import get_week_dates
            week_start, _ = get_week_dates(w, profile.plan_start_date)
        else:
            week_start = date.today()

        result.append(
            TrendPoint(
                week_number=w,
                week_start=week_start,
                total_tss=round(total_tss, 1),
                sessions_count=len(sessions),
            )
        )
    return result


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = db.query(AthleteProfile).first()
    if not profile:
        return {}
    from schemas import AthleteProfileOut
    out = AthleteProfileOut.model_validate(profile)
    out.current_week = get_current_week(profile)
    return out


@router.patch("/profile")
def update_profile(data: dict, db: Session = Depends(get_db)):
    profile = db.query(AthleteProfile).first()
    if not profile:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")
    allowed = {"ftp_watts", "max_hr", "name", "race_goal"}
    for key, value in data.items():
        if key in allowed:
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    from schemas import AthleteProfileOut
    out = AthleteProfileOut.model_validate(profile)
    out.current_week = get_current_week(profile)
    return out
