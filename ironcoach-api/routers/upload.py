import os
import shutil
from datetime import date
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import AthleteProfile, TrainingSession
from schemas import UploadResponse
from services.fit_parser import parse_fit_file, parse_gpx_file
from services.plan_generator import get_week_for_date
from core.config import settings
from core.deps import get_profile

router = APIRouter()

ALLOWED_EXTENSIONS = {".fit", ".gpx"}


def _ablage(user_id: int | None, ext: str) -> str:
    """Ein sicherer Ablagepfad: eigener Ordner je Nutzer, Name vom Server.

    Vorher wurde der Dateiname des Browsers übernommen. Mit „../" landete die
    Datei außerhalb des Upload-Ordners, und zwei Nutzer mit „Morning_Run.gpx"
    (Strava benennt Exporte nach dem Titel) überschrieben einander — scheiterte
    das Einlesen, löschte `os.remove` sogar die Datei des anderen.
    """
    import uuid

    basis = os.path.realpath(settings.UPLOAD_DIR)
    ordner = os.path.join(basis, str(user_id) if user_id is not None else "ohne_nutzer")
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.realpath(os.path.join(ordner, f"{uuid.uuid4().hex}{ext}"))
    if not pfad.startswith(basis + os.sep):  # pragma: no cover - kann nicht eintreten
        raise HTTPException(status_code=400, detail="Ungültiger Ablagepfad")
    return pfad


def _vorhandene_einheit(db: Session, parsed: dict) -> TrainingSession | None:
    """Dieselbe Einheit schon da? Gleicher Tag, Sportart und ähnliche Dauer.

    Dieselbe Regel wie beim Strava-Import (`ingest._durations_match`), nur in
    beide Richtungen: Eine Datei kann nach Strava kommen oder davor. Vorher
    legte jeder Upload eine neue Einheit an — dieselbe Datei zweimal ergab
    doppelte TSS.
    """
    from services.ingest import _durations_match

    kandidaten = db.query(TrainingSession).filter(
        TrainingSession.session_date == parsed["session_date"],
        TrainingSession.discipline == parsed["discipline"],
        TrainingSession.deleted_at == None,  # noqa: E711
    ).all()
    for k in kandidaten:
        if _durations_match(k.duration_min, parsed.get("duration_min")):
            return k
    return None


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from core.deps import get_plan_anchor
    from services.ingest import nachbearbeiten

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Nur .fit und .gpx Dateien erlaubt. Erhalten: {ext}")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Datei zu groß (max {settings.MAX_UPLOAD_SIZE_MB}MB)")

    profile = get_profile(db)
    user_id = profile.user_id if profile else None
    file_path = _ablage(user_id, ext)
    with open(file_path, "wb") as f:
        f.write(content)

    # Keine Ersatz-FTP: Hier stand 238 W, die Schwelle eines einzelnen
    # Athleten. Ohne Profil keine leistungsbasierte TSS.
    ftp = profile.ftp_watts if profile else None
    max_hr = profile.max_hr if profile else None

    try:
        from services.fit_parser import zones_from_profile

        if ext == ".fit":
            parsed = parse_fit_file(
                file_path, ftp=ftp, max_hr=max_hr,
                hr_zone_bounds=zones_from_profile(profile),
            )
        else:
            parsed = parse_gpx_file(file_path, hr_zone_bounds=zones_from_profile(profile))
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Datei konnte nicht geparst werden: {str(e)}")

    session_date = parsed["session_date"]
    # Über den Anker (Saisonziel, sonst Profil) wie beim Strava-Import —
    # vorher immer über das Profil, und dieselbe Einheit bekam je nach Weg
    # eine andere Wochennummer.
    anker = get_plan_anchor(db)
    week_number = get_week_for_date(anker, session_date) if anker else 1

    try:
        vorhanden = _vorhandene_einheit(db, parsed)
        if vorhanden is not None:
            # Ergänzen statt verdoppeln: Die Datei ist die genauere Quelle für
            # Ströme und Leistung, die vorhandene Einheit behält ihre
            # Zuordnung, Reflexion und Strava-ID.
            for feld in ("avg_watts", "normalized_power", "avg_hr", "max_hr",
                         "distance_km", "avg_pace_min_km", "hr_zones", "streams"):
                if getattr(vorhanden, feld, None) in (None, {}) and parsed.get(feld) is not None:
                    setattr(vorhanden, feld, parsed[feld])
            if not vorhanden.fit_file_path:
                vorhanden.fit_file_path = file_path
            else:
                os.remove(file_path)
            db.commit()
            session = vorhanden
            meldung = (f"Diese Einheit gab es schon ({parsed['discipline']}, "
                       f"{session_date}) — fehlende Werte wurden ergänzt")
        else:
            session = TrainingSession(
                user_id=user_id,
                session_date=session_date,
                week_number=week_number,
                discipline=parsed["discipline"],
                duration_min=parsed.get("duration_min"),
                distance_km=parsed.get("distance_km"),
                avg_hr=parsed.get("avg_hr"),
                max_hr=parsed.get("max_hr"),
                avg_watts=parsed.get("avg_watts"),
                normalized_power=parsed.get("normalized_power"),
                avg_pace_min_km=parsed.get("avg_pace_min_km"),
                tss=parsed.get("tss"),
                hr_zones=parsed.get("hr_zones"),
                streams=parsed.get("streams"),
                fit_file_path=file_path,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            meldung = f"Einheit erfolgreich gespeichert ({parsed['discipline']})"
    except Exception:
        # Keine verwaiste Datei, wenn die Datenbank scheitert.
        db.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    # Zuordnen, Zonen ableiten, Vault — wie beim Strava-Import.
    await nachbearbeiten(db, session, {})

    return UploadResponse(
        session_id=session.id,
        message=meldung,
        parsed={k: str(v) if isinstance(v, date) else v for k, v in parsed.items()},
    )
