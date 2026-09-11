from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pydantic import BaseModel

from database import get_db
from models import TrainingSession, WeeklyPlan
from schemas import TrainingSessionOut, WeeklyPlanOut

router = APIRouter()


@router.get("/history/sessions", response_model=list[TrainingSessionOut])
def list_sessions(
    limit: int = 50,
    week: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(TrainingSession)
    if not include_deleted:
        q = q.filter(TrainingSession.deleted_at == None)
    if week is not None:
        q = q.filter(TrainingSession.week_number == week)
    return q.order_by(TrainingSession.session_date.desc()).limit(limit).all()


@router.get("/history/sessions/{session_id}", response_model=TrainingSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    return s


class ReflectionIn(BaseModel):
    reflection: str | None = None


@router.patch("/history/sessions/{session_id}", response_model=TrainingSessionOut)
def update_reflection(session_id: int, body: ReflectionIn, db: Session = Depends(get_db)):
    """Reflexion zur Einheit speichern.

    Wird beim nächsten Obsidian-Sync in die Note geschrieben, sofern dort
    noch nichts steht — was im Vault getippt wurde, hat Vorrang.
    """
    from datetime import datetime

    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")

    text = (body.reflection or "").strip()
    session.reflection = text or None
    session.reflection_updated_at = datetime.utcnow() if text else None
    db.commit()

    # Sofort in die Note schreiben. Ohne das läge die Reflexion bis zum
    # nächsten Sync nur in der Datenbank — und der läuft für bereits
    # synchronisierte Einheiten nicht mehr an.
    #
    # Auch ohne bestehende Note: `sync_session` legt sie dann an. Vorher
    # verlangte die Bedingung einen Pfad, wodurch eine Reflexion zu einer nie
    # synchronisierten Einheit stillschweigend nur in der Datenbank landete.
    # Ist Obsidian nicht eingerichtet, meldet der Aufruf "disabled" zurück.
    try:
        from services.obsidian.sync import sync_session
        sync_session(db, session)
    except Exception as e:  # pragma: no cover - Speichern darf nie scheitern
        import logging
        logging.getLogger(__name__).warning("Reflexion nicht nach Obsidian übertragen: %s", e)

    db.refresh(session)
    return session


@router.delete("/history/sessions/{session_id}")
def soft_delete_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    s.deleted_at = datetime.utcnow()
    db.commit()
    return {"message": "Einheit gelöscht (wiederherstellbar)"}


@router.delete("/history/sessions/{session_id}/hard")
def hard_delete_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    db.delete(s)
    db.commit()
    return {"message": "Einheit permanent gelöscht"}


@router.post("/history/sessions/{session_id}/restore")
def restore_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    s.deleted_at = None
    db.commit()
    return {"message": "Einheit wiederhergestellt"}


@router.get("/history/plans", response_model=list[WeeklyPlanOut])
def list_plans(db: Session = Depends(get_db)):
    return db.query(WeeklyPlan).order_by(WeeklyPlan.week_number.desc()).all()
