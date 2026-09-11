"""Krank- und Gesundmeldung.

Der Athlet meldet den Zustand, die Planung zieht die Konsequenzen — nicht
umgekehrt. Deshalb hält dieser Router nur den Zustand fest und stößt die
Neuplanung an; die Regeln stehen in `services/health.py`.
"""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.deps import get_current_user
from database import get_db
from models import HealthEvent, User
from services import health as health_service

logger = logging.getLogger(__name__)
router = APIRouter()


class IllnessIn(BaseModel):
    kind: str = Field(default="illness", description="illness | injury | other")
    severity: str = Field(default="mild", description="mild | moderate | severe")
    fever: bool = False
    start_date: date | None = None
    note: str | None = None
    # Standardmäßig wird der Wochenplan sofort neu erstellt — genau dafür
    # meldet man sich krank. Wer das nicht will, schaltet es hier ab.
    adjust_plan: bool = True


class RecoveredIn(BaseModel):
    end_date: date | None = None
    note: str | None = None
    adjust_plan: bool = True


def _validate(kind: str, severity: str) -> None:
    if kind not in health_service.KINDS:
        raise HTTPException(status_code=422, detail=f"Unbekannte Art {kind!r}")
    if severity not in health_service.SEVERITIES:
        raise HTTPException(status_code=422, detail=f"Unbekannter Schweregrad {severity!r}")


async def _regenerate(user_id: int | None, reason: str) -> None:
    """Wochenplan neu erstellen. Darf die Meldung nie mitreißen.

    Die Generierung legt eine neue Zeile an und überschreibt nichts — der
    bisherige Plan bleibt als Verlauf erhalten.

    Der Mandantenkontext muss ausdrücklich gesetzt werden: Eine
    Hintergrundaufgabe läuft, nachdem die Anfrage beendet ist, und die
    Middleware hat ihn dann bereits zurückgenommen. Ohne `acting_as` findet
    die Generierung kein Profil und bricht still ab — genau das ist hier
    passiert, weshalb die automatische Neuplanung nie lief.
    """
    from core.tenancy import acting_as
    from database import SessionLocal
    from services.plan_generator import generate_and_save_plan

    if user_id is None:
        logger.warning("Neuplanung ohne Nutzerbezug angefordert — übersprungen")
        return

    db = SessionLocal()
    try:
        with acting_as(user_id):
            await generate_and_save_plan(db, special_requests=reason)
        logger.info("Plan nach Gesundheitsmeldung neu erstellt (Nutzer %s)", user_id)
    except Exception as e:
        logger.warning("Neuplanung nach Gesundheitsmeldung fehlgeschlagen: %s", e)
    finally:
        db.close()


@router.get("/health/status")
def status(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Zustand und die daraus folgenden Vorgaben."""
    return health_service.guidance(db, user).to_dict()


@router.get("/health/events")
def list_events(
    days: int = 365,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    events = health_service.recent_events(db, user, days=days)
    return [health_service.event_to_dict(e) for e in events]


@router.post("/health/illness")
async def report_illness(
    body: IllnessIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Krank oder verletzt melden."""
    _validate(body.kind, body.severity)

    beginn = body.start_date or date.today()
    if beginn > date.today():
        raise HTTPException(status_code=422, detail="Beginn kann nicht in der Zukunft liegen")

    # Eine offene Meldung wird aktualisiert statt verdoppelt: wer erst
    # "Schnupfen" meldet und zwei Tage später Fieber bekommt, meldet nicht
    # eine zweite Krankheit, sondern eine Verschlechterung derselben.
    event = health_service.open_event(db, user)
    if event is not None:
        event.kind = body.kind
        event.severity = body.severity
        event.fever = body.fever and body.kind == "illness"
        event.start_date = min(event.start_date, beginn)
        if body.note:
            event.note = body.note
        neu = False
    else:
        event = HealthEvent(
            user_id=user.id if user else None,
            kind=body.kind,
            severity=body.severity,
            fever=body.fever and body.kind == "illness",
            start_date=beginn,
            note=body.note,
        )
        db.add(event)
        neu = True

    db.commit()
    db.refresh(event)

    guidance = health_service.guidance(db, user)
    if body.adjust_plan:
        art = "verletzt" if body.kind == "injury" else "krank"
        background.add_task(
            _regenerate,
            user.id if user else None,
            f"Der Athlet hat sich {art} gemeldet "
            f"({health_service.severity_label(body.kind, body.severity)}"
            f"{', mit Fieber' if body.fever else ''}). Plane die laufende Woche entsprechend um.",
        )

    return {
        "created": neu,
        "event": health_service.event_to_dict(event),
        "guidance": guidance.to_dict(),
        "plan_wird_angepasst": body.adjust_plan,
    }


@router.post("/health/recovered")
async def report_recovered(
    body: RecoveredIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Wieder gesund. Ab hier zählt der Wiedereinstieg."""
    event = health_service.open_event(db, user)
    if event is None:
        raise HTTPException(status_code=404, detail="Keine offene Krankmeldung")

    ende = body.end_date or date.today()
    if ende < event.start_date:
        raise HTTPException(status_code=422, detail="Ende liegt vor dem Beginn")
    if ende > date.today():
        raise HTTPException(status_code=422, detail="Ende kann nicht in der Zukunft liegen")

    event.end_date = ende
    if body.note:
        event.note = f"{event.note}\n{body.note}" if event.note else body.note
    db.commit()
    db.refresh(event)

    guidance = health_service.guidance(db, user)
    if body.adjust_plan:
        background.add_task(
            _regenerate,
            user.id if user else None,
            f"Der Athlet ist nach {event.days} Tagen Ausfall wieder gesund. "
            "Plane den Wiedereinstieg für die laufende Woche.",
        )

    return {
        "event": health_service.event_to_dict(event),
        "guidance": guidance.to_dict(),
        "plan_wird_angepasst": body.adjust_plan,
    }


@router.delete("/health/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Fehlmeldung zurücknehmen."""
    query = db.query(HealthEvent).filter(HealthEvent.id == event_id)
    if user is not None:
        query = query.filter(HealthEvent.user_id == user.id)
    event = query.first()
    if event is None:
        raise HTTPException(status_code=404, detail="Meldung nicht gefunden")
    db.delete(event)
    db.commit()
    return {"message": "gelöscht"}
