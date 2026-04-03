import asyncio
import logging
from datetime import datetime, date

import httpx

from core.config import settings
from services.tss_calculator import calculate_tss, calculate_run_tss, hrv_status_from_rmssd

logger = logging.getLogger(__name__)

STRAVA_BASE = "https://www.strava.com/api/v3"


class StravaService:
    def __init__(self, db):
        self.db = db

    def _get_credentials(self, athlete_id: int):
        from models import StravaCredentials
        return self.db.query(StravaCredentials).filter(
            StravaCredentials.athlete_id == athlete_id
        ).first()

    def _update_credentials(self, athlete_id: int, tokens: dict):
        from models import StravaCredentials
        creds = self._get_credentials(athlete_id)
        if creds:
            creds.access_token = tokens["access_token"]
            creds.refresh_token = tokens["refresh_token"]
            creds.expires_at = tokens["expires_at"]
            self.db.commit()

    async def refresh_token_if_needed(self, athlete_id: int) -> str:
        creds = self._get_credentials(athlete_id)
        if creds is None:
            raise ValueError(f"No Strava credentials for athlete {athlete_id}")

        if creds.expires_at < datetime.now().timestamp():
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            "https://www.strava.com/oauth/token",
                            data={
                                "client_id": settings.STRAVA_CLIENT_ID,
                                "client_secret": settings.STRAVA_CLIENT_SECRET,
                                "grant_type": "refresh_token",
                                "refresh_token": creds.refresh_token,
                            },
                        )
                        if resp.status_code == 429:
                            wait = 2 ** attempt
                            logger.warning(f"Strava rate limit hit, waiting {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        new_tokens = resp.json()
                        self._update_credentials(athlete_id, new_tokens)
                        return new_tokens["access_token"]
                except httpx.HTTPStatusError as e:
                    logger.error(f"Token refresh failed: {e}")
                    raise

        return creds.access_token

    async def fetch_activity(self, activity_id: int, athlete_id: int) -> dict:
        token = await self.refresh_token_if_needed(athlete_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{STRAVA_BASE}/activities/{activity_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_activity_streams(self, activity_id: int, athlete_id: int) -> dict:
        token = await self.refresh_token_if_needed(athlete_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{STRAVA_BASE}/activities/{activity_id}/streams",
                params={"keys": "heartrate,watts,velocity_smooth,cadence,time"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                return {}
            resp.raise_for_status()
            data = resp.json()
            return {s["type"]: s["data"] for s in data} if isinstance(data, list) else {}

    def get_auth_url(self, redirect_uri: str) -> str:
        return (
            f"https://www.strava.com/oauth/authorize"
            f"?client_id={settings.STRAVA_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&approval_prompt=force"
            f"&scope=activity:read_all"
        )

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    def save_credentials(self, token_data: dict):
        from models import StravaCredentials
        athlete_id = token_data["athlete"]["id"]
        existing = self._get_credentials(athlete_id)
        if existing:
            existing.access_token = token_data["access_token"]
            existing.refresh_token = token_data["refresh_token"]
            existing.expires_at = token_data["expires_at"]
            self.db.commit()
        else:
            creds = StravaCredentials(
                athlete_id=athlete_id,
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
            )
            self.db.add(creds)
            self.db.commit()
        return athlete_id

    def map_strava_to_session(
        self, activity: dict, streams: dict, ftp: int, week_number: int
    ) -> dict:
        sport = activity.get("sport_type", "").lower()
        if "cycling" in sport or "ride" in sport:
            discipline = "bike"
        elif "run" in sport or "hike" in sport or "walk" in sport:
            discipline = "run"
        elif "swim" in sport:
            discipline = "swim"
        elif any(x in sport for x in ("weight", "workout", "gym", "crossfit", "yoga", "pilates", "strength")):
            discipline = "gym"
        else:
            discipline = sport or "other"

        hr_data = streams.get("heartrate", [])
        power_data = streams.get("watts", [])

        from services.fit_parser import calculate_hr_zones
        hr_zones = calculate_hr_zones(hr_data) if hr_data else None

        moving_time = activity.get("moving_time", 0)
        duration_min = round(moving_time / 60) if moving_time else None

        avg_watts = activity.get("average_watts")
        np_watts = activity.get("weighted_average_watts")
        tss = None
        if power_data and ftp:
            tss = calculate_tss(power_data, ftp, moving_time)
        elif discipline == "run" and activity.get("average_heartrate") and duration_min:
            tss = calculate_run_tss(duration_min, int(activity["average_heartrate"]))

        avg_speed = activity.get("average_speed", 0)
        avg_pace_min_km = None
        if discipline == "run" and avg_speed > 0:
            avg_pace_min_km = round(1000 / avg_speed / 60, 2)

        try:
            session_date = datetime.strptime(
                activity.get("start_date_local", "")[:10], "%Y-%m-%d"
            ).date()
        except Exception:
            session_date = date.today()

        return {
            "session_date": session_date,
            "week_number": week_number,
            "discipline": discipline,
            "duration_min": duration_min,
            "distance_km": round(activity.get("distance", 0) / 1000, 2),
            "avg_hr": int(activity["average_heartrate"]) if activity.get("average_heartrate") else None,
            "max_hr": int(activity["max_heartrate"]) if activity.get("max_heartrate") else None,
            "avg_watts": int(avg_watts) if avg_watts else None,
            "normalized_power": int(np_watts) if np_watts else None,
            "avg_pace_min_km": avg_pace_min_km,
            "tss": round(tss, 1) if tss else None,
            "hr_zones": hr_zones,
            "strava_activity_id": activity.get("id"),
        }
