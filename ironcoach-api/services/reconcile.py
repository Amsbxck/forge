"""Reconciliation: aktiv bei Strava nachfragen statt auf Webhooks zu hoffen.

Strava stellt verpasste Events nicht erneut zu. Lief der Tunnel nicht oder
schlief der Rechner, ist die Aktivität für den Webhook für immer verloren.
Dieser Job fragt die Aktivitätsliste ab und zieht nach, was fehlt — damit
wird der Webhook zur Komfortfunktion statt zur Voraussetzung.

Zusätzlich: offene Obsidian-Syncs abarbeiten (Outbox) und den Zustand der
Webhook-Subscription prüfen.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from models import StravaCredentials, TrainingSession
from services.ingest import ingest_activity
from services.strava_service import StravaService

logger = logging.getLogger(__name__)


async def reconcile_activities(
    db: Session, days: int = 14, dry_run: bool = False, limit: int = 100
) -> dict:
    """Aktivitäten der letzten Tage abgleichen und Fehlendes nachziehen."""
    creds = db.query(StravaCredentials).first()
    if not creds:
        return {"status": "no_credentials", "checked": 0}

    after = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    service = StravaService(db)

    try:
        activities = await service.list_activities(creds.athlete_id, after=after, per_page=limit)
    except Exception as e:
        logger.error("Strava-Aktivitätsliste konnte nicht geladen werden: %s", e)
        return {"status": "strava_error", "error": str(e), "checked": 0}

    # Bereits bekannte Aktivitäten aussortieren, BEVOR Detaildaten geholt
    # werden. Sonst kostet jeder stündliche Lauf einen API-Call pro Aktivität
    # im Fenster — bei 14 Tagen und stündlichem Job schnell mehrere hundert
    # Requests am Tag, obwohl sich fast nie etwas ändert.
    ids = [a.get("id") for a in activities if a.get("id")]
    known = {
        row[0]
        for row in db.query(TrainingSession.strava_activity_id)
        .filter(TrainingSession.strava_activity_id.in_(ids))
        .all()
    } if ids else set()

    results: list[dict] = []
    counts: dict[str, int] = {}
    if known:
        counts["skipped_duplicate"] = len(known)

    for activity in activities:
        activity_id = activity.get("id")
        if not activity_id or activity_id in known:
            continue
        try:
            result = await ingest_activity(
                db, activity_id, creds.athlete_id,
                sync_obsidian=not dry_run, dry_run=dry_run,
            )
        except Exception as e:
            logger.error("Aktivität %s konnte nicht verarbeitet werden: %s", activity_id, e)
            result = {"activity_id": activity_id, "action": "error", "error": str(e)}
        counts[result["action"]] = counts.get(result["action"], 0) + 1
        # Duplikate sind der Normalfall und würden den Report zumüllen.
        if result["action"] != "skipped_duplicate":
            results.append(result)

    return {
        "status": "ok",
        "dry_run": dry_run,
        "window_days": days,
        "checked": len(activities),
        "by_action": counts,
        "details": results,
    }


async def check_subscription(db: Session, expected_url: str | None = None) -> dict:
    """Zustand der Webhook-Subscription.

    Meldet nur, richtet nichts ein: eine Subscription anzulegen verändert
    Zustand bei Strava und gehört nicht in einen Hintergrundjob.
    """
    service = StravaService(db)
    try:
        subs = await service.list_push_subscriptions()
    except Exception as e:
        return {"status": "error", "error": str(e)}

    payload = {
        "status": "ok",
        "count": len(subs),
        "active": bool(subs),
        "subscriptions": [
            {"id": s.get("id"), "callback_url": s.get("callback_url")} for s in subs
        ],
    }
    if expected_url:
        payload["matches_expected"] = any(
            (s.get("callback_url") or "").startswith(expected_url) for s in subs
        )
    if not subs:
        payload["hint"] = (
            "Keine Subscription registriert — Webhooks kommen nicht an. "
            "Der Reconcile-Job holt Aktivitäten trotzdem nach."
        )
    return payload


async def run_full_reconcile(db: Session, days: int = 14) -> dict:
    """Was der Cron-Job stündlich macht: Strava nachziehen, dann Obsidian-Outbox."""
    from services.obsidian.sync import sync_pending

    activities = await reconcile_activities(db, days=days)
    obsidian = sync_pending(db)
    return {
        "ran_at": datetime.utcnow().isoformat(),
        "activities": activities,
        "obsidian": obsidian,
    }
