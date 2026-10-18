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
from core.wochen import montag_von
from database import get_db
from models import RaceGoal, RaceResult, User
from schemas import RaceGoalIn, RaceGoalOut, RaceGoalPatch, RaceResultIn, RaceResultOut


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


# Eine Abfrage für „das Saisonziel", nicht drei: Hier stand eine eigene
# Kopie, eine weitere in `services/race_calendar.py` (ohne Sortierung).
from core.deps import get_active_goal  # noqa: E402


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
        # Auch ein selbst gewählter Start wird auf seinen Montag gezogen. Die
        # Wochenansicht sucht über `week_start == Montag der Kalenderwoche`;
        # ein Start an einem Dienstag legt jede Planwoche daneben, und der
        # Athlet sieht für keine Woche einen Plan.
        start = (
            montag_von(body.plan_start_date) if body.plan_start_date
            else plan_start_for(body.race_date, weeks)
        )
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
def update_goal(
    goal_id: int,
    body: RaceGoalPatch,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Ein Ziel ändern — mit denselben Folgen wie beim Anlegen.

    Vorher wurden die Felder einzeln übernommen, ohne die Folgen:
      * Ein verschobenes Renndatum ließ den Planstart stehen; das Rennen lag
        danach in „Woche 24 von 20", und die Wochen davor hießen Off Season.
      * Sportart oder Distanz behielten die alte Planlänge.
      * `is_active: true` machte ein zweites Saisonziel aktiv, ohne das erste
        zu beenden — welches dann zählte, hing am früheren Datum.
    """
    from services.race_calendar import normalize_priority

    query = db.query(RaceGoal).filter(RaceGoal.id == goal_id)
    if user is not None:
        query = query.filter(RaceGoal.user_id == user.id)
    goal = query.first()
    if not goal:
        raise HTTPException(status_code=404, detail="Ziel nicht gefunden")

    daten = body.model_dump(exclude_unset=True)
    if "plan_start_date" in daten and daten["plan_start_date"] is None:
        raise HTTPException(
            status_code=422,
            detail="Der Planstart lässt sich ändern, aber nicht leeren — ohne ihn "
                   "gibt es keine Wochenzählung.",
        )

    sport = daten.get("sport", goal.sport)
    distance = daten.get("distance", goal.distance)
    _validate(sport, distance, daten.get("priority"))
    prioritaet = normalize_priority(daten["priority"]) if daten.get("priority") else goal.priority
    art_geaendert = sport != goal.sport or distance != goal.distance

    for feld in ("race_name", "goal_time", "race_date"):
        if feld in daten and (daten[feld] is not None or feld != "race_date"):
            setattr(goal, feld, daten[feld])
    goal.sport, goal.distance, goal.priority = sport, distance, prioritaet

    if prioritaet == "A":
        # Planlänge: ausdrücklich angegeben, sonst bei geänderter Art die
        # Vorgabe der neuen Art, sonst wie bisher.
        if daten.get("plan_weeks"):
            goal.plan_weeks = daten["plan_weeks"]
        elif art_geaendert or not goal.plan_weeks:
            goal.plan_weeks = default_weeks(sport, distance)
        # Planstart: ausdrücklich angegeben (auf seinen Montag gezogen), sonst
        # neu aus Renndatum und Länge, sobald sich eines davon geändert hat.
        if daten.get("plan_start_date"):
            goal.plan_start_date = montag_von(daten["plan_start_date"])
        elif {"race_date", "plan_weeks", "sport", "distance"} & daten.keys() or goal.plan_start_date is None:
            goal.plan_start_date = plan_start_for(goal.race_date, goal.plan_weeks)
    else:
        goal.plan_weeks = None
        goal.plan_start_date = None

    if "is_active" in daten and daten["is_active"] is not None:
        goal.is_active = daten["is_active"]
    # Nur ein aktives Saisonziel, wie beim Anlegen.
    if goal.is_active and prioritaet == "A":
        andere = db.query(RaceGoal).filter(
            RaceGoal.id != goal.id,
            RaceGoal.is_active == True,  # noqa: E712
            RaceGoal.priority == "A",
        )
        if goal.user_id is not None:
            andere = andere.filter(RaceGoal.user_id == goal.user_id)
        for anderes in andere.all():
            anderes.is_active = False

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
    """Vorschau der Testwoche — genau so, wie sie angelegt würde.

    Dieselbe Woche und dieselbe Entzerrung wie `create_benchmark_plan`. Vorher
    rechnete die Vorschau ab dem Planstart des Ziels (meist Monate zurück) und
    ohne die Off-Season-Entzerrung: Sie zeigte zwei Maximaltests, wo dann einer
    angelegt wurde, und Daten aus einer vergangenen Woche.
    """
    from core.deps import get_active_goal
    from core.race_types import season_state
    from services.benchmark import benchmark_week
    from services.benchmark_timing import entzerren, naechster_montag

    goal = get_active_goal(db, user)
    sport = goal.sport if goal else "triathlon"
    start = naechster_montag()
    days = benchmark_week(sport, start)
    if goal is None or season_state(goal.race_date) == "off_season":
        days = entzerren(days)
    return {"sport": sport, "week_start": str(start), "days": days}


@router.get("/benchmark/timing")
def benchmark_timing(db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    """Darf die Testwoche in der kommenden Woche liegen?

    Eigener Endpunkt, damit die Oberfläche den Grund **vor** dem Klick zeigen
    kann. Erst nach dem Anlegen zu erfahren, dass es nicht geht, wäre eine
    vermeidbare Sackgasse.
    """
    from datetime import date as _date

    from core.deps import get_active_goal, get_profile
    from services.benchmark_timing import (
        faelligkeit, letzte_testwoche, pruefe,
    )

    goal = get_active_goal(db, user)
    profil = get_profile(db, user)
    gemessen = getattr(profil, "zones_updated_at", None)
    uid = user.id if user else getattr(profil, "user_id", None)
    testwoche = letzte_testwoche(db, user_id=uid)
    lage = pruefe(
        db, getattr(goal, "race_date", None),
        gemessen_am=gemessen.date() if gemessen else None,
        testwoche_am=testwoche,
    )
    # Eine geplante (oder laufende) Testwoche — die Oberfläche zeigt dann
    # „geplant ab …" statt eines Knopfs, der nur eine Sperre auslöst.
    geplant_ab = (
        testwoche if testwoche and testwoche >= montag_von(_date.today()) else None
    )

    stand = faelligkeit(gemessen.date() if gemessen else None)
    return {
        "moeglich": lage["moeglich"],
        "start": str(lage["start"]) if lage["start"] else None,
        "frueheste": str(lage["frueheste"]) if lage["frueheste"] else None,
        "gruende": lage["gruende"],
        "geplant_ab": str(geplant_ab) if geplant_ab else None,
        # Wann der nächste Test ansteht. Die Oberfläche zeigt das an, damit
        # niemand erst beim Anlegen erfährt, dass es noch zu früh ist — und
        # damit die Woche vorher freigehalten werden kann.
        "faellig_am": str(stand["faellig_am"]) if stand["faellig_am"] else None,
        "tage_bis_faellig": stand["tage_hin"],
        # Keine Mahnung „Testwoche steht an", solange eine geplant ist — sie
        # forderte sonst zu etwas auf, das schon erledigt ist.
        "vorwarnung": (
            stand["text"] if stand["vorwarnung"] and not geplant_ab else None
        ),
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
        # Die entstand früher aus `max(1, …)` und war vor dem Beginn der
        # Vorbereitung für jedes Datum 1. Die Meldung sagte dann "für Woche 1
        # existiert bereits ein Plan" und nannte im selben Atemzug ein Datum
        # aus dem September — zwei Angaben, die sich widersprechen.
        "message": (
            "Testwoche angelegt und inzwischen wieder storniert"
            if getattr(plan, "storniert", False)
            else "Testwoche angelegt" if created
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
