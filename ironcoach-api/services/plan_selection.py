"""Welcher Plan gilt für eine Woche?

Für dieselbe Woche können mehrere weekly_plans-Zeilen existieren: jede
Neugenerierung und jede Planänderung im Chat legt eine neue an. Ohne eine
gemeinsame Auswahlregel liefert jeder Endpoint eine andere Antwort — genau
so kam es dazu, dass der Wochenkalender einen leeren Plan zeigte, obwohl
darunter noch ein vollständiger lag.

Regel: der neueste Plan der **Kalenderwoche** (über ihren Montag), der
tatsächlich Tage enthält.

Bis hierher wählten mehrere Stellen über die Wochennummer. Die ist aber
relativ zum Anker (Saisonziel oder Profil) und verschiebt sich mit jedem
Zielwechsel und jeder neuen Saison — dieselbe Nummer meint dann eine andere
Kalenderwoche. Plankachel, Kalender, PDF, Chat und Zuordnung zeigten so nach
einem Zielwechsel verschiedene Pläne. Die Nummer bleibt deshalb Beschriftung;
gewählt wird nur noch über den Montag.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import WeeklyPlan
from core.deps import get_plan_anchor
from core.wochen import kalenderwoche


def pick_plan(query) -> WeeklyPlan | None:
    """Neuester Plan aus einem Query — leere Pläne überdecken keinen vollen."""
    plans = query.order_by(WeeklyPlan.generated_at.desc(), WeeklyPlan.id.desc()).limit(10).all()
    for plan in plans:
        if (plan.plan_content or {}).get("days"):
            return plan
    return plans[0] if plans else None


def plan_der_woche(db: Session, tag: date | None = None) -> WeeklyPlan | None:
    """Aktiver Plan der Kalenderwoche, in der `tag` liegt (ohne Angabe: heute)."""
    montag, _ = kalenderwoche(tag)
    return pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_start == montag))


def montag_fuer_wochennummer(db: Session, week_number: int) -> date | None:
    """Der Montag, den die Wochennummer **unter dem heutigen Anker** meint.

    Für die Adressen, die noch eine Nummer tragen (`/plan/{n}`,
    `/planned/week/{n}`, `/obsidian/sync-plan/{n}`). Ohne Anker gibt es keinen
    Bezugspunkt, dann `None`.
    """
    anchor = get_plan_anchor(db)
    start = getattr(anchor, "plan_start_date", None)
    if start is None:
        return None
    start = start - timedelta(days=start.weekday())
    return start + timedelta(weeks=week_number - 1)


def active_plan_for_week(db: Session, week_number: int) -> WeeklyPlan | None:
    """Plan zu einer Wochennummer — aufgelöst über den Montag, siehe oben."""
    montag = montag_fuer_wochennummer(db, week_number)
    if montag is None:
        return None
    return plan_der_woche(db, montag)


def current_week_number(db: Session) -> int:
    from services.plan_generator import get_current_week

    anchor = get_plan_anchor(db)
    return get_current_week(anchor) if anchor else 1


def active_current_plan(db: Session) -> WeeklyPlan | None:
    return plan_der_woche(db)
