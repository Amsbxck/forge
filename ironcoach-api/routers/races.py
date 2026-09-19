"""Wettkampfziele und absolvierte Rennen."""

import os
import re
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.deps import get_current_user
from core.race_types import RACE_TYPES, SPORT_LABEL, default_weeks, plan_start_for
from database import get_db
from models import RaceGoal, RaceResult, User
from schemas import RaceGoalIn, RaceGoalOut, RaceResultIn, RaceResultOut

router = APIRouter()

_TIME_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*$")


def parse_time(value: str | None) -> int | None:
    """"5:28:14" oder "28:14" in Sekunden. Ungültiges wird abgelehnt,
    nicht stillschweigend als 0 gespeichert."""
    if value in (None, ""):
        return None
    match = _TIME_RE.match(str(value))
    if not match:
        raise HTTPException(status_code=422, detail=f"Zeitformat nicht erkannt: {value!r} (erwartet H:MM:SS oder MM:SS)")
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def _validate(sport: str, distance: str, priority: str | None = None) -> None:
    if priority is not None and priority.strip().upper() not in ("A", "B", "C"):
        raise HTTPException(status_code=422, detail=f"Priorität {priority!r} muss A, B oder C sein")
    if sport not in RACE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unbekannte Sportart {sport!r}")
    if distance not in RACE_TYPES[sport]:
        erlaubt = ", ".join(RACE_TYPES[sport])
        raise HTTPException(status_code=422, detail=f"Distanz {distance!r} passt nicht zu {sport} — erlaubt: {erlaubt}")


@router.get("/race-types")
def race_types():
    """Auswahlmöglichkeiten für die Oberfläche."""
    return {
        "sports": [
            {
                "key": sport,
                "label": SPORT_LABEL.get(sport, sport),
                "distances": [
                    {
                        "key": key,
                        "label": config["label"],
                        "weeks": config["weeks"],
                        "legs": {
                            k.replace("_km", ""): v
                            for k, v in config.items() if k.endswith("_km")
                        },
                    }
                    for key, config in distances.items()
                ],
            }
            for sport, distances in RACE_TYPES.items()
        ]
    }


# --- Ziele -------------------------------------------------------------------

@router.get("/goals", response_model=list[RaceGoalOut])
def list_goals(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    query = db.query(RaceGoal).order_by(RaceGoal.race_date.desc())
    if user:
        query = query.filter(RaceGoal.user_id == user.id)
    return query.all()


@router.get("/goals/active", response_model=RaceGoalOut)
def active_goal(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    goal = get_active_goal(db, user)
    if goal is None:
        raise HTTPException(status_code=404, detail="Kein aktives Ziel gesetzt")
    return goal


def get_active_goal(db: Session, user: User | None = None) -> RaceGoal | None:
    """Das Saisonziel. B- und C-Rennen kommen hier nicht in Frage."""
    query = db.query(RaceGoal).filter(
        RaceGoal.is_active == True,  # noqa: E712
        RaceGoal.priority == "A",
    )
    if user:
        query = query.filter(RaceGoal.user_id == user.id)
    return query.order_by(RaceGoal.race_date.asc()).first()


@router.get("/goals/upcoming", response_model=list[RaceGoalOut])
def upcoming_races(
    # Ein Jahr voraus: eine Saison kann über 30 Wochen laufen, und ein
    # Wettkampf im März wäre bei einem kürzeren Fenster im September
    # unsichtbar gewesen.
    days: int = 365,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Wettkämpfe unterwegs — alles außer dem Saisonziel."""
    from datetime import date as _date, timedelta as _td

    from services.race_calendar import secondary_races

    heute = _date.today()
    return secondary_races(db, user, von=heute, bis=heute + _td(days=days))


@router.post("/goals", response_model=RaceGoalOut)
def create_goal(
    body: RaceGoalIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    _validate(body.sport, body.distance, body.priority)

    from services.race_calendar import normalize_priority

    prioritaet = normalize_priority(body.priority)
    weeks = body.plan_weeks or default_weeks(body.sport, body.distance)

    if prioritaet == "A":
        start = body.plan_start_date or plan_start_for(body.race_date, weeks)
        # Nur ein aktives Saisonziel: sonst wäre unklar, worauf sich die
        # Wochenzählung und die Phasenlogik beziehen. B- und C-Rennen bleiben
        # unangetastet — sie gehören zur selben Saison.
        query = db.query(RaceGoal).filter(
            RaceGoal.is_active == True,  # noqa: E712
            RaceGoal.priority == "A",
        )
        if user:
            query = query.filter(RaceGoal.user_id == user.id)
        for existing in query.all():
            existing.is_active = False
    else:
        # Ein Zwischenwettkampf trägt keinen eigenen Planstart: die Woche,
        # in die er fällt, wird über das Saisonziel gezählt.
        start = None
        weeks = None

    goal = RaceGoal(
        user_id=user.id if user else None,
        sport=body.sport,
        distance=body.distance,
        race_date=body.race_date,
        race_name=body.race_name,
        goal_time=body.goal_time,
        priority=prioritaet,
        plan_weeks=weeks,
        plan_start_date=start,
        is_active=True,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.patch("/goals/{goal_id}", response_model=RaceGoalOut)
def update_goal(goal_id: int, body: dict, db: Session = Depends(get_db)):
    goal = db.query(RaceGoal).filter(RaceGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Ziel nicht gefunden")
    for key in ("race_name", "goal_time", "race_date", "plan_weeks", "plan_start_date", "is_active"):
        if key in body:
            setattr(goal, key, body[key])
    if "sport" in body or "distance" in body:
        sport = body.get("sport", goal.sport)
        distance = body.get("distance", goal.distance)
        _validate(sport, distance)
        goal.sport, goal.distance = sport, distance
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/goals/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Ziel oder Wettkampf entfernen."""
    query = db.query(RaceGoal).filter(RaceGoal.id == goal_id)
    if user:
        query = query.filter(RaceGoal.user_id == user.id)
    goal = query.first()
    if not goal:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    db.delete(goal)
    db.commit()
    return {"message": "gelöscht"}


# --- Ergebnisse --------------------------------------------------------------

@router.get("/races", response_model=list[RaceResultOut])
def list_races(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    query = db.query(RaceResult).order_by(RaceResult.race_date.desc())
    if user:
        query = query.filter(RaceResult.user_id == user.id)
    return query.all()


@router.post("/races", response_model=RaceResultOut)
def create_race(
    body: RaceResultIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    _validate(body.sport, body.distance)
    result = RaceResult(
        user_id=user.id if user else None,
        race_date=body.race_date,
        race_name=body.race_name,
        sport=body.sport,
        distance=body.distance,
        location=body.location,
        finish_time_s=parse_time(body.finish_time),
        swim_time_s=parse_time(body.swim_time),
        t1_time_s=parse_time(body.t1_time),
        bike_time_s=parse_time(body.bike_time),
        t2_time_s=parse_time(body.t2_time),
        run_time_s=parse_time(body.run_time),
        overall_rank=body.overall_rank,
        age_group_rank=body.age_group_rank,
        age_group=body.age_group,
        finishers=body.finishers,
        notes=body.notes,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


@router.patch("/races/{race_id}", response_model=RaceResultOut)
def update_race(
    race_id: int,
    body: RaceResultIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Eingetragenes Rennen korrigieren.

    Vollständige Ersetzung statt Teilaktualisierung: Das Formular schickt
    ohnehin alle Felder, und ein geleertes Feld soll den Wert löschen —
    bei einer Teilaktualisierung wäre nicht unterscheidbar, ob ein Feld
    fehlt oder absichtlich geleert wurde. Das Foto bleibt unberührt.
    """
    _validate(body.sport, body.distance)

    query = db.query(RaceResult).filter(RaceResult.id == race_id)
    if user:
        query = query.filter(RaceResult.user_id == user.id)
    race = query.first()
    if not race:
        raise HTTPException(status_code=404, detail="Rennen nicht gefunden")

    race.race_date = body.race_date
    race.race_name = body.race_name
    race.sport = body.sport
    race.distance = body.distance
    race.location = body.location
    race.finish_time_s = parse_time(body.finish_time)
    race.swim_time_s = parse_time(body.swim_time)
    race.t1_time_s = parse_time(body.t1_time)
    race.bike_time_s = parse_time(body.bike_time)
    race.t2_time_s = parse_time(body.t2_time)
    race.run_time_s = parse_time(body.run_time)
    race.overall_rank = body.overall_rank
    race.age_group_rank = body.age_group_rank
    race.age_group = body.age_group
    race.finishers = body.finishers
    race.notes = body.notes

    db.commit()
    db.refresh(race)
    return race


# Nur Formate, die jeder Browser darstellt. Geprüft wird an den ersten Bytes,
# nicht am Dateinamen oder am gemeldeten Content-Type — beides kann lügen.
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"RIFF": ("image/webp", ".webp"),
}
MAX_IMAGE_MB = 8


def _detect_image(data: bytes) -> tuple[str, str]:
    for signature, (mime, suffix) in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            if signature == b"RIFF" and data[8:12] != b"WEBP":
                continue
            return mime, suffix
    raise HTTPException(status_code=422, detail="Nur JPEG, PNG oder WebP")


def _race_or_404(db: Session, race_id: int) -> RaceResult:
    race = db.query(RaceResult).filter(RaceResult.id == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail="Rennen nicht gefunden")
    return race


def _image_dir() -> str:
    path = os.path.join(settings.UPLOAD_DIR, "races")
    os.makedirs(path, exist_ok=True)
    return path


@router.post("/races/{race_id}/image", response_model=RaceResultOut)
async def upload_race_image(
    race_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Foto zum Rennen hinterlegen."""
    race = _race_or_404(db, race_id)

    data = await file.read()
    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Bild zu groß (max {MAX_IMAGE_MB} MB)")
    _, suffix = _detect_image(data[:16])

    # Dateiname aus einem Zufallswert, nicht aus dem hochgeladenen Namen:
    # der kann Pfadanteile enthalten und wäre erratbar.
    name = f"{race.id}-{secrets.token_hex(8)}{suffix}"
    with open(os.path.join(_image_dir(), name), "wb") as target:
        target.write(data)

    old = race.image_file
    race.image_file = name
    db.commit()
    db.refresh(race)

    if old and old != name:
        try:
            os.remove(os.path.join(_image_dir(), old))
        except OSError:
            pass  # verwaistes Bild ist harmlos, ein Absturz hier nicht

    return race


@router.get("/races/{race_id}/image")
def get_race_image(race_id: int, db: Session = Depends(get_db)):
    """Foto ausliefern — nur an den Besitzer.

    Der Zugriff geht über die Datenbank, nicht über den Dateipfad: so greift
    der Mandantenfilter, und fremde Fotos sind selbst bei bekanntem Namen
    nicht erreichbar.
    """
    race = _race_or_404(db, race_id)
    if not race.image_file:
        raise HTTPException(status_code=404, detail="Kein Bild hinterlegt")

    path = os.path.join(_image_dir(), race.image_file)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Bilddatei fehlt")
    return FileResponse(path, media_type=_detect_image(open(path, "rb").read(16))[0])


@router.delete("/races/{race_id}/image", response_model=RaceResultOut)
def delete_race_image(race_id: int, db: Session = Depends(get_db)):
    race = _race_or_404(db, race_id)
    if race.image_file:
        try:
            os.remove(os.path.join(_image_dir(), race.image_file))
        except OSError:
            pass
        race.image_file = None
        db.commit()
        db.refresh(race)
    return race


@router.get("/benchmark/week")
def benchmark_preview(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Vorschau der Testwoche für das aktive Ziel."""
    from datetime import date as _date, timedelta

    from core.deps import get_active_goal
    from services.benchmark import benchmark_week

    goal = get_active_goal(db, user)
    sport = goal.sport if goal else "triathlon"
    start = goal.plan_start_date if goal and goal.plan_start_date else _date.today()
    # Auf Montag ziehen, damit die Woche zur Wochenzählung passt.
    start = start - timedelta(days=start.weekday())
    return {"sport": sport, "week_start": str(start), "days": benchmark_week(sport, start)}


@router.get("/benchmark/timing")
def benchmark_timing(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Darf die Testwoche in der kommenden Woche liegen?

    Eigener Endpunkt, damit die Oberfläche den Grund **vor** dem Klick zeigen
    kann. Erst nach dem Anlegen zu erfahren, dass es nicht geht, wäre eine
    vermeidbare Sackgasse.
    """
    from core.deps import get_active_goal
    from services.benchmark_timing import pruefe

    goal = get_active_goal(db, user)
    lage = pruefe(db, getattr(goal, "race_date", None))
    return {
        "moeglich": lage["moeglich"],
        "start": str(lage["start"]) if lage["start"] else None,
        "frueheste": str(lage["frueheste"]) if lage["frueheste"] else None,
        "gruende": lage["gruende"],
    }


@router.post("/benchmark/plan")
def benchmark_plan(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Testwoche als echten Wochenplan anlegen — für die kommende Woche."""
    from services.benchmark import BenchmarkGesperrt, create_benchmark_plan

    try:
        plan, created = create_benchmark_plan(db, user)
    except BenchmarkGesperrt as e:
        # 409 statt 422: Die Anfrage ist richtig, nur der Zeitpunkt nicht.
        # Der Ersatztermin geht mit, damit die Oberfläche etwas anbieten kann.
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Testwoche jetzt nicht sinnvoll",
                "gruende": e.lage["gruende"],
                "frueheste": str(e.lage["frueheste"]) if e.lage["frueheste"] else None,
            },
        )

    return {
        "created": created,
        "plan_id": plan.id,
        "week_number": plan.week_number,
        "week_start": str(plan.week_start),
        # Die Woche über ihr Datum benennen, nicht über die Wochennummer:
        # Die entsteht aus `max(1, …)` und ist vor dem Beginn der
        # Vorbereitung für jedes Datum 1. Die Meldung sagte dann "für Woche 1
        # existiert bereits ein Plan" und nannte im selben Atemzug ein Datum
        # aus dem September — zwei Angaben, die sich widersprechen.
        "message": (
            "Testwoche angelegt" if created
            else f"Für die Woche ab {plan.week_start} existiert bereits ein Plan"
        ),
    }


@router.post("/benchmark/derive")
def benchmark_derive(
    apply: bool = False,
    days: int = 21,
    db: Session = Depends(get_db),
):
    """Zonen aus den Testeinheiten ableiten.

    Standardmäßig nur Vorschau — Zonen sind die Grundlage jeder späteren
    Bewertung und sollen nicht versehentlich überschrieben werden.
    """
    from services.benchmark import derive_zones

    return derive_zones(db, days=days, apply=apply)


@router.delete("/races/{race_id}")
def delete_race(race_id: int, db: Session = Depends(get_db)):
    result = db.query(RaceResult).filter(RaceResult.id == race_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Rennen nicht gefunden")
    db.delete(result)
    db.commit()
    return {"message": "gelöscht"}


@router.get("/onboarding/status")
def onboarding_status(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Wo steht der Athlet auf dem Weg zum ersten Plan?"""
    from services.onboarding import status

    return status(db, user)
