"""Lesezugriff auf die normalisierten geplanten Einheiten.

Modul 1 stellt nur Lesen + Backfill bereit. Das Verschieben per Drag & Drop
(PATCH) kommt in Modul 2, sobald das Frontend darauf umgestellt ist.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.training_types import DISCIPLINES, is_valid_training_type, normalize_discipline
from database import get_db
from models import PlannedSession, WeeklyPlan
from schemas import (
    PlannedReplacementIn,
    PlannedSessionOut,
    PlannedSessionPatch,
    PlannedSwapIn,
)
from services.plan_projection import backfill_all, planned_sessions_available, project_plan
from services.plan_selection import active_plan_for_week, current_week_number

router = APIRouter()


def _require_table(db: Session) -> None:
    if not planned_sessions_available(db):
        raise HTTPException(status_code=503, detail="planned_sessions fehlt — Migration 005 nötig")


def _get_or_404(db: Session, session_id: int) -> PlannedSession:
    row = db.query(PlannedSession).filter(PlannedSession.id == session_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Geplante Einheit {session_id} nicht gefunden")
    return row


@router.get("/planned/status")
def planned_status(db: Session = Depends(get_db)):
    """Ist die Projektion aktiv? Zeigt an, ob Migration 005 gelaufen ist."""
    available = planned_sessions_available(db)
    count = db.query(PlannedSession).count() if available else 0
    return {
        "table_exists": available,
        "planned_sessions": count,
        "hint": None if available else "Migration 005 ausführen: alembic upgrade head",
    }


@router.get("/planned/week/{week_number}", response_model=list[PlannedSessionOut])
def planned_for_week(week_number: int, db: Session = Depends(get_db)):
    """Einheiten des *aktiven* Plans dieser Woche.

    Für eine Woche können mehrere Pläne existieren (Neugenerierung, Chat-
    Änderung). Ohne Filter auf den aktiven Plan lieferte der Endpoint die
    Einheiten aller Pläne — bei doppelt generierten Wochen also 14 statt 7.
    """
    _require_table(db)
    plan = active_plan_for_week(db, week_number)
    if plan is None:
        return []
    return (
        db.query(PlannedSession)
        .filter(PlannedSession.plan_id == plan.id)
        .order_by(PlannedSession.planned_date.asc(), PlannedSession.day_index.asc())
        .all()
    )


@router.get("/planned/current", response_model=list[PlannedSessionOut])
def planned_current(db: Session = Depends(get_db)):
    _require_table(db)
    return planned_for_week(current_week_number(db), db)


@router.patch("/planned/{session_id}", response_model=PlannedSessionOut)
def patch_planned(session_id: int, body: PlannedSessionPatch, db: Session = Depends(get_db)):
    """Einzelne geplante Einheit ändern — Termin, Sportart, Typ, Dauer.

    Verschiebt sich das Datum, wird der ursprüngliche Termin in
    moved_from_date festgehalten. Genau das braucht der spätere Ist/Soll-
    Abgleich: sonst würde ein verschobener Schwimmtag gegen den ursprünglich
    geplanten Radtag gematcht.
    """
    _require_table(db)
    row = _get_or_404(db, session_id)

    if body.discipline is not None:
        discipline = normalize_discipline(body.discipline)
        if discipline is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unbekannte Sportart '{body.discipline}' — erlaubt: {', '.join(DISCIPLINES)}",
            )
        row.discipline = discipline
        # Typ muss zur neuen Sportart passen, sonst verwerfen statt Unsinn behalten.
        if not is_valid_training_type(discipline, row.training_type):
            row.training_type = None

    if body.training_type is not None:
        if not is_valid_training_type(row.discipline, body.training_type):
            raise HTTPException(
                status_code=422,
                detail=f"training_type '{body.training_type}' passt nicht zu '{row.discipline}'",
            )
        row.training_type = body.training_type

    if body.planned_date is not None and body.planned_date != row.planned_date:
        if row.moved_from_date is None:
            row.moved_from_date = row.planned_date
        row.planned_date = body.planned_date
        if row.status == "planned":
            row.status = "moved"

    if body.duration_min is not None:
        row.duration_min = body.duration_min
    if body.notes is not None:
        row.notes = body.notes
    if body.status is not None:
        row.status = body.status

    db.commit()
    db.refresh(row)
    return row


@router.post("/planned/{session_id}/replacement", response_model=PlannedSessionOut)
def set_replacement(
    session_id: int, body: PlannedReplacementIn, db: Session = Depends(get_db)
):
    """Statt der geplanten Einheit wurde etwas anderes gemacht.

    Eigener Status statt „ausgelassen": Wer mit Freunden wandern geht, hat
    trainiert. Beides als Ausfall zu führen hieße, den Plan zurückzufahren,
    obwohl Belastung stattgefunden hat — und dem Athleten nebenbei zu
    unterstellen, er habe versagt.

    Leerer Text wird abgewiesen: Ein Ersatz ohne Angabe, wodurch, ist für die
    Planung nichts anderes als ein Ausfall, sähe aber besser aus.
    """
    _require_table(db)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Bitte angeben, was stattdessen gemacht wurde.",
        )

    row = _get_or_404(db, session_id)
    row.status = "replaced"
    row.replacement = text
    row.replacement_min = body.duration_min
    db.commit()
    db.refresh(row)
    return row


@router.delete("/planned/{session_id}/replacement", response_model=PlannedSessionOut)
def clear_replacement(session_id: int, db: Session = Depends(get_db)):
    """Ersatz zurücknehmen — versehentlich eingetragen oder doch nachgeholt."""
    _require_table(db)
    row = _get_or_404(db, session_id)
    if row.status == "replaced":
        # Zurück auf den Ausgangszustand, nicht auf „erledigt": Ob die Einheit
        # doch noch stattfand, weiß der Abgleich mit Strava, nicht dieser Klick.
        row.status = "planned"
    row.replacement = None
    row.replacement_min = None
    db.commit()
    db.refresh(row)
    return row


@router.post("/planned/swap", response_model=list[PlannedSessionOut])
def swap_planned(body: PlannedSwapIn, db: Session = Depends(get_db)):
    """Zwei Einheiten tauschen ihre Termine — ein Drop im Wochenkalender.

    Bewusst ein Endpoint statt zwei PATCH-Calls: der Tausch ist atomar, damit
    bei einem Abbruch nicht zwei Einheiten auf demselben Tag landen.
    """
    _require_table(db)
    if body.a_id == body.b_id:
        raise HTTPException(status_code=422, detail="a_id und b_id sind identisch")

    a = _get_or_404(db, body.a_id)
    b = _get_or_404(db, body.b_id)

    a_date, b_date = a.planned_date, b.planned_date
    if a_date != b_date:
        if a.moved_from_date is None:
            a.moved_from_date = a_date
        if b.moved_from_date is None:
            b.moved_from_date = b_date
        a.planned_date, b.planned_date = b_date, a_date
        a.day_name, b.day_name = b.day_name, a.day_name
        for row in (a, b):
            if row.status == "planned":
                row.status = "moved"

    db.commit()
    db.refresh(a)
    db.refresh(b)
    return [a, b]


@router.post("/planned/classify")
def classify(
    limit: int | None = None,
    only_unclassified: bool = True,
    dry_run: bool = True,
    db: Session = Depends(get_db),
):
    """Ist-Daten klassifizieren und dem Plan zuordnen.

    dry_run ist der Standard — der Lauf zeigt erst, was er setzen würde.
    """
    _require_table(db)
    from services.classification import classify_all

    if not dry_run:
        return classify_all(db, limit=limit, only_unclassified=only_unclassified)

    # Trockenlauf: klassifizieren, aber nichts festschreiben.
    result = classify_all(
        db, limit=limit, only_unclassified=only_unclassified, commit=False
    )
    db.rollback()
    result["dry_run"] = True
    return result


@router.post("/planned/backfill")
def backfill(db: Session = Depends(get_db)):
    """Projiziert bestehende Pläne nachträglich — einmalig nach der Migration."""
    _require_table(db)
    return backfill_all(db)


@router.post("/planned/reproject/{plan_id}")
def reproject(plan_id: int, db: Session = Depends(get_db)):
    """Einen einzelnen Plan neu projizieren (verwirft manuelle Verschiebungen)."""
    _require_table(db)
    plan = db.query(WeeklyPlan).filter(WeeklyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} nicht gefunden")
    written = project_plan(db, plan)
    return {"plan_id": plan_id, "sessions": written}
