import os
import shutil
from datetime import date
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import AthleteProfile, TrainingSession
from schemas import UploadResponse
from services.fit_parser import parse_fit_file, parse_gpx_file
from services.plan_generator import get_current_week
from core.config import settings

router = APIRouter()

ALLOWED_EXTENSIONS = {".fit", ".gpx"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Nur .fit und .gpx Dateien erlaubt. Erhalten: {ext}")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Datei zu groß (max {settings.MAX_UPLOAD_SIZE_MB}MB)")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = file.filename.replace(" ", "_") if file.filename else "upload"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    profile = db.query(AthleteProfile).first()
    ftp = profile.ftp_watts if profile else 238
    max_hr = profile.max_hr if profile else None

    try:
        if ext == ".fit":
            parsed = parse_fit_file(file_path, ftp=ftp, max_hr=max_hr)
        else:
            parsed = parse_gpx_file(file_path)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Datei konnte nicht geparst werden: {str(e)}")

    current_week = get_current_week(profile) if profile else 1

    session = TrainingSession(
        session_date=parsed["session_date"],
        week_number=current_week,
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

    return UploadResponse(
        session_id=session.id,
        message=f"Einheit erfolgreich gespeichert ({parsed['discipline']})",
        parsed={k: str(v) if isinstance(v, date) else v for k, v in parsed.items()},
    )
