import asyncio
import logging
from datetime import datetime, date

import httpx

from core.config import settings
from services.tss_calculator import calculate_tss, calculate_run_tss

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

    async def fetch_activity_laps(self, activity_id: int, athlete_id: int) -> list[dict]:
        """Runden einer Aktivität.

        Liefert die tatsächliche Struktur einer Einheit — Einlaufen,
        Intervalle, Pausen, Auslaufen — ohne den Plantext interpretieren zu
        müssen. Fehlen Runden, ist die Liste leer.
        """
        token = await self.refresh_token_if_needed(athlete_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{STRAVA_BASE}/activities/{activity_id}/laps",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []

    @staticmethod
    def compact_laps(laps: list[dict]) -> list[dict]:
        """Nur die Felder behalten, die für die Auswertung zählen."""
        out = []
        for lap in laps:
            distance = round((lap.get("distance") or 0) / 1000, 3)
            moving = int(lap.get("moving_time") or 0)
            if distance <= 0 or moving <= 0:
                continue
            out.append({
                "d": distance,
                "t": moving,
                "hr": round(lap["average_heartrate"]) if lap.get("average_heartrate") else None,
                # Leistung je Runde — beim Rad die einzige Größe, an der sich
                # ein Intervall von einer Erholung unterscheiden lässt.
                "w": round(lap["average_watts"]) if lap.get("average_watts") else None,
            })
        return out

    async def list_activities(
        self, athlete_id: int, after: int | None = None, per_page: int = 50,
        max_seiten: int = 1,
    ) -> list[dict]:
        """Aktivitätsliste vom Athleten.

        Das ist der Weg, der ohne öffentliche Webhook-URL funktioniert:
        verpasste Events lassen sich damit nachträglich einsammeln, weil
        Strava keine Zustellung wiederholt.

        `max_seiten` blättert weiter. Für das stündliche Fenster von zwei
        Wochen genügt eine Seite. Beim erstmaligen Nachholen mehrerer Monate
        nicht: Dort passen mehr Aktivitäten in den Zeitraum, als eine Seite
        fasst, und der Rest fiele stillschweigend weg — ohne Fehler, nur mit
        einer Historie, die vorne abgeschnitten ist.
        """
        token = await self.refresh_token_if_needed(athlete_id)
        gesammelt: list[dict] = []

        async with httpx.AsyncClient(timeout=20.0) as client:
            for seite in range(1, max_seiten + 1):
                params: dict = {"per_page": per_page, "page": seite}
                if after:
                    params["after"] = after
                resp = await client.get(
                    f"{STRAVA_BASE}/athlete/activities",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                teil = resp.json()
                if not isinstance(teil, list):
                    break
                gesammelt.extend(teil)
                # Weniger als angefragt heisst: Das war die letzte Seite.
                if len(teil) < per_page:
                    break

        return gesammelt

    async def list_push_subscriptions(self) -> list[dict]:
        """Health-Check der Webhook-Subscription.

        Braucht kein Athleten-Token, sondern Client-ID und -Secret.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{STRAVA_BASE}/push_subscriptions",
                params={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []

    async def create_push_subscription(self, callback_url: str, verify_token: str) -> dict:
        """Webhook bei Strava registrieren.

        Strava ruft die callback_url sofort zur Prüfung auf — sie muss in
        diesem Moment öffentlich erreichbar sein. Schlägt das fehl, liegt es
        fast immer daran und nicht an den Zugangsdaten.
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{STRAVA_BASE}/push_subscriptions",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "callback_url": callback_url,
                    "verify_token": verify_token,
                },
            )
            if resp.status_code >= 400:
                raise ValueError(resp.text[:400])
            return resp.json()

    async def delete_push_subscription(self, subscription_id: int) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"{STRAVA_BASE}/push_subscriptions/{subscription_id}",
                params={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                },
            )
            if resp.status_code >= 400 and resp.status_code != 404:
                raise ValueError(resp.text[:400])

    def get_auth_url(self, redirect_uri: str, state: str | None = None) -> str:
        """Autorisierungs-URL.

        `state` reicht Strava unverändert an die Rückleitung durch — der
        einzige Weg, dort zu erfahren, für welches Konto die Verbindung gilt.
        """
        from urllib.parse import quote

        url = (
            f"https://www.strava.com/oauth/authorize"
            f"?client_id={settings.STRAVA_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&approval_prompt=force"
            f"&scope=activity:read_all"
        )
        if state:
            url += f"&state={quote(state, safe='')}"
        return url

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
            from core.deps import resolve_user
            user = resolve_user(self.db)
            creds = StravaCredentials(
                user_id=user.id if user else None,
                athlete_id=athlete_id,
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
            )
            self.db.add(creds)
            self.db.commit()
        return athlete_id

    def map_strava_to_session(
        self,
        activity: dict,
        streams: dict,
        ftp: int,
        week_number: int,
        hr_zone_bounds: dict | None = None,
    ) -> dict:
        # Strava kennt rund fünfzig Sportarten und nimmt laufend neue auf.
        # Statt sie einzeln zu pflegen, werden nur die abgebildet, für die
        # die App eine eigene Logik hat; alles andere wird als "other"
        # mitgeführt — mit dem Originalnamen in `sport_type`, damit die
        # Einheit weiter benennbar bleibt.
        sport_raw = activity.get("sport_type") or activity.get("type") or ""
        sport = sport_raw.lower()
        if "cycling" in sport or "ride" in sport or "handcycle" in sport:
            discipline = "bike"
        # Hike/Walk NICHT als Lauf zählen: sonst erzeugt eine Wanderung über
        # calculate_run_tss eine Trainingslast, die es nie gab.
        elif "hike" in sport or "walk" in sport or "snowshoe" in sport:
            discipline = "hike"
        elif "run" in sport:
            discipline = "run"
        elif "swim" in sport:
            discipline = "swim"
        elif any(x in sport for x in ("weight", "workout", "gym", "crossfit", "yoga", "pilates", "strength")):
            discipline = "gym"
        else:
            discipline = "other"

        hr_data = streams.get("heartrate", [])
        power_data = streams.get("watts", [])

        # Laufleistung verwerfen. Sie ist mit Radwatt nicht vergleichbar:
        # gegen die Rad-FTP gerechnet erzeugt ein lockerer Dauerlauf mehr
        # TSS als eine harte Radausfahrt, und im Plan-Vergleich stünde sie
        # neben einem Watt-Zielband, das fürs Rad gedacht ist.
        if discipline in ("run", "hike"):
            power_data = []

        from services.fit_parser import calculate_hr_zones, sample_stream
        hr_zones = calculate_hr_zones(hr_data, hr_zone_bounds) if hr_data else None

        # Rohdaten mitspeichern — ohne sie lassen sich die Zonen nach einer
        # Neukalibrierung nicht nachrechnen, und die Einheit müsste erneut
        # bei Strava abgefragt werden. Gesampelt wie beim FIT-Import.
        stored_streams: dict = {}
        if hr_data:
            stored_streams["hr"] = sample_stream(hr_data)
        if power_data:
            stored_streams["watts"] = sample_stream(power_data)
        speed_data = streams.get("velocity_smooth") or []
        if speed_data:
            stored_streams["speed"] = sample_stream([round(v * 3.6, 2) for v in speed_data])

        moving_time = activity.get("moving_time", 0)
        duration_min = round(moving_time / 60) if moving_time else None

        avg_watts = activity.get("average_watts")
        np_watts = activity.get("weighted_average_watts")
        if discipline in ("run", "hike"):
            avg_watts = np_watts = None

        tss = None
        # Schwellenpuls aus dem Profil statt fest 173. Der bisherige
        # Festwert entsprach genau der Obergrenze von Zone 2 dieses Athleten;
        # diese Konvention wird beibehalten, damit alte und neue TSS-Werte
        # vergleichbar bleiben. Für jeden anderen Athleten war 173 schlicht
        # falsch.
        grenzen = hr_zone_bounds or {}
        # Im Wasser gilt ein eigener Schwellenpuls, sofern gesetzt.
        schwelle = (
            (grenzen.get("swim_threshold_hr") if discipline == "swim" else None)
            or grenzen.get("threshold_hr")
            or grenzen.get("z2_max")
        )
        if power_data and ftp:
            tss = calculate_tss(power_data, ftp, moving_time)
        elif activity.get("average_heartrate") and duration_min and discipline != "rest":
            # Über die Herzfrequenz statt über Leistung: gilt jetzt für jede
            # Sportart mit Pulsaufzeichnung. Vorher bekam nur der Lauf eine
            # TSS, und ein Crosstrainer oder StairMaster tauchte in der
            # Belastungsrechnung überhaupt nicht auf.
            tss = calculate_run_tss(
                duration_min, int(activity["average_heartrate"]),
                threshold_hr=schwelle or 173,
            )

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
            "sport_type": sport_raw or None,
            "hr_zones": hr_zones,
            "streams": stored_streams or None,
            "strava_activity_id": activity.get("id"),
        }
