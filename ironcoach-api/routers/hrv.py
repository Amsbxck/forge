from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import HrvMeasurement
from schemas import HrvCreate, HrvOut
from services.hrv_baseline import evaluate as hrv_evaluate
from core.deps import resolve_user

router = APIRouter()


@router.post("/hrv", response_model=HrvOut)
def create_hrv(data: HrvCreate, db: Session = Depends(get_db)):
    from core.deps import get_profile

    user = resolve_user(db)
    # Mit Garmin kommt die HRV automatisch. Eine Handeingabe daneben würde
    # am nächsten Morgen ohnehin von Garmins Wert überschrieben (Garmin ist
    # die Quelle) — sie anzunehmen hieße, etwas zu speichern, das gleich
    # wieder verschwindet. Ohne Garmin bleibt die Handeingabe: Athleten ohne
    # Garmin-Uhr hätten sonst gar keine HRV.
    profile = get_profile(db, user)
    if profile is not None and profile.garmin_api_key:
        raise HTTPException(status_code=409, detail="HRV kommt automatisch aus Garmin Connect")

    # Gegen die eigene Normalspanne statt gegen feste Zahlen. Ohne
    # ausreichende Grundlinie bleibt der Status offen, statt geraten zu werden.
    status, _ = hrv_evaluate(db, data.rmssd)
    measurement = HrvMeasurement(
        user_id=user.id if user else None,
        measured_at=data.measured_at,
        rmssd=data.rmssd,
        hrv_status=status,
        readiness_score=data.readiness_score,
        notes=data.notes,
        quelle="manual",
    )
    db.add(measurement)
    db.commit()

    # Fortlaufend nachziehen: Jede neue Messung verschiebt Mittelwert und
    # Streuung ein wenig, also auch die Normalspanne. Ohne das trug die neue
    # Messung die heutige Spanne und jede ältere die von damals — im
    # Verlaufsdiagramm lägen Punkte in Farben, die zur eingezeichneten Spanne
    # nicht passen. Ein paar hundert Zeilen neu zu bewerten kostet nichts.
    from services.hrv_baseline import recompute_all

    try:
        recompute_all(db, user)
    except Exception as e:  # pragma: no cover - darf das Eintragen nie reissen
        import logging
        logging.getLogger(__name__).warning("Grundlinie nicht nachgezogen: %s", e)
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
        BAND_SIGMA, FENSTER_TAGE, MAX_MESSUNGEN, MIN_MESSUNGEN,
        compute_baseline, thresholds_for,
    )

    profile = get_profile(db)
    baseline = compute_baseline(db)
    grenzen = thresholds_for(profile, baseline)
    return {
        "grenzen": grenzen,
        "baseline": baseline,
        # Die Regeln der Rechnung mitliefern, nicht nur ihr Ergebnis. Das
        # Diagramm zeichnet die Spanne je Tag mit, und es muss dafür dasselbe
        # Fenster und dieselbe Streuungsbreite verwenden — sonst zeigt es eine
        # Rechnung, die es hier nicht gibt.
        "min_messungen": MIN_MESSUNGEN,
        "max_messungen": MAX_MESSUNGEN,
        "fenster_tage": FENSTER_TAGE,
        "band_sigma": BAND_SIGMA,
        # Für das Dashboard: Mit Garmin entfällt die Handeingabe. Hier statt in
        # einem eigenen Aufruf, weil das Dashboard diesen Endpunkt ohnehin lädt.
        "garmin_verbunden": bool(profile is not None and profile.garmin_api_key),
    }


# `POST /hrv/range` und `DELETE /hrv/range` sind entfernt. Die Spanne kommt
# aus Garmin Connect (`services/garmin_hrv.spanne_uebernehmen`, sonntags und
# beim Verbinden) und ist nicht mehr von Hand änderbar. Eine früher von Hand
# eingetragene Spanne gilt weiter (siehe `hrv_baseline.thresholds_for`).
