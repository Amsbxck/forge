"""Die Verbindung zwischen geplanter und absolvierter Einheit lösen.

Beim Löschen einer Einheit blieb sie stehen. Die Folgen waren beide still:

  * **Der Tag blieb grün.** `planned.status` bleibt "completed", auch wenn die
    Einheit, die ihn erfüllt hat, gelöscht ist. Im Wochenplan stand danach ein
    Häkchen an einem Tag, an dem nichts mehr verbucht war.
  * **Die spätere, richtige Einheit wurde nicht mehr zugeordnet.** Nach einem
    weichen Löschen zeigte `matched_session_id` weiter auf die gelöschte
    Einheit, und die Regel "die mit der kleineren id gewinnt" — gedacht für
    Bricks — behielt sie: Die abends absolvierte Ausfahrt hing daneben.

Genau das passiert beim Arbeitsweg: morgens getrackt, in FORGE gelöscht, weil er
nicht in den Plan gehört, abends die eigentliche Einheit. Ohne dieses Lösen war
die Vorgabe schon vom Arbeitsweg belegt.

Ein Brick besteht aus zwei Einheiten an einer Vorgabe. Deshalb wird nicht blind
zurückgesetzt, sondern nachgesehen, ob noch eine andere übrig ist.
"""

import logging

from sqlalchemy.orm import Session

from models import PlannedSession, TrainingSession

logger = logging.getLogger(__name__)


def release_planned(db: Session, session: TrainingSession, commit: bool = True) -> dict:
    """Die Vorgabe dieser Einheit freigeben, falls keine andere sie noch erfüllt."""
    planned_id = session.planned_session_id
    if planned_id is None:
        return {"status": "keine_vorgabe"}

    planned = db.query(PlannedSession).filter(PlannedSession.id == planned_id).first()
    if planned is None:
        return {"status": "vorgabe_weg"}

    # Andere Einheiten an derselben Vorgabe — bei einem Brick sind es zwei.
    # Die gerade gelöschte ist ausgenommen, gelöschte ohnehin.
    verbleibend = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.planned_session_id == planned_id,
            TrainingSession.id != session.id,
            TrainingSession.deleted_at == None,  # noqa: E711
        )
        .order_by(TrainingSession.id.asc())
        .all()
    )

    if verbleibend:
        # Die Vorgabe bleibt erfüllt, aber der Rückverweis darf nicht auf die
        # gelöschte Einheit zeigen.
        planned.matched_session_id = verbleibend[0].id
        ergebnis = {"status": "bleibt_erfuellt", "planned_id": planned_id,
                    "verbleibend": len(verbleibend)}
    else:
        planned.status = "planned"
        planned.matched_session_id = None
        ergebnis = {"status": "freigegeben", "planned_id": planned_id}

    session.planned_session_id = None
    session.match_confidence = None
    if commit:
        db.commit()
    logger.info("Vorgabe %s nach Löschen von Einheit %s: %s",
                planned_id, session.id, ergebnis["status"])
    return ergebnis
