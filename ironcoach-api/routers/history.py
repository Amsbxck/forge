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
    """Einheit löschen, wiederherstellbar — und ihre Vorgabe freigeben.

    Das Freigeben ist der Teil, der gefehlt hat. Ohne es blieb der Tag im
    Wochenplan grün, obwohl die Einheit, die ihn erfüllt hat, gelöscht war; und
    die später absolvierte, richtige Einheit wurde nicht mehr zugeordnet, weil
    `matched_session_id` weiter auf die gelöschte zeigte.
    """
    from services.planned_link import release_planned

    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    s.deleted_at = datetime.utcnow()
    vorgabe = release_planned(db, s, commit=False)
    db.commit()
    return {"message": "Einheit gelöscht (wiederherstellbar)", "vorgabe": vorgabe}


@router.delete("/history/sessions/{session_id}/hard")
def hard_delete_session(session_id: int, db: Session = Depends(get_db)):
    """Einheit endgültig löschen — samt ihrer Notiz im Vault.

    Der häufigste Anlass ist eine Doppelaufnahme: Wer eine Ausfahrt zugleich mit
    Garmin und Wahoo aufzeichnet, bekommt zwei Strava-Aktivitäten mit
    verschiedenen IDs. Die Entdopplung läuft über `strava_activity_id` und greift
    dort nicht. Blieb die Notiz liegen, behielt der Vault genau den Fehler, den
    man in FORGE gerade beseitigt hat.

    Die Notiz wird **vor** dem Löschen der Zeile entfernt, weil `obsidian_path`
    nur an ihr hängt. Das Ergebnis geht mit in die Antwort: Ist der Vault gerade
    nicht erreichbar, wäre eine stille Zusage schlimmer als der Hinweis, dass
    dort noch etwas liegt — niemand sucht später eine Notiz, von der er glaubt,
    sie sei gelöscht.
    """
    from services.obsidian.sync import delete_session_note

    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")

    vault = delete_session_note(db, s)

    from services.planned_link import release_planned
    # Vor dem Löschen: Danach ist `planned_session_id` nicht mehr zu lesen.
    # Der Fremdschlüssel setzt zwar `matched_session_id` auf NULL, aber
    # `status` bliebe auf "completed" — der Tag wäre grün ohne alles.
    vorgabe = release_planned(db, s, commit=False)

    db.delete(s)
    db.commit()

    meldung = "Einheit permanent gelöscht"
    if vault["status"] == "gelöscht":
        meldung += " — Notiz im Vault entfernt"
    elif vault["status"] in ("unavailable", "error"):
        meldung += (
            f" — die Notiz {vault.get('path')} konnte nicht entfernt werden "
            "(Vault nicht erreichbar). Bitte dort von Hand löschen."
        )
    elif vault["status"] == "behalten_eigene_note":
        meldung += f" — die Notiz {vault.get('path')} bleibt: sie ist von dir überarbeitet"
    return {"message": meldung, "vault": vault, "vorgabe": vorgabe}


@router.patch("/history/sessions/{session_id}/commute")
def set_commute(session_id: int, is_commute: bool, db: Session = Depends(get_db)):
    """Eine Einheit als Arbeitsweg markieren — oder die Markierung aufheben.

    Der Rückfall, wenn Strava das Kennzeichen nicht mitliefert. Garmin setzt es
    beim Aktivitätstyp "Bike Commute", aber nicht bei jedem Gerät und nicht,
    wenn die Fahrt als normale Radausfahrt gespeichert wurde.

    Der Sinn gegenüber dem Löschen: Ein Arbeitsweg ist echtes Radfahren und
    gehört in die Formkurve. Er soll nur nicht als die geplante Einheit gelten.
    Wer ihn löscht, verliert die Last; wer ihn markiert, behält sie.

    Beides zieht eine Neuzuordnung nach sich: Beim Markieren wird die Vorgabe
    freigegeben (sonst bliebe der Tag grün), beim Aufheben neu gematcht.
    """
    from services.classification import classify_session
    from services.planned_link import release_planned

    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")

    s.is_commute = is_commute
    if is_commute:
        vorgabe = release_planned(db, s, commit=False)
        db.commit()
    else:
        db.commit()
        vorgabe = classify_session(db, s)

    return {
        "message": "Als Arbeitsweg markiert" if is_commute else "Markierung aufgehoben",
        "is_commute": is_commute,
        "vorgabe": vorgabe,
    }


@router.post("/history/sessions/{session_id}/restore")
def restore_session(session_id: int, db: Session = Depends(get_db)):
    """Einheit zurückholen — und neu zuordnen.

    Beim Löschen wurde die Verbindung zur Vorgabe gelöst. Sie hier nicht wieder
    herzustellen hiesse: Die Einheit ist zurück, gilt aber als ungeplant, und
    der Tag im Wochenplan bleibt grau. Neu zugeordnet statt gemerkt, weil sich
    der Plan zwischenzeitlich geändert haben kann.
    """
    from services.classification import classify_session

    s = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Einheit nicht gefunden")
    s.deleted_at = None
    db.commit()

    try:
        zuordnung = classify_session(db, s)
    except Exception as e:  # pragma: no cover - Wiederherstellen darf nie scheitern
        import logging
        logging.getLogger(__name__).warning("Neuzuordnung nach Wiederherstellen fehlgeschlagen: %s", e)
        zuordnung = None

    return {"message": "Einheit wiederhergestellt", "zuordnung": zuordnung}


@router.get("/history/plans", response_model=list[WeeklyPlanOut])
def list_plans(db: Session = Depends(get_db)):
    return db.query(WeeklyPlan).order_by(WeeklyPlan.week_number.desc()).all()
