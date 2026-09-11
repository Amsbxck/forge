"""Welcher Plan gilt für eine Woche?

Für dieselbe Woche können mehrere weekly_plans-Zeilen existieren: jede
Neugenerierung und jede Planänderung im Chat legt eine neue an. Ohne eine
gemeinsame Auswahlregel liefert jeder Endpoint eine andere Antwort — genau
so kam es dazu, dass der Wochenkalender einen leeren Plan zeigte, obwohl
darunter noch ein vollständiger lag.

Regel: der neueste Plan der Woche, der tatsächlich Tage enthält.
"""

from sqlalchemy.orm import Session

from models import AthleteProfile, WeeklyPlan
from services.plan_generator import get_current_week
from core.deps import get_profile, get_plan_anchor


def pick_plan(query) -> WeeklyPlan | None:
    """Neuester Plan aus einem Query — leere Pläne überdecken keinen vollen."""
    plans = query.order_by(WeeklyPlan.generated_at.desc()).limit(10).all()
    for plan in plans:
        if (plan.plan_content or {}).get("days"):
            return plan
    return plans[0] if plans else None


def active_plan_for_week(db: Session, week_number: int) -> WeeklyPlan | None:
    return pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_number == week_number))


def current_week_number(db: Session) -> int:
    anchor = get_plan_anchor(db)
    return get_current_week(anchor) if anchor else 1


def active_current_plan(db: Session) -> WeeklyPlan | None:
    return active_plan_for_week(db, current_week_number(db))
