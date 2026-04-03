from datetime import date, datetime
from pydantic import BaseModel, Field


# --- Athlete Profile ---

class AthleteProfileOut(BaseModel):
    id: int
    name: str | None
    ftp_watts: int
    max_hr: int
    z1_hr_max: int
    z2_hr_min: int
    z2_hr_max: int
    z3_hr_min: int
    z3_hr_max: int
    z4_hr_min: int
    z4_hr_max: int
    race_date: date
    race_goal: str
    plan_start_date: date
    current_week: int | None = None
    updated_at: datetime

    class Config:
        from_attributes = True


class AthleteProfileUpdate(BaseModel):
    name: str | None = None
    ftp_watts: int | None = None
    max_hr: int | None = None
    race_goal: str | None = None


# --- HRV ---

class HrvCreate(BaseModel):
    measured_at: date
    rmssd: float = Field(gt=0, lt=300)
    readiness_score: int | None = Field(None, ge=0, le=100)
    notes: str | None = None


class HrvOut(BaseModel):
    id: int
    measured_at: date
    rmssd: float
    hrv_status: str | None
    readiness_score: int | None
    notes: str | None

    class Config:
        from_attributes = True


# --- Training Session ---

class TrainingSessionOut(BaseModel):
    id: int
    session_date: date
    week_number: int
    discipline: str
    duration_min: int | None
    distance_km: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_watts: int | None
    normalized_power: int | None
    avg_pace_min_km: float | None
    tss: float | None
    rpe: int | None
    hr_zones: dict | None
    streams: dict | None
    strava_activity_id: int | None
    notes: str | None
    created_at: datetime
    deleted_at: datetime | None

    class Config:
        from_attributes = True


class TrainingSessionCreate(BaseModel):
    session_date: date
    discipline: str
    duration_min: int | None = None
    distance_km: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_watts: int | None = None
    normalized_power: int | None = None
    avg_pace_min_km: float | None = None
    tss: float | None = None
    rpe: int | None = None
    notes: str | None = None


# --- Weekly Plan ---

class WeeklyPlanOut(BaseModel):
    id: int
    week_number: int
    week_start: date
    week_end: date
    plan_phase: str | None
    plan_content: dict
    plan_text: str | None
    adjustments_applied: list[str] | None
    generated_at: datetime

    class Config:
        from_attributes = True


# --- Chat ---

class ChatMessageIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    context_week: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: str
    history: list[ChatMessageOut]


# --- Metrics ---

class WeekMetrics(BaseModel):
    week_number: int
    total_tss: float
    sessions_count: int
    total_duration_min: int
    disciplines: dict[str, int]
    avg_hr: float | None
    hr_zones_avg: dict | None
    hrv_latest: float | None
    hrv_status: str | None


class TrendPoint(BaseModel):
    week_number: int
    week_start: date
    total_tss: float
    sessions_count: int


# --- Upload ---

class UploadResponse(BaseModel):
    session_id: int
    message: str
    parsed: dict


# --- Strava ---

class StravaAuthUrl(BaseModel):
    auth_url: str


class StravaConnected(BaseModel):
    connected: bool
    athlete_id: int | None = None
