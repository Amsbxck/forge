"""Hintergrundjobs im Backend-Prozess (APScheduler).

Bewusst kein eigener Service und kein System-Cron: ein Container weniger,
kein zusätzliches Deployment. Bei einem einzelnen Backend-Prozess reicht das.

Standardmäßig AUS. Die Jobs schreiben in die Datenbank und reden nach außen
(Strava, Garmin) — das soll niemand versehentlich durch einen Container-Neustart
auslösen. Zwei getrennte Schalter:

- RECONCILE_ENABLED=true: stündlicher Strava-Abgleich und Subscription-Check.
- GARMIN_SYNC_ENABLED=true: HRV morgens und die Spanne sonntags aus Garmin
  Connect. Eigener Schalter, weil wer Strava nicht nutzt, trotzdem HRV
  bekommen soll.

Der Scheduler startet, sobald einer der beiden gesetzt ist, und hängt nur die
Jobs der eingeschalteten Schalter an.
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

    # Erst nur die Nutzer-IDs, dann je Athlet eine **eigene** Session.
    #
    # Vorher lief der ganze Job über eine einzige Session. Scheiterte bei einem
    # Athleten eine Datenbankanweisung, stand die Transaktion danach auf
    # „abgebrochen" — und schon das Protokollieren im Fehlerzweig
    # (`creds.user_id` auf dem verfallenen Objekt) warf erneut. Jeder Athlet
    # hinter dem ersten Fehler bekam keinen Abgleich mehr, jede Stunde wieder.
    db = SessionLocal()
    try:
        nutzer_ids = [
            row[0] for row in (
                db.query(StravaCredentials.user_id)
                .execution_options(**{SKIP_OPTION: True})
                .all()
            )
        ]
    except Exception:
        logger.exception("Reconcile-Job: Athletenliste nicht lesbar")
        return
    finally:
        db.close()

    if not nutzer_ids:
        logger.info("Reconcile: kein Athlet mit Strava-Verbindung")
        return

    for user_id in nutzer_ids:
        sitzung = SessionLocal()
        try:
            with acting_as(user_id):
                result = await run_full_reconcile(sitzung, days=settings.RECONCILE_WINDOW_DAYS)
            logger.info(
                "Reconcile Nutzer %s: %s Aktivitäten geprüft, %s | Obsidian: %s",
                user_id,
                result["activities"].get("checked"),
                result["activities"].get("by_action"),
                result["obsidian"].get("by_status"),
            )
        except Exception:
            # Ein Athlet mit abgelaufenem Token darf die übrigen nicht aufhalten.
            sitzung.rollback()
            logger.exception("Reconcile für Nutzer %s fehlgeschlagen", user_id)
        finally:
            sitzung.close()


async def _garmin_job(mit_spanne: bool) -> None:
    """HRV (und sonntags die Spanne) für jeden Athleten mit Garmin-Schlüssel.

    Dasselbe Muster wie `_reconcile_job` und aus demselben Grund: erst nur
    die Nutzer-IDs ohne Nutzerkontext, dann je Athlet eine **eigene** Session
    in `acting_as`. Eine geteilte Session hätte nach dem ersten Fehler auf
    „abgebrochen" gestanden und jeden folgenden Athleten mitgerissen. Ein
    Fehler oder ein 429 bei einem Athleten hält die anderen nicht auf; er
    wird beim nächsten Lauf erneut versucht.

    Morgens wird ein Athlet ausgelassen, für den Garmins Wert von heute
    schon da ist: Der Job läuft stündlich von 7 bis 12 Uhr, damit auch eine
    spät synchronisierte Uhr erfasst wird, soll Garmin aber nicht fünfmal
    fragen, wenn der Wert um 7 Uhr schon kam.
    """
    from database import SessionLocal
    from models import AthleteProfile, User
    from core.tenancy import SKIP_OPTION, acting_as
    from services.garmin_hrv import abgleich_fuer, heute_schon_da

    db = SessionLocal()
    try:
        nutzer_ids = [
            row[0] for row in (
                db.query(AthleteProfile.user_id)
                .filter(AthleteProfile.garmin_api_key.isnot(None),
                        AthleteProfile.user_id.isnot(None))
                .execution_options(**{SKIP_OPTION: True})
                .all()
            )
        ]
    except Exception:
        logger.exception("Garmin-Job: Athletenliste nicht lesbar")
        return
    finally:
        db.close()

    for user_id in nutzer_ids:
        sitzung = SessionLocal()
        try:
            with acting_as(user_id):
                if not mit_spanne and heute_schon_da(sitzung, user_id):
                    continue
                user = sitzung.query(User).filter(User.id == user_id).first()
                if user is None:
                    continue
                ergebnis = await abgleich_fuer(sitzung, user, tage=7, mit_spanne=mit_spanne)
            logger.info("Garmin Nutzer %s: %s", user_id, ergebnis)
        except Exception:
            sitzung.rollback()
            logger.exception("Garmin-Abgleich für Nutzer %s fehlgeschlagen", user_id)
        finally:
            sitzung.close()


async def _garmin_morgens_job() -> None:
    await _garmin_job(mit_spanne=False)


async def _garmin_sonntag_job() -> None:
    await _garmin_job(mit_spanne=True)


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
    if not (settings.RECONCILE_ENABLED or settings.GARMIN_SYNC_ENABLED):
        logger.info("Scheduler deaktiviert (RECONCILE_ENABLED und GARMIN_SYNC_ENABLED aus)")
        return None
    if _scheduler is not None:
        return _scheduler

    # Zeitzone explizit über zoneinfo: die Zeichenkette allein wurde vom
    # Scheduler stillschweigend als UTC übernommen, wodurch der tägliche
    # Check um 6:15 tatsächlich um 8:15 Ortszeit lief.
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Berlin")
    # Auch an jedem CronTrigger: Ein Trigger-Objekt ohne eigene Zone nimmt die
    # Zone des Rechners, nicht die des Schedulers. Das stimmt nur, solange TZ
    # im Container gesetzt ist; für „7 Uhr morgens" soll das nicht davon abhängen.
    _scheduler = AsyncIOScheduler(timezone=zone)
    if settings.RECONCILE_ENABLED:
        _scheduler.add_job(
            _reconcile_job,
            CronTrigger(minute=settings.RECONCILE_MINUTE, timezone=zone),
            id="reconcile",
            max_instances=1,
            coalesce=True,  # verpasste Läufe nicht nachholen, nur den nächsten fahren
        )
        _scheduler.add_job(
            _subscription_job,
            CronTrigger(hour=6, minute=15, timezone=zone),
            id="subscription_health",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Reconcile gestartet (stündlich zur Minute %s)", settings.RECONCILE_MINUTE)
    if settings.GARMIN_SYNC_ENABLED:
        # Stündlich von 7 bis 12 Uhr: Die Uhr synchronisiert erst, wenn der
        # Athlet das Handy in die Hand nimmt. Wer um 9 aufsteht, hat um 7
        # noch keinen Wert; der nächste Lauf holt ihn.
        _scheduler.add_job(
            _garmin_morgens_job,
            CronTrigger(hour="7-12", minute=settings.GARMIN_MINUTE, timezone=zone),
            id="garmin_hrv_morgens",
            max_instances=1,
            coalesce=True,
        )
        # Sonntags die Spanne. Um 13 Uhr hat die Uhr sicher synchronisiert,
        # und Garmins Baseline enthält die Nacht von Sonntag.
        _scheduler.add_job(
            _garmin_sonntag_job,
            CronTrigger(day_of_week="sun", hour=13, minute=15, timezone=zone),
            id="garmin_spanne_sonntag",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Garmin-HRV gestartet (7–12 Uhr zur Minute %s, Spanne sonntags 13:15)",
                    settings.GARMIN_MINUTE)
    _scheduler.start()
    return _scheduler


def scheduler_status() -> dict:
    """Läuft der Scheduler wirklich, und wann feuert er das nächste Mal?

    Nötig, weil sich das sonst nicht überprüfen lässt: ein nicht gestarteter
    Scheduler verhält sich exakt wie einer, der gerade nichts zu tun hat.
    `reconcile_enabled` und `garmin_enabled` zeigen getrennt, welche Jobs
    eingeschaltet sind; `enabled` heißt „irgendeiner".
    """
    schalter = {
        "reconcile_enabled": settings.RECONCILE_ENABLED,
        "garmin_enabled": settings.GARMIN_SYNC_ENABLED,
    }
    if not (settings.RECONCILE_ENABLED or settings.GARMIN_SYNC_ENABLED):
        return {
            "enabled": False,
            "running": False,
            **schalter,
            "jobs": [],
            "hint": "RECONCILE_ENABLED=true bzw. GARMIN_SYNC_ENABLED=true in der .env setzen "
                    "und Backend neu starten",
        }
    if _scheduler is None:
        return {
            "enabled": True,
            "running": False,
            **schalter,
            "jobs": [],
            "hint": "Aktiviert, aber nicht gestartet — Backend neu starten",
        }
    return {
        "enabled": True,
        "running": _scheduler.running,
        **schalter,
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
