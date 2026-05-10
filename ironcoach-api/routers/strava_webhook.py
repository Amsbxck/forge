import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import AthleteProfile, TrainingSession
from schemas import StravaAuthUrl, StravaConnected
from services.strava_service import StravaService
from services.plan_generator import get_week_for_date
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


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
    db = SessionLocal()
    try:
        service = StravaService(db)
        profile = db.query(AthleteProfile).first()
        ftp = profile.ftp_watts if profile else 238

        activity = await service.fetch_activity(activity_id, athlete_id)
        streams = await service.fetch_activity_streams(activity_id, athlete_id)

        from datetime import datetime, date as _date
        try:
            session_date = datetime.strptime(activity.get("start_date_local", "")[:10], "%Y-%m-%d").date()
        except Exception:
            session_date = _date.today()
        week_number = get_week_for_date(profile, session_date) if profile else 1

        session_data = service.map_strava_to_session(activity, streams, ftp, week_number)

        existing = db.query(TrainingSession).filter(
            TrainingSession.strava_activity_id == activity_id
        ).first()
        if existing:
            logger.info(f"Strava activity {activity_id} already exists, skipping")
            return

        session = TrainingSession(**session_data)
        db.add(session)
        db.commit()
        logger.info(f"Saved Strava activity {activity_id} as session {session.id}")
    except Exception as e:
        logger.error(f"Failed to process Strava activity {activity_id}: {e}")
    finally:
        db.close()


@router.get("/api/strava/auth", response_model=StravaAuthUrl)
def strava_auth(request: Request):
    redirect_uri = str(request.base_url) + "api/strava/callback"
    service = StravaService(None)
    return StravaAuthUrl(auth_url=service.get_auth_url(redirect_uri))


@router.get("/api/strava/callback")
async def strava_callback(code: str, db: Session = Depends(get_db)):
    service = StravaService(db)
    try:
        token_data = await service.exchange_code(code)
        athlete_id = service.save_credentials(token_data)
        return {"message": "Strava verbunden", "athlete_id": athlete_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth fehlgeschlagen: {str(e)}")


@router.get("/api/strava/status", response_model=StravaConnected)
def strava_status(db: Session = Depends(get_db)):
    from models import StravaCredentials
    creds = db.query(StravaCredentials).first()
    if creds:
        return StravaConnected(connected=True, athlete_id=creds.athlete_id)
    return StravaConnected(connected=False)
