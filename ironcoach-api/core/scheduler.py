"""Hintergrundjobs im Backend-Prozess (APScheduler).

Bewusst kein eigener Service und kein System-Cron: ein Container weniger,
kein zusätzliches Deployment. Bei einem einzelnen Backend-Prozess reicht das.

Standardmäßig AUS. Der Job schreibt in die Datenbank und redet mit Strava —
das soll niemand versehentlich durch einen Container-Neustart auslösen.
Aktivieren über RECONCILE_ENABLED=true.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _reconcile_job() -> None:
    """Für jeden Athleten mit Strava-Verbindung einzeln abgleichen.

    Ein Durchlauf ohne Nutzerkontext sähe die Daten aller Athleten als eine
    Menge: Aktivitäten des zweiten Nutzers landeten beim ersten, und der
    Duplikatabgleich verglich quer über Konten hinweg.
    """
    from database import SessionLocal
    from models import StravaCredentials
    from core.tenancy import SKIP_OPTION, acting_as
    from services.reconcile import run_full_reconcile

    db = SessionLocal()
    try:
        athletes = (
            db.query(StravaCredentials)
            .execution_options(**{SKIP_OPTION: True})
            .all()
        )
        if not athletes:
            logger.info("Reconcile: kein Athlet mit Strava-Verbindung")
            return

        for creds in athletes:
            try:
                with acting_as(creds.user_id):
                    result = await run_full_reconcile(db, days=settings.RECONCILE_WINDOW_DAYS)
                logger.info(
                    "Reconcile Nutzer %s: %s Aktivitäten geprüft, %s | Obsidian: %s",
                    creds.user_id,
                    result["activities"].get("checked"),
                    result["activities"].get("by_action"),
                    result["obsidian"].get("by_status"),
                )
            except Exception:
                # Ein Athlet mit abgelaufenem Token darf die übrigen nicht aufhalten.
                logger.exception("Reconcile für Nutzer %s fehlgeschlagen", creds.user_id)
    except Exception:
        logger.exception("Reconcile-Job fehlgeschlagen")
    finally:
        db.close()


async def _subscription_job() -> None:
    from database import SessionLocal
    from services.reconcile import check_subscription

    db = SessionLocal()
    try:
        result = await check_subscription(db)
        if not result.get("active"):
            logger.warning("Strava-Subscription: %s", result.get("hint") or result)
        else:
            logger.info("Strava-Subscription aktiv: %s", result.get("count"))
    except Exception:
        logger.exception("Subscription-Health-Check fehlgeschlagen")
    finally:
        db.close()


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    if not settings.RECONCILE_ENABLED:
        logger.info("Reconcile-Scheduler deaktiviert (RECONCILE_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    # Zeitzone explizit über zoneinfo: die Zeichenkette allein wurde vom
    # Scheduler stillschweigend als UTC übernommen, wodurch der tägliche
    # Check um 6:15 tatsächlich um 8:15 Ortszeit lief.
    from zoneinfo import ZoneInfo

    _scheduler = AsyncIOScheduler(timezone=ZoneInfo("Europe/Berlin"))
    _scheduler.add_job(
        _reconcile_job,
        CronTrigger(minute=settings.RECONCILE_MINUTE),
        id="reconcile",
        max_instances=1,
        coalesce=True,  # verpasste Läufe nicht nachholen, nur den nächsten fahren
    )
    _scheduler.add_job(
        _subscription_job,
        CronTrigger(hour=6, minute=15),
        id="subscription_health",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Reconcile-Scheduler gestartet (stündlich zur Minute %s)", settings.RECONCILE_MINUTE)
    return _scheduler


def scheduler_status() -> dict:
    """Läuft der Scheduler wirklich, und wann feuert er das nächste Mal?

    Nötig, weil sich das sonst nicht überprüfen lässt: ein nicht gestarteter
    Scheduler verhält sich exakt wie einer, der gerade nichts zu tun hat.
    """
    if not settings.RECONCILE_ENABLED:
        return {
            "enabled": False,
            "running": False,
            "jobs": [],
            "hint": "RECONCILE_ENABLED=true in der .env setzen und Backend neu starten",
        }
    if _scheduler is None:
        return {
            "enabled": True,
            "running": False,
            "jobs": [],
            "hint": "Aktiviert, aber nicht gestartet — Backend neu starten",
        }
    return {
        "enabled": True,
        "running": _scheduler.running,
        "window_days": settings.RECONCILE_WINDOW_DAYS,
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in _scheduler.get_jobs()
        ],
    }


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
