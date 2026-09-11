from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pydantic import BaseModel

from database import get_db
from models import HrvMeasurement
from schemas import HrvCreate, HrvOut
from services.hrv_baseline import evaluate as hrv_evaluate
from core.deps import resolve_user

router = APIRouter()


@router.post("/hrv", response_model=HrvOut)
def create_hrv(data: HrvCreate, db: Session = Depends(get_db)):
    # Gegen die eigene Normalspanne statt gegen feste Zahlen. Ohne
    # ausreichende Grundlinie bleibt der Status offen, statt geraten zu werden.
    status, _ = hrv_evaluate(db, data.rmssd)
    user = resolve_user(db)
    measurement = HrvMeasurement(
        user_id=user.id if user else None,
        measured_at=data.measured_at,
        rmssd=data.rmssd,
        hrv_status=status,
        readiness_score=data.readiness_score,
        notes=data.notes,
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return measurement


@router.get("/hrv", response_model=list[HrvOut])
def list_hrv(limit: int = 14, db: Session = Depends(get_db)):
    return (
        db.query(HrvMeasurement)
        .order_by(HrvMeasurement.measured_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/hrv/latest", response_model=HrvOut)
def latest_hrv(db: Session = Depends(get_db)):
    m = db.query(HrvMeasurement).order_by(HrvMeasurement.measured_at.desc()).first()
    if not m:
        raise HTTPException(status_code=404, detail="Keine HRV-Daten vorhanden")
    return m


@router.get("/hrv/range")
def hrv_range(db: Session = Depends(get_db)):
    """Die geltende Normalspanne und woher sie stammt."""
    from core.deps import get_profile
    from services.hrv_baseline import (
        MIN_MESSUNGEN, compute_baseline, thresholds_for,
    )

    profile = get_profile(db)
    baseline = compute_baseline(db)
    grenzen = thresholds_for(profile, baseline)
    return {
        "grenzen": grenzen,
        "baseline": baseline,
        "min_messungen": MIN_MESSUNGEN,
    }


class HrvRangeIn(BaseModel):
    """Spanne von Hand setzen.

    Bevorzugt als grüner Bereich, so wie ihn die Uhr anzeigt (`band_low` bis
    `band_high`) — die rote Grenze wird daraus abgeleitet. Wer die Grenzen
    direkt kennt, kann sie weiterhin einzeln setzen.
    """
    band_low: float | None = None
    band_high: float | None = None
    green_min: float | None = None
    red_below: float | None = None


@router.post("/hrv/range")
def set_hrv_range(body: HrvRangeIn, db: Session = Depends(get_db)):
    from fastapi import HTTPException

    from core.deps import get_profile
    from services.hrv_baseline import recompute_all

    from services.hrv_baseline import red_from_band

    profile = get_profile(db)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")

    if body.band_low is not None and body.band_high is not None:
        if body.band_high <= body.band_low:
            raise HTTPException(
                status_code=422,
                detail="Das obere Ende muss über dem unteren liegen. Vertauscht?",
            )
        gruen, oben = body.band_low, body.band_high
        rot = red_from_band(gruen, oben)
    elif body.green_min is not None and body.red_below is not None:
        if body.red_below >= body.green_min:
            raise HTTPException(
                status_code=422,
                detail="Die rote Grenze muss unter der grünen liegen. Vertauscht?",
            )
        gruen, oben, rot = body.green_min, None, body.red_below
    else:
        raise HTTPException(
            status_code=422,
            detail="Entweder den grünen Bereich (von/bis) oder beide Grenzen angeben",
        )

    profile.hrv_green_min = gruen
    profile.hrv_band_high = oben
    profile.hrv_red_below = rot
    profile.hrv_range_source = "manual"
    db.commit()

    # Bestehende Messungen mitziehen — sonst tragen sie weiter die Farbe der
    # alten Spanne, und der Verlauf widerspricht der neuen Einstellung.
    geaendert = recompute_all(db)
    return {
        "status": "gesetzt",
        "gruen_ab": gruen,
        "gruen_bis": oben,
        "rot_unter": rot,
        "neu_bewertet": geaendert,
    }


@router.delete("/hrv/range")
def clear_hrv_range(db: Session = Depends(get_db)):
    """Zurück zur berechneten Spanne."""
    from fastapi import HTTPException

    from core.deps import get_profile
    from services.hrv_baseline import recompute_all

    profile = get_profile(db)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")
    profile.hrv_green_min = None
    profile.hrv_band_high = None
    profile.hrv_red_below = None
    profile.hrv_range_source = None
    db.commit()
    return {"status": "zurückgesetzt", "neu_bewertet": recompute_all(db)}
