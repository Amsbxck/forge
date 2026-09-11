"""Status und manuelle Auslöser für die Obsidian-Integration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from models import TrainingSession
from services.obsidian.client import ObsidianClient, ObsidianError, ObsidianUnavailable
from services.obsidian.sync import pending_sessions, sync_pending, sync_session_by_id

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/obsidian/status")
def obsidian_status(db: Session = Depends(get_db)):
    """Erreichbarkeit + Größe der Outbox. Blockiert nie länger als der Timeout."""
    # Anbindung des angemeldeten Athleten. Vorher stand hier ein Client aus
    # der .env: Jeder Nutzer bekam Erreichbarkeit und Adresse des Vaults der
    # Installation zu sehen — also die des Betreibers.
    from core.deps import get_profile
    from services.obsidian.client import client_for_profile, vault_subdir_for

    profil = get_profile(db)
    client = client_for_profile(profil)
    payload = {
        "enabled": client.enabled,
        "base_url": client.base_url or None,
        "vault_subdir": vault_subdir_for(profil),
        "reachable": False,
        "authenticated": False,
        "pending": len(pending_sessions(db)),
        "synced": db.query(TrainingSession)
        .filter(TrainingSession.obsidian_synced_at != None)  # noqa: E711
        .count(),
        "error": None,
    }
    if not client.enabled:
        payload["error"] = "Noch kein eigener Vault verbunden — unter Verbindungen einrichten"
        return payload

    try:
        info = client.ping()
        payload["reachable"] = True
        payload["authenticated"] = bool(info.get("authenticated"))
        payload["plugin_version"] = info.get("versions", {}).get("self")
    except ObsidianError as e:
        payload["reachable"] = True
        payload["error"] = str(e)
    except ObsidianUnavailable as e:
        payload["error"] = str(e)
    return payload


@router.post("/obsidian/sync/{session_id}")
def sync_one(session_id: int, db: Session = Depends(get_db)):
    result = sync_session_by_id(db, session_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Einheit {session_id} nicht gefunden")
    return result


@router.post("/obsidian/sync-plan/{week_number}")
def sync_plan(week_number: int, db: Session = Depends(get_db)):
    """Wochenplan als Note in den Vault schreiben."""
    from services.obsidian.plan_note import sync_plan_note
    from services.plan_selection import active_plan_for_week

    plan = active_plan_for_week(db, week_number)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Kein Plan für Woche {week_number}")
    return sync_plan_note(db, plan)


@router.post("/obsidian/sync-plans")
def sync_all_plans(db: Session = Depends(get_db)):
    """Alle aktiven Wochenpläne nachziehen — einmalig nach dem Einbau."""
    from models import WeeklyPlan
    from services.obsidian.plan_note import sync_plan_note
    from services.plan_selection import active_plan_for_week

    weeks = [row[0] for row in db.query(WeeklyPlan.week_number).distinct().all()]
    results = []
    for week in sorted(weeks):
        plan = active_plan_for_week(db, week)
        if plan is not None:
            results.append(sync_plan_note(db, plan))
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"weeks": len(results), "by_status": counts}


@router.post("/obsidian/sync-pending")
def sync_outbox(days: int = 30, limit: int = 50, db: Session = Depends(get_db)):
    """Offene Syncs nachholen — der manuelle Zwilling des Reconcile-Jobs."""
    return sync_pending(db, days=days, limit=limit)
