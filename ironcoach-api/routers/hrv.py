from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import HrvMeasurement
from schemas import HrvCreate, HrvOut
from services.tss_calculator import hrv_status_from_rmssd

router = APIRouter()


@router.post("/hrv", response_model=HrvOut)
def create_hrv(data: HrvCreate, db: Session = Depends(get_db)):
    status = hrv_status_from_rmssd(data.rmssd)
    measurement = HrvMeasurement(
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
