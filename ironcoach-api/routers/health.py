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
    # Wo es weh tut. Nur bei Verletzungen sinnvoll; entscheidet, welche
    # Disziplin geschont wird und welche den Umfang weiter trägt.
    body_part: str | None = None
    start_date: date | None = None
    note: str | None = None
    # Standardmäßig wird der Wochenplan sofort neu erstellt — genau dafür
    # meldet man sich krank. Wer das nicht will, schaltet es hier ab.
    adjust_plan: bool = True


class RecoveredIn(BaseModel):
    end_date: date | None = None
    note: str | None = None
    adjust_plan: bool = True


def _validate(kind: str, severity: str, body_part: str | None = None) -> None:
    if kind not in health_service.KINDS:
        raise HTTPException(status_code=422, detail=f"Unbekannte Art {kind!r}")
    if severity not in health_service.SEVERITIES:
        raise HTTPException(status_code=422, detail=f"Unbekannter Schweregrad {severity!r}")
    # Eine unbekannte Stelle wird abgewiesen statt stillschweigend verworfen:
    # Sonst meldet jemand eine Verletzung, die Oberfläche bestätigt sie, und
    # der Plan ändert nichts — weil die Vorgabe zu der Stelle nie gefunden wurde.
    if body_part and body_part.lower() not in health_service.KOERPERSTELLEN:
        raise HTTPException(
            status_code=422,
            detail=f"Unbekannte Körperstelle {body_part!r}. "
                   f"Erlaubt: {', '.join(sorted(health_service.KOERPERSTELLEN))}",
        )


# Stand der letzten Neuplanung je Nutzer. Die Neuplanung läuft im Hintergrund
# (sie dauert eine Minute und länger); die Antwort auf die Meldung kann ihr
# Ergebnis also nicht enthalten. Vorher behauptete sie trotzdem
# „plan_wird_angepasst: true", auch wenn das Budget erschöpft war oder das
# Modell scheiterte — der Fehler stand nur im Log. Jetzt fragt die Oberfläche
# hier nach. Im Speicher genügt: Nach einem Neustart ist die Neuplanung
# ohnehin abgebrochen, und „unbekannt" ist dann die ehrliche Auskunft.
_NEUPLANUNG: dict[int, dict] = {}


def _ziel_montag(heute: date | None = None) -> date:
    """Die Woche, die nach einer Meldung neu geplant wird.

    Sonntags die kommende: Die laufende hat dann nur noch diesen einen Tag,
    und vorher wurden sechs vergangene Tage neu geplant.
    """
    from datetime import timedelta
    from core.wochen import montag_von

    heute = heute or date.today()
    montag = montag_von(heute)
    return montag + timedelta(days=7) if heute.weekday() == 6 else montag


async def _regenerate(user_id: int | None, reason: str, montag: date | None = None) -> None:
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
    from services.api_budget import BudgetExhausted
    from services.plan_generator import generate_and_save_plan

    if user_id is None:
        logger.warning("Neuplanung ohne Nutzerbezug angefordert — übersprungen")
        return

    montag = montag or _ziel_montag()
    _NEUPLANUNG[user_id] = {"status": "laeuft", "montag": str(montag), "detail": None}
    db = SessionLocal()
    try:
        with acting_as(user_id):
            plan = await generate_and_save_plan(db, special_requests=reason, montag=montag)
        _NEUPLANUNG[user_id] = {
            "status": "fertig", "montag": str(montag), "plan_id": plan.id, "detail": None,
        }
        logger.info("Plan nach Gesundheitsmeldung neu erstellt (Nutzer %s)", user_id)
    except BudgetExhausted:
        _NEUPLANUNG[user_id] = {
            "status": "fehlgeschlagen", "montag": str(montag),
            "detail": "Das Guthaben für Planerstellungen ist aufgebraucht — "
                      "der Plan wurde nicht angepasst.",
        }
    except Exception as e:
        logger.warning("Neuplanung nach Gesundheitsmeldung fehlgeschlagen: %s", e)
        _NEUPLANUNG[user_id] = {
            "status": "fehlgeschlagen", "montag": str(montag),
            "detail": "Der Plan konnte nicht automatisch angepasst werden. "
                      "Erstelle die Woche im Planfenster neu.",
        }
    finally:
        db.close()


@router.get("/health/neuplanung")
def neuplanung(user: User | None = Depends(get_current_user)):
    """Wie es um die Neuplanung nach der letzten Meldung steht."""
    if user is None:
        return {"status": "unbekannt"}
    return _NEUPLANUNG.get(user.id, {"status": "unbekannt"})


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
    _validate(body.kind, body.severity, body.body_part)

    beginn = body.start_date or date.today()
    if beginn > date.today():
        raise HTTPException(status_code=422, detail="Beginn kann nicht in der Zukunft liegen")

    # Eine offene Meldung wird aktualisiert statt verdoppelt: wer erst
    # "Schnupfen" meldet und zwei Tage später Fieber bekommt, meldet nicht
    # eine zweite Krankheit, sondern eine Verschlechterung derselben.
    event = health_service.open_event(db, user)
    if event is not None and event.kind != body.kind:
        # Eine andere **Art** ist eine neue Episode, keine Verschlechterung:
        # Wer verletzt war und jetzt krank wird, hat zwei Ereignisse. Vorher
        # wurde die alte Episode überschrieben, samt Art und Körperstelle — die
        # Verletzung verschwand aus dem Verlauf.
        from datetime import timedelta

        event.end_date = max(event.start_date, beginn - timedelta(days=1))
        db.flush()
        event = None
    if event is not None:
        event.kind = body.kind
        event.severity = body.severity
        event.fever = body.fever and body.kind == "illness"
        # Nur bei einer Verletzung: Wer von "Verletzung Schienbein" auf
        # "Erkältung" wechselt, soll die Stelle nicht mitschleppen.
        event.body_part = body.body_part.lower() if (body.body_part and body.kind == "injury") else None
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
            body_part=body.body_part.lower() if (body.body_part and body.kind == "injury") else None,
            start_date=beginn,
            note=body.note,
        )
        db.add(event)
        neu = True

    db.commit()
    db.refresh(event)

    guidance = health_service.guidance(db, user)
    angestossen = bool(body.adjust_plan and user is not None)
    if angestossen:
        art = "verletzt" if body.kind == "injury" else "krank"
        montag = _ziel_montag()
        _NEUPLANUNG[user.id] = {"status": "laeuft", "montag": str(montag), "detail": None}
        background.add_task(
            _regenerate,
            user.id,
            # Aus dem gespeicherten Stand, nicht aus der Anfrage: Fieber wird
            # nur bei einer Krankheit gespeichert, der Text sagte es auch bei
            # einer Verletzung.
            f"Der Athlet hat sich {art} gemeldet "
            f"({health_service.severity_label(event.kind, event.severity)}"
            f"{', mit Fieber' if event.fever else ''}). Plane die Woche entsprechend um.",
            montag,
        )

    return {
        "created": neu,
        "event": health_service.event_to_dict(event),
        "guidance": guidance.to_dict(),
        # Angestoßen, nicht erledigt — das Ergebnis steht unter
        # `/health/neuplanung`.
        "plan_wird_angepasst": angestossen,
        "neuplanung": _NEUPLANUNG.get(user.id) if angestossen else None,
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
    angestossen = bool(body.adjust_plan and user is not None)
    if angestossen:
        montag = _ziel_montag()
        _NEUPLANUNG[user.id] = {"status": "laeuft", "montag": str(montag), "detail": None}
        background.add_task(
            _regenerate,
            user.id,
            f"Der Athlet ist nach {event.days} Tagen Ausfall wieder gesund. "
            "Plane den Wiedereinstieg für diese Woche.",
            montag,
        )

    return {
        "event": health_service.event_to_dict(event),
        "guidance": guidance.to_dict(),
        "plan_wird_angepasst": angestossen,
        "neuplanung": _NEUPLANUNG.get(user.id) if angestossen else None,
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
