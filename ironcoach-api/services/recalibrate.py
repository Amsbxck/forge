"""HF-Zonen neu kalibrieren und die Historie nachrechnen.

Anlass: die Zonen im Profil standen auf einer Maximalherzfrequenz von 212,
tatsächlich gemessen wurden nie mehr als 203. Zone 5 (>210) lag damit über
dem physisch Erreichbaren und war in 82 Einheiten kein einziges Mal belegt —
jede VO₂max-Einheit wurde zwangsläufig als Threshold eingestuft.

Der Lauf ist idempotent: mehrfaches Ausführen ändert nichts am Ergebnis.
"""

import logging

from sqlalchemy.orm import Session

from models import AthleteProfile, StravaCredentials, TrainingSession
from services.fit_parser import calculate_hr_zones, sample_stream, zones_from_profile
from core.deps import get_profile

logger = logging.getLogger(__name__)


def apply_profile_zones(db: Session, max_hr: int, zones: dict, commit: bool = True) -> dict:
    """Neue Zonengrenzen ins Athletenprofil schreiben."""
    profile = get_profile(db)
    if profile is None:
        return {"status": "no_profile"}

    before = {
        "max_hr": profile.max_hr,
        "z1_max": profile.z1_hr_max,
        "z2": [profile.z2_hr_min, profile.z2_hr_max],
        "z3": [profile.z3_hr_min, profile.z3_hr_max],
        "z4": [profile.z4_hr_min, profile.z4_hr_max],
    }

    profile.max_hr = max_hr
    profile.z1_hr_max = zones["z1_max"]
    profile.z2_hr_min = zones["z1_max"] + 1
    profile.z2_hr_max = zones["z2_max"]
    profile.z3_hr_min = zones["z2_max"] + 1
    profile.z3_hr_max = zones["z3_max"]
    profile.z4_hr_min = zones["z3_max"] + 1
    profile.z4_hr_max = zones["z4_max"]

    if commit:
        db.commit()

    return {
        "status": "updated",
        "before": before,
        "after": {
            "max_hr": profile.max_hr,
            "z1_max": profile.z1_hr_max,
            "z2": [profile.z2_hr_min, profile.z2_hr_max],
            "z3": [profile.z3_hr_min, profile.z3_hr_max],
            "z4": [profile.z4_hr_min, profile.z4_hr_max],
        },
    }


async def fetch_missing_streams(db: Session, limit: int = 100) -> dict:
    """HF-Streams für Strava-Einheiten nachladen, die keine gespeichert haben.

    Betrifft alle Einheiten, die vor der Stream-Ablage eingelesen wurden.
    Ohne sie lassen sich ihre Zonen nach einer Neukalibrierung nicht neu
    berechnen.
    """
    creds = db.query(StravaCredentials).first()
    if not creds:
        return {"status": "no_credentials", "fetched": 0}

    from services.strava_service import StravaService
    service = StravaService(db)

    candidates = [
        s for s in db.query(TrainingSession).filter(
            TrainingSession.strava_activity_id != None,  # noqa: E711
            TrainingSession.deleted_at == None,  # noqa: E711
        ).order_by(TrainingSession.session_date.desc()).limit(limit).all()
        if not (s.streams or {}).get("hr")
    ]

    fetched, failed = 0, 0
    for session in candidates:
        try:
            streams = await service.fetch_activity_streams(
                session.strava_activity_id, creds.athlete_id
            )
        except Exception as e:
            logger.warning("Streams für Einheit %s nicht ladbar: %s", session.id, e)
            failed += 1
            continue

        stored = dict(session.streams or {})
        if streams.get("heartrate"):
            stored["hr"] = sample_stream(streams["heartrate"])
        if streams.get("watts"):
            stored["watts"] = sample_stream(streams["watts"])
        if streams.get("velocity_smooth"):
            stored["speed"] = sample_stream([round(v * 3.6, 2) for v in streams["velocity_smooth"]])

        if stored:
            session.streams = stored
            fetched += 1

    db.commit()
    return {"status": "ok", "candidates": len(candidates), "fetched": fetched, "failed": failed}


def strip_run_power(db: Session, commit: bool = True) -> dict:
    """Laufleistung entfernen und TSS aus der Herzfrequenz neu berechnen.

    Bis hierher wurde die von der Uhr gemeldete Laufleistung gespeichert und
    gegen die Rad-FTP in TSS umgerechnet. Ein lockerer Dauerlauf bei HF 128
    kam so auf 105 TSS — mehr als eine harte Radeinheit. Diese Werte
    verzerren Wochenlast, Trends und jeden Coaching-Prompt.
    """
    from services.tss_calculator import calculate_run_tss

    profile = get_profile(db)
    threshold_hr = int((profile.max_hr if profile and profile.max_hr else 203) * 0.88)

    sessions = db.query(TrainingSession).filter(
        TrainingSession.discipline.in_(("run", "hike")),
        TrainingSession.deleted_at == None,  # noqa: E711
    ).all()

    cleared, retssed = 0, 0
    changes = []
    for session in sessions:
        had_power = session.avg_watts is not None or session.normalized_power is not None
        if had_power:
            session.avg_watts = None
            session.normalized_power = None
            cleared += 1
        if session.streams and "watts" in session.streams:
            streams = dict(session.streams)
            streams.pop("watts", None)
            session.streams = streams

        # TSS neu: Wanderungen bekommen keine, Läufe aus der HF.
        old_tss = session.tss
        if session.discipline == "hike":
            new_tss = None
        elif session.avg_hr and session.duration_min:
            new_tss = round(calculate_run_tss(session.duration_min, session.avg_hr, threshold_hr), 1)
        else:
            new_tss = None

        if new_tss != old_tss:
            session.tss = new_tss
            retssed += 1
            changes.append({
                "date": str(session.session_date),
                "duration": session.duration_min,
                "avg_hr": session.avg_hr,
                "tss_before": old_tss,
                "tss_after": new_tss,
            })

    if commit:
        db.commit()

    return {
        "status": "ok",
        "threshold_hr": threshold_hr,
        "sessions": len(sessions),
        "power_cleared": cleared,
        "tss_recomputed": retssed,
        "changes": changes,
    }


def recompute_hr_zones(db: Session, commit: bool = True) -> dict:
    """hr_zones aller Einheiten mit den aktuellen Profilgrenzen neu berechnen."""
    profile = get_profile(db)
    bounds = zones_from_profile(profile)
    if bounds is None:
        return {"status": "no_profile"}

    sessions = db.query(TrainingSession).filter(
        TrainingSession.deleted_at == None  # noqa: E711
    ).all()

    changed, skipped, gained_z5 = 0, 0, 0
    for session in sessions:
        hr = (session.streams or {}).get("hr")
        if not hr:
            skipped += 1
            continue
        new_zones = calculate_hr_zones(hr, bounds)
        old_zones = session.hr_zones or {}
        if new_zones != old_zones:
            if (new_zones.get("z5") or 0) > 0 and (old_zones.get("z5") or 0) == 0:
                gained_z5 += 1
            session.hr_zones = new_zones
            changed += 1

    if commit:
        db.commit()

    return {
        "status": "ok",
        "bounds": bounds,
        "sessions": len(sessions),
        "recomputed": changed,
        "skipped_no_stream": skipped,
        "newly_with_z5": gained_z5,
    }
