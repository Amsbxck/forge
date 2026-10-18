"""Was an einer absolvierten Einheit nachträglich geändert wird.

Arbeitsweg markieren, löschen, endgültig löschen, wiederherstellen. Jeder
dieser Schritte hat Folgen für die Vorgabe im Plan und für die Vault-Notiz —
und jede Stelle, die einen davon auslöst (Verlaufsseite, Strava-Webhook), muss
dieselben Folgen ziehen. Vorher stand die Logik im Router, und der Webhook
kannte sie nicht.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models import TrainingSession

logger = logging.getLogger(__name__)


def arbeitsweg_setzen(db: Session, session: TrainingSession, is_commute: bool) -> dict | None:
    """Markieren gibt die Vorgabe frei, Aufheben ordnet neu zu.

    Beim Markieren verschwindet auch die Abweichungsnotiz — sie verglich mit
    einer Vorgabe, zu der die Fahrt nicht mehr gehört — und die Vault-Notiz
    wird zum Neuschreiben vorgemerkt (`release_planned`).
    """
    from services.classification import classify_session
    from services.planned_link import release_planned

    session.is_commute = is_commute
    if is_commute:
        vorgabe = release_planned(db, session, commit=False)
        session.actual_type = None
        session.obsidian_synced_at = None
        db.flush()
        return vorgabe
    db.flush()
    return classify_session(db, session, commit=False)


def weich_loeschen(db: Session, session: TrainingSession) -> dict:
    """Wiederherstellbar löschen und die Vorgabe freigeben.

    Die Vault-Notiz wird mit entfernt (eine selbst überarbeitete bleibt, siehe
    `delete_session_note`) — vorher blieb sie liegen und zeigte im Vault eine
    Einheit, die es in FORGE nicht mehr gab. Beim Wiederherstellen entsteht
    sie neu.
    """
    from services.planned_link import release_planned

    session.deleted_at = datetime.utcnow()
    vorgabe = release_planned(db, session, commit=False)
    try:
        from services.obsidian.sync import delete_session_note
        delete_session_note(db, session)
    except Exception as e:  # pragma: no cover - Löschen darf nie am Vault scheitern
        logger.warning("Vault-Notiz zu Einheit %s nicht entfernt: %s", session.id, e)
    return vorgabe


def endgueltig_loeschen(db: Session, session: TrainingSession) -> tuple[dict, dict]:
    """Zeile, Notiz und Zuordnung entfernen — und die Strava-Aktivität merken.

    Ohne den Vermerk kam sie beim nächsten Abgleich zurück (siehe
    `models.GeloeschteStravaAktivitaet`).
    """
    from models import GeloeschteStravaAktivitaet
    from services.obsidian.sync import delete_session_note
    from services.planned_link import release_planned

    vault = delete_session_note(db, session)
    # Vor dem Löschen: Danach ist `planned_session_id` nicht mehr zu lesen.
    vorgabe = release_planned(db, session, commit=False)
    if session.strava_activity_id:
        schon = db.query(GeloeschteStravaAktivitaet.id).filter(
            GeloeschteStravaAktivitaet.strava_activity_id == session.strava_activity_id
        ).first()
        if schon is None:
            db.add(GeloeschteStravaAktivitaet(
                user_id=session.user_id, strava_activity_id=session.strava_activity_id,
            ))
    db.delete(session)
    return vault, vorgabe


def wiederherstellen(db: Session, session: TrainingSession) -> dict | None:
    """Zurückholen, neu zuordnen, Notiz neu schreiben lassen."""
    from services.classification import classify_session

    session.deleted_at = None
    session.obsidian_synced_at = None
    db.flush()
    try:
        return classify_session(db, session, commit=False)
    except Exception as e:  # pragma: no cover - Wiederherstellen darf nie scheitern
        logger.warning("Neuzuordnung nach Wiederherstellen fehlgeschlagen: %s", e)
        return None
