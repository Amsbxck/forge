from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ChatMessage, AthleteProfile, WeeklyPlan, TrainingSession, HrvMeasurement
from schemas import ChatMessageIn, ChatMessageOut, ChatResponse
from services.claude_service import chat_with_coach
from services.plan_generator import get_current_week
from core.prompt_templates import get_phase, format_sessions, format_hrv, get_week_dates

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatMessageIn, db: Session = Depends(get_db)):
    history_records = (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.asc())
        .limit(20)
        .all()
    )
    history = [{"role": r.role, "content": r.content} for r in history_records]

    profile = db.query(AthleteProfile).first()
    current_week = get_current_week(profile) if profile else 10
    ftp = profile.ftp_watts if profile else 238

    # Letzte 14 Tage Einheiten
    cutoff = date.today() - timedelta(days=14)
    sessions = db.query(TrainingSession).filter(
        TrainingSession.session_date >= cutoff,
        TrainingSession.deleted_at == None,
    ).order_by(TrainingSession.session_date.desc()).all()

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

    # Letzte 7 Tage HRV
    hrv_cutoff = date.today() - timedelta(days=7)
    hrv_records = db.query(HrvMeasurement).filter(
        HrvMeasurement.measured_at >= hrv_cutoff
    ).order_by(HrvMeasurement.measured_at.asc()).all()
    hrv_dicts = [{"measured_at": str(h.measured_at), "rmssd": h.rmssd, "hrv_status": h.hrv_status} for h in hrv_records]

    # Aktueller Plan
    latest_plan = db.query(WeeklyPlan).order_by(WeeklyPlan.generated_at.desc()).first()
    plan_text = latest_plan.plan_text if latest_plan else None

    # Season Context
    from models import SeasonContext
    season_items = db.query(SeasonContext).order_by(SeasonContext.created_at.asc()).all()
    season_text = "\n\n".join(f"=== {i.label} ===\n{i.text}" for i in season_items) if season_items else ""

    context = {
        "week": current_week,
        "phase": get_phase(current_week),
        "ftp": ftp,
        "sessions_summary": format_sessions(sessions_dicts),
        "hrv_summary": format_hrv(hrv_dicts),
        "current_plan": plan_text,
        "season_context": season_text,
    }

    try:
        reply, updated_plan = await chat_with_coach(body.message, history, context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat fehlgeschlagen: {str(e)}")

    # Plan in DB speichern wenn Claude einen erstellt/geändert hat
    if updated_plan and profile:
        target_week = updated_plan.get("week", current_week + 1)
        week_start, week_end = get_week_dates(target_week, profile.plan_start_date)
        plan_text_lines = [f"Wochenplan {target_week} ({week_start} – {week_end})", ""]
        for day in updated_plan.get("days", []):
            plan_text_lines.append(
                f"{day['day']} ({day['date']}): {day['session_type'].upper()} "
                f"{day.get('duration_min', '')}min — {day.get('notes', '')}"
            )
        plan_text_lines.append("")
        plan_text_lines.append(updated_plan.get("coaching_comment", ""))

        db_plan = WeeklyPlan(
            week_number=target_week,
            week_start=week_start,
            week_end=week_end,
            plan_phase=updated_plan.get("phase"),
            plan_content=updated_plan,
            plan_text="\n".join(plan_text_lines),
            adjustments_applied=updated_plan.get("adjustments", []),
        )
        db.add(db_plan)

    db.add(ChatMessage(role="user", content=body.message, context_week=current_week))
    db.add(ChatMessage(role="assistant", content=reply, context_week=current_week))
    db.commit()

    all_records = (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.asc())
        .limit(40)
        .all()
    )
    return ChatResponse(reply=reply, history=all_records)


@router.get("/chat/history", response_model=list[ChatMessageOut])
def get_chat_history(db: Session = Depends(get_db)):
    return (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.asc())
        .limit(40)
        .all()
    )


@router.delete("/chat")
def clear_chat(db: Session = Depends(get_db)):
    db.query(ChatMessage).delete()
    db.commit()
    return {"message": "Chat-Verlauf gelöscht"}
