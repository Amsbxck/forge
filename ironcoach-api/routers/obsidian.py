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
    from core.saison import saison_ziele
    from models import WeeklyPlan
    from services.obsidian.plan_note import sync_plan_note
    from services.plan_selection import active_plan_for_week

    ziele = saison_ziele(db)
    weeks = [row[0] for row in db.query(WeeklyPlan.week_number).distinct().all()]
    results = []
    for week in sorted(weeks):
        plan = active_plan_for_week(db, week)
        if plan is not None:
            results.append(sync_plan_note(db, plan, ziele=ziele))
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"weeks": len(results), "by_status": counts}


@router.post("/obsidian/neu-ordnen")
def neu_ordnen(db: Session = Depends(get_db)):
    """Bestand in die Saisonordner umziehen — einmalig nach der Umstellung.

    Der Reconcile-Job fasst nur an, was noch nie geschrieben wurde
    (`obsidian_synced_at IS NULL`). Notes, die vor der Umstellung flach im
    Vault lagen, wären dadurch für immer dort geblieben. Hier wird jede
    Einheit einmal erneut synchronisiert; der Umzug samt Reflexion steckt
    schon in `sync_session`.

    Gibt es keinen Vault, passiert nichts — der Aufruf ist gefahrlos
    wiederholbar, weil bereits umgezogene Notes als "unchanged" durchlaufen.
    """
    from core.saison import saison_ziele
    from services.obsidian.client import client_for_profile
    from services.obsidian.sync import sync_session
    from core.deps import get_profile

    client = client_for_profile(get_profile(db))
    if not client.enabled:
        raise HTTPException(status_code=400, detail="Kein Vault verbunden")

    ziele = saison_ziele(db)
    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.deleted_at == None)  # noqa: E711
        .order_by(TrainingSession.session_date.asc())
        .all()
    )

    counts: dict[str, int] = {}
    umgezogen = []
    fehler = None
    for session in sessions:
        result = sync_session(db, session, client=client, ziele=ziele)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result.get("moved_from"):
            umgezogen.append({"von": result["moved_from"], "nach": result["path"]})
        # Ist der Vault mitten im Durchgang weg, bringt das Weitermachen
        # nichts — die restlichen Einheiten bleiben offen und der
        # Reconcile-Job holt sie nach.
        if result["status"] in ("unavailable", "error"):
            fehler = result.get("error")
            break

    # Nur weitermachen, wenn der Vault überhaupt antwortet. Vorher lief der
    # Plandurchgang auch dann noch, wenn schon die erste Einheit gescheitert
    # war — und zählte die geprüften Wochen mit, als wäre etwas geschrieben
    # worden.
    plaene = sync_all_plans(db) if fehler is None else None

    # Noten, zu denen es keine Planzeile mehr gibt, ordnen sich aus ihrem
    # eigenen Frontmatter ein. Ohne das blieben nach einem Umzug auf eine
    # neue Installation sämtliche Pläne früherer Saisons flach liegen: die
    # Einheiten werden übernommen, die Wochenpläne nicht.
    verwaiste = []
    if fehler is None:
        from core.deps import get_profile as _profil
        from services.obsidian.client import vault_subdir_for
        from services.obsidian.plan_note import verwaiste_plannoten_einordnen

        try:
            verwaiste = verwaiste_plannoten_einordnen(
                db, client, vault_subdir_for(_profil(db)), ziele
            )
        except (ObsidianError, ObsidianUnavailable) as e:
            logger.warning("Verwaiste Plan-Noten nicht eingeordnet: %s", e)
            fehler = str(e)

    # Ein Durchgang, der nichts geschrieben hat, weil der Vault nicht
    # antwortet, ist kein Erfolg. Vorher stand in der Oberfläche ein grünes
    # "✓ 0 von 112 Notizen umgezogen" — also gleichzeitig die Meldung, dass
    # alles geklappt hat, und der Beweis, dass nichts passiert ist.
    erreicht = sum(
        n for status, n in counts.items()
        if status in ("written", "moved", "unchanged", "skipped_block_removed")
    )
    return {
        "einheiten": len(sessions),
        "erreicht": erreicht,
        "by_status": counts,
        "umgezogen": umgezogen,
        "plaene": plaene,
        "verwaiste_plaene": verwaiste,
        "abgebrochen": fehler is not None,
        "fehler": fehler,
    }


@router.post("/obsidian/sync-pending")
def sync_outbox(days: int = 30, limit: int = 50, db: Session = Depends(get_db)):
    """Offene Syncs nachholen — der manuelle Zwilling des Reconcile-Jobs."""
    return sync_pending(db, days=days, limit=limit)
