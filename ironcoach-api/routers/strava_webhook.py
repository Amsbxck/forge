import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import AthleteProfile, TrainingSession
from schemas import StravaAuthUrl, StravaConnected
from services.strava_service import StravaService
from services.plan_generator import get_week_for_date
from core.config import settings
from core.deps import require_user

logger = logging.getLogger(__name__)

# Zwei Router mit Absicht: der Webhook muss ohne Anmeldung erreichbar sein,
# weil Strava ihn aufruft. Alles andere unter /api/strava/ gehört hinter die
# Anmeldung — sonst könnte jeder einen Abgleich auslösen oder den Zustand
# der Verbindung auslesen.
router = APIRouter()          # offen: nur /webhook
api_router = APIRouter()      # geschützt: /api/strava/*


@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == settings.STRAVA_VERIFY_TOKEN:
        return {"hub.challenge": params.get("hub.challenge")}
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if (
        payload.get("object_type") == "activity"
        and payload.get("aspect_type") == "create"
    ):
        activity_id = payload["object_id"]
        athlete_id = payload["owner_id"]
        background_tasks.add_task(process_new_strava_activity, activity_id, athlete_id)

    return {"status": "ok"}


async def process_new_strava_activity(activity_id: int, athlete_id: int):
    """Webhook-Pfad — nutzt denselben Ingest wie der Reconcile-Job.

    Zwei getrennte Implementierungen würden auseinanderdriften; hier gibt es
    nur eine, inklusive Duplikat-Matching und Obsidian-Sync.
    """
    db = SessionLocal()
    try:
        from models import StravaCredentials
        from services.ingest import ingest_activity
        from core.tenancy import SKIP_OPTION, acting_as

        # Strava ruft ohne Token an und nennt nur die Athleten-ID. Ohne diese
        # Auflösung liefe der Ingest ohne Nutzerkontext und ordnete die
        # Aktivität irgendeinem Konto zu — bei mehreren Athleten dem falschen.
        creds = (
            db.query(StravaCredentials)
            .filter(StravaCredentials.athlete_id == athlete_id)
            .execution_options(**{SKIP_OPTION: True})
            .first()
        )
        if creds is None:
            logger.warning("Webhook für unbekannten Strava-Athleten %s ignoriert", athlete_id)
            return

        with acting_as(creds.user_id):
            result = await ingest_activity(db, activity_id, athlete_id)
        logger.info(f"Webhook-Ingest {activity_id} (Nutzer {creds.user_id}): {result}")
    except Exception as e:
        # Verloren ist nichts: der Reconcile-Job zieht die Aktivität nach.
        logger.error(f"Failed to process Strava activity {activity_id}: {e}")
    finally:
        db.close()


@api_router.get("/api/strava/auth", response_model=StravaAuthUrl)
def strava_auth(request: Request, user=Depends(require_user)):
    """Autorisierungs-URL mit Nutzerbezug im state-Parameter.

    Strava ruft den Callback später ohne Token auf. Ohne diesen Umweg wüsste
    er nicht, für wen die Verbindung gilt, und würde sie dem ersten Konto
    zuschreiben."""
    from core.security import create_access_token

    redirect_uri = str(request.base_url) + "api/strava/callback"
    state = create_access_token(user.id, user.email)
    service = StravaService(None)
    return StravaAuthUrl(auth_url=service.get_auth_url(redirect_uri, state=state))


@router.get("/api/strava/callback")
async def strava_callback(code: str, state: str | None = None, db: Session = Depends(get_db)):
    """Rückleitung von Strava — ohne Token, dafür mit unserem state."""
    from core.security import user_id_from_token
    from core.tenancy import acting_as

    user_id = user_id_from_token(state)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Ungültiger oder fehlender state — Verbindung erneut starten")

    service = StravaService(db)
    try:
        token_data = await service.exchange_code(code)
        with acting_as(user_id):
            athlete_id = service.save_credentials(token_data)
        return {"message": "Strava verbunden", "athlete_id": athlete_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth fehlgeschlagen: {str(e)}")


@api_router.get("/api/strava/status", response_model=StravaConnected)
def strava_status(db: Session = Depends(get_db)):
    from models import StravaCredentials
    creds = db.query(StravaCredentials).first()
    if creds:
        return StravaConnected(connected=True, athlete_id=creds.athlete_id)
    return StravaConnected(connected=False)


@api_router.get("/api/strava/scheduler")
def scheduler_state():
    """Läuft der stündliche Abgleich, und wann kommt der nächste Lauf?"""
    from core.scheduler import scheduler_status
    return scheduler_status()


@api_router.get("/api/strava/subscription")
async def strava_subscription(db: Session = Depends(get_db)):
    """Health-Check der Webhook-Subscription."""
    from services.reconcile import check_subscription
    return await check_subscription(db)


@api_router.post("/api/strava/sync-now")
async def sync_now(db: Session = Depends(get_db)):
    """Sofort abgleichen — derselbe Ablauf wie der stündliche Job.

    Strava nachziehen, klassifizieren, Obsidian-Outbox abarbeiten. Damit
    muss nach einer Einheit nicht bis zur nächsten vollen Stunde gewartet
    werden.
    """
    from core.config import settings
    from services.reconcile import run_full_reconcile

    result = await run_full_reconcile(db, days=settings.RECONCILE_WINDOW_DAYS)
    activities = result["activities"]
    counts = activities.get("by_action", {})
    details = activities.get("details", [])

    # Notes entstehen bereits beim Einlesen jeder Aktivität; die Outbox
    # danach fängt nur noch Nachzügler ab. Beides zählen, sonst meldet der
    # Knopf null geschriebene Notes, obwohl gerade welche entstanden sind.
    written = sum(1 for d in details if d.get("obsidian") in ("written", "moved"))
    written += (result["obsidian"].get("by_status") or {}).get("written", 0)

    return {
        "ok": activities.get("status") == "ok",
        "checked": activities.get("checked", 0),
        "created": counts.get("created", 0),
        "linked": counts.get("linked", 0),
        "unchanged": counts.get("skipped_duplicate", 0),
        "obsidian_written": written,
        "error": activities.get("error"),
        "details": details,
    }


@api_router.post("/api/strava/reconcile")
async def strava_reconcile(
    days: int = 14,
    dry_run: bool = True,
    db: Session = Depends(get_db),
):
    """Verpasste Aktivitäten nachziehen.

    dry_run ist absichtlich der Standard: der Lauf zeigt erst, was er tun
    würde. Schreiben nur mit dry_run=false.
    """
    from services.reconcile import reconcile_activities
    return await reconcile_activities(db, days=days, dry_run=dry_run)
