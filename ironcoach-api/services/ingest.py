"""Ein einziger Weg, auf dem eine Strava-Aktivität ins System kommt.

Webhook und Reconcile-Job rufen beide `ingest_activity()`. Zwei getrennte
Codepfade würden garantiert auseinanderdriften — einer bekäme irgendwann
die Obsidian-Anbindung, der andere nicht.

Das Kernproblem beim Nachziehen: rund zwei Drittel der bestehenden Einheiten
stammen aus FIT-Uploads und haben keine `strava_activity_id`. Der Unique-Index
greift dort nicht. Würde der Job stumpf einfügen, entstünden Dubletten für
jede Einheit, die längst da ist. Deshalb das zweistufige Matching:

  1. exakt über strava_activity_id
  2. sonst über Datum + Sportart + ähnliche Dauer, bei Einheiten ohne
     Strava-ID → dann wird **verknüpft**, nicht neu angelegt
"""

import logging
from datetime import date as _date, datetime

from sqlalchemy.orm import Session

from models import AthleteProfile, TrainingSession
from services.plan_generator import get_week_for_date
from services.strava_service import StravaService
from core.deps import get_profile, get_plan_anchor

logger = logging.getLogger(__name__)

# Toleranz beim Zuordnen: die Dauer aus einem FIT-File und Stravas moving_time
# weichen regelmäßig um ein paar Minuten ab (Pausenerkennung).
DURATION_TOLERANCE_MIN = 5
DURATION_TOLERANCE_PCT = 0.10


def _parse_activity_date(activity: dict) -> _date:
    try:
        return datetime.strptime(activity.get("start_date_local", "")[:10], "%Y-%m-%d").date()
    except Exception:
        return _date.today()


def _durations_match(a: int | None, b: int | None) -> bool:
    if not a or not b:
        return False
    tolerance = max(DURATION_TOLERANCE_MIN, round(max(a, b) * DURATION_TOLERANCE_PCT))
    return abs(a - b) <= tolerance


def find_existing_session(
    db: Session, activity_id: int, session_data: dict
) -> tuple[TrainingSession | None, str]:
    """Bestehende Einheit zu einer Strava-Aktivität finden.

    Gibt (Einheit, Grund) zurück. Grund ist 'strava_id' bei exaktem Treffer,
    'heuristic' bei Zuordnung über Datum/Sportart/Dauer.
    """
    exact = db.query(TrainingSession).filter(
        TrainingSession.strava_activity_id == activity_id
    ).first()
    if exact:
        return exact, "strava_id"

    candidates = db.query(TrainingSession).filter(
        TrainingSession.session_date == session_data["session_date"],
        TrainingSession.discipline == session_data["discipline"],
        TrainingSession.strava_activity_id == None,  # noqa: E711
        TrainingSession.deleted_at == None,  # noqa: E711
    ).all()

    for candidate in candidates:
        if _durations_match(candidate.duration_min, session_data.get("duration_min")):
            return candidate, "heuristic"

    # Genau eine Einheit an dem Tag in der Sportart, aber Dauer passt nicht:
    # trotzdem zuordnen wäre zu riskant — lieber als neu behandeln und im
    # Log sichtbar machen.
    if candidates:
        logger.info(
            "Aktivität %s: %s Kandidat(en) am %s (%s), aber keine Dauer passt — wird neu angelegt",
            activity_id, len(candidates), session_data["session_date"], session_data["discipline"],
        )
    return None, "none"


async def ingest_activity(
    db: Session,
    activity_id: int,
    athlete_id: int,
    sync_obsidian: bool = True,
    dry_run: bool = False,
) -> dict:
    """Eine Strava-Aktivität einlesen — idempotent.

    dry_run meldet nur, was passieren würde, ohne zu schreiben.
    """
    service = StravaService(db)
    profile = get_profile(db)
    ftp = profile.ftp_watts if profile else 238

    activity = await service.fetch_activity(activity_id, athlete_id)
    session_date = _parse_activity_date(activity)
    anchor = get_plan_anchor(db)
    week_number = get_week_for_date(anchor, session_date) if anchor else 1

    # Streams sind teuer (eigener Request) — beim Dry-Run nicht nötig.
    streams = {} if dry_run else await service.fetch_activity_streams(activity_id, athlete_id)

    # Runden für Lauf und Rad: dort tragen sie die Struktur (Ein-/Ausfahren,
    # Intervalle, Pausen), die im Durchschnitt der Einheit verschwindet.
    # Ein Radintervall bei 210 W verschwindet sonst hinter 188 W Schnitt.
    laps: list[dict] = []
    sport = (activity.get("sport_type") or "").lower()
    is_run = "run" in sport and "hike" not in sport
    is_ride = "ride" in sport or "cycling" in sport
    # Schwimmen kommt dazu: dort tragen die Runden die Teststrecken des
    # CSS-Tests (400 m und 200 m). Ohne sie lässt sich die Schwellenpace im
    # Wasser nicht ableiten.
    is_swim = "swim" in sport
    if not dry_run and (is_run or is_ride or is_swim):
        try:
            laps = service.compact_laps(await service.fetch_activity_laps(activity_id, athlete_id))
        except Exception as e:
            logger.warning("Runden für Aktivität %s nicht ladbar: %s", activity_id, e)
    from services.fit_parser import zones_from_profile
    session_data = service.map_strava_to_session(
        activity, streams, ftp, week_number, hr_zone_bounds=zones_from_profile(profile)
    )
    if laps:
        session_data["streams"] = {**(session_data.get("streams") or {}), "laps": laps}

    existing, reason = find_existing_session(db, activity_id, session_data)

    if existing and reason == "strava_id":
        return {
            "activity_id": activity_id, "action": "skipped_duplicate",
            "session_id": existing.id, "date": str(session_date),
        }

    if existing and reason == "heuristic":
        result = {
            "activity_id": activity_id, "action": "linked", "session_id": existing.id,
            "date": str(session_date), "discipline": session_data["discipline"],
            "duration_db": existing.duration_min, "duration_strava": session_data.get("duration_min"),
        }
        if dry_run:
            return result
        # Nur die Strava-ID nachtragen und fehlende Messwerte auffüllen.
        # Vorhandene Werte bleiben stehen: die FIT-Datei ist die genauere Quelle.
        existing.strava_activity_id = activity_id
        for field in ("avg_watts", "normalized_power", "avg_hr", "max_hr",
                      "distance_km", "tss", "avg_pace_min_km", "hr_zones"):
            if getattr(existing, field, None) is None and session_data.get(field) is not None:
                setattr(existing, field, session_data[field])
        db.commit()
        logger.info("Aktivität %s mit bestehender Einheit %s verknüpft", activity_id, existing.id)
        session = existing
    else:
        result = {
            "activity_id": activity_id, "action": "created", "date": str(session_date),
            "discipline": session_data["discipline"],
            "duration": session_data.get("duration_min"),
        }
        if dry_run:
            return result
        from core.deps import resolve_user
        user = resolve_user(db)
        session = TrainingSession(user_id=user.id if user else None, **session_data)
        db.add(session)
        db.commit()
        result["session_id"] = session.id
        logger.info("Aktivität %s als Einheit %s angelegt", activity_id, session.id)

    # Erst klassifizieren, dann nach Obsidian — sonst stünde in der Note ein
    # leeres actual_type und die Abweichung fehlte.
    try:
        from services.classification import classify_session
        classification = classify_session(db, session)
        result["actual_type"] = classification["actual_type"]
        result["deviation"] = classification["deviation"]
    except Exception as e:  # pragma: no cover
        logger.warning("Klassifizierung für Einheit %s fehlgeschlagen: %s", session.id, e)

    # In der Testphase die Zonen aus den Tests übernehmen — der Sinn der
    # Benchmark-Woche ist, dass danach niemand Zahlen von Hand eintragen muss.
    try:
        from services.benchmark import maybe_autoderive
        derived = maybe_autoderive(db)
        if derived:
            result["zones_derived"] = derived.get("applied")
    except Exception as e:  # pragma: no cover
        logger.warning("Automatische Zonenableitung fehlgeschlagen: %s", e)

    if sync_obsidian:
        try:
            from services.obsidian.sync import sync_session
            result["obsidian"] = sync_session(db, session)["status"]
        except Exception as e:  # pragma: no cover - darf den Ingest nie reißen
            logger.warning("Obsidian-Sync für Einheit %s fehlgeschlagen: %s", session.id, e)
            result["obsidian"] = "error"

    return result
