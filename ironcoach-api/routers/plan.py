import re
from services.api_budget import BudgetExhausted, NoBillingContext
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from models import AthleteProfile, WeeklyPlan
from schemas import WeeklyPlanOut
from services.plan_generator import generate_and_save_plan, get_current_week
from services.plan_selection import pick_plan as _pick_plan


def _safe_filename(name: str) -> str:
    name = name.replace('—', '-').replace('–', '-')
    return re.sub(r'[^\x00-\x7f]', '', name).replace(' ', '_')
from services.pdf_generator import generate_plan_pdf
from core.deps import get_profile, get_plan_anchor

router = APIRouter()


@router.get("/plan/generate", response_model=WeeklyPlanOut)
async def generate_plan(
    requests: str = Query(default="", description="Besondere Wünsche oder Hinweise"),
    db: Session = Depends(get_db),
):
    try:
        plan = await generate_and_save_plan(db, special_requests=requests)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NoBillingContext:
        # Kein Serverfehler im üblichen Sinn: Die Anfrage war in Ordnung, nur
        # ließ sich kein Konto zuordnen. Als 500 wäre das im Log von echten
        # Abstürzen nicht zu unterscheiden.
        raise HTTPException(
            status_code=503,
            detail="Anfrage konnte keinem Konto zugeordnet werden — bitte neu anmelden.",
        )
    except BudgetExhausted:
        # Weiterreichen an den Handler in main.py: ein aufgebrauchtes Guthaben
        # ist kein Serverfehler, und als 500 könnte die Oberfläche es nicht
        # von einem echten Ausfall unterscheiden.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan-Generierung fehlgeschlagen: {str(e)}")


@router.get("/plan/current", response_model=WeeklyPlanOut)
def get_current_plan(db: Session = Depends(get_db)):
    anchor = get_plan_anchor(db)
    current_week = get_current_week(anchor) if anchor else 1
    plan = _pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_number == current_week))
    if not plan:
        raise HTTPException(status_code=404, detail="Kein Plan für diese Woche — erst /api/plan/generate aufrufen")
    return plan


@router.get("/plan/current/pdf")
def download_current_plan_pdf(db: Session = Depends(get_db)):
    plan = _pick_plan(db.query(WeeklyPlan))
    if not plan:
        raise HTTPException(status_code=404, detail="Kein Plan vorhanden")
    pdf_bytes = generate_plan_pdf({"plan_content": plan.plan_content})
    filename = _safe_filename(f"IronCoach_Woche_{plan.week_number}_{plan.plan_phase or 'Plan'}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/plan/{week_number}/pdf")
def download_plan_pdf(week_number: int, db: Session = Depends(get_db)):
    plan = _pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_number == week_number))
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für Woche {week_number}")
    pdf_bytes = generate_plan_pdf({"plan_content": plan.plan_content})
    filename = _safe_filename(f"IronCoach_Woche_{week_number}_{plan.plan_phase or 'Plan'}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/plan/{week_number}", response_model=WeeklyPlanOut)
def get_plan_by_week(week_number: int, db: Session = Depends(get_db)):
    plan = _pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_number == week_number))
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für Woche {week_number}")
    return plan
