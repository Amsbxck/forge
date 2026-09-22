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
    threshold_hr: int | None = None
    threshold_pace_s_per_km: int | None = None
    threshold_source: str | None = None
    # Herkunft der Zonen und Zeitpunkt der letzten Messung. Beides stand im
    # Profil, wurde aber nie ausgeliefert — die Oberfläche konnte deshalb
    # nicht zeigen, ob Werte gemessen oder eingetragen sind, und wann der
    # nächste Test fällig wird.
    zones_source: str | None = None
    ftp_source: str | None = None
    zones_updated_at: datetime | None = None
    css_pace_s_per_100m: float | None = None
    css_source: str | None = None
    swim_threshold_hr: int | None = None
    swim_threshold_source: str | None = None
    hrv_green_min: float | None = None
    hrv_band_high: float | None = None
    hrv_red_below: float | None = None
    hrv_range_source: str | None = None
    intake_done_at: datetime | None = None
    css_t400_s: int | None = None
    css_t200_s: int | None = None
    css_dist_lang_m: int | None = None
    css_dist_kurz_m: int | None = None
    current_week: int | None = None
    # Dauer und Renntag stammen aus dem aktiven Saisonziel, sofern eines
    # gesetzt ist — im Profil stehen nur Platzhalter aus der Registrierung.
    total_weeks: int | None = None
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
    # Ursprüngliche Bezeichnung, wenn die Sportart keiner Kategorie entspricht
    # (StairStepper, Rowing, Elliptical …).
    sport_type: str | None = None
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

    # Ergebnis der Klassifizierung — ohne diese Felder sieht das Frontend
    # nichts davon, obwohl es in der Datenbank steht.
    actual_type: str | None = None
    intensity: str | None = None
    intensity_label: str | None = None
    planned_session_id: int | None = None
    match_confidence: float | None = None
    deviation_note: str | None = None
    obsidian_path: str | None = None
    obsidian_synced_at: datetime | None = None
    reflection: str | None = None
    reflection_updated_at: datetime | None = None

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


# --- Geplante Einheiten (normalisierte Projektion von plan_content) ---

class PlannedSessionOut(BaseModel):
    id: int
    plan_id: int
    week_number: int
    planned_date: date
    day_name: str | None
    discipline: str
    training_type: str | None
    intensity: str | None = None
    intensity_label: str | None = None
    duration_min: int | None
    target_tss: float | None
    target_watts_low: int | None
    target_watts_high: int | None
    target_pace_low_s_per_km: int | None
    target_pace_high_s_per_km: int | None
    target_hr_zone: str | None
    target_distance_km: float | None
    details: dict | None
    notes: str | None
    status: str
    replacement: str | None = None
    replacement_min: int | None = None
    moved_from_date: date | None
    matched_session_id: int | None
    day_index: int

    class Config:
        from_attributes = True


class PlannedSessionPatch(BaseModel):
    """Teilaktualisierung einer geplanten Einheit (Drag & Drop, manuelle Korrektur)."""
    planned_date: date | None = None
    discipline: str | None = None
    training_type: str | None = None
    duration_min: int | None = None
    notes: str | None = None
    status: str | None = None


class PlannedReplacementIn(BaseModel):
    """Statt der geplanten Einheit wurde etwas anderes gemacht.

    `text` ist bewusst frei: Was jemand stattdessen tut, lässt sich nicht
    vorab aufzählen. `duration_min` ist optional, weil man nach einer
    Wanderung selten auf die Uhr geschaut hat — fehlt sie, gilt der Ersatz
    trotzdem, nur ohne Umfangsangabe.
    """
    text: str
    duration_min: int | None = None


class PlannedSwapIn(BaseModel):
    """Zwei Einheiten tauschen ihre Termine — ein Drop im Wochenkalender."""
    a_id: int
    b_id: int


# --- Wettkampfziele und Ergebnisse ---

class RaceGoalIn(BaseModel):
    # A, B oder C. Ohne Angabe ein Saisonziel — das ist der häufigste Fall
    # und das bisherige Verhalten.
    priority: str = "A"
    sport: str
    distance: str
    race_date: date
    race_name: str | None = None
    goal_time: str | None = None
    plan_weeks: int | None = None
    plan_start_date: date | None = None


class RaceGoalOut(BaseModel):
    id: int
    sport: str
    distance: str
    label: str
    # A = Saisonziel (verankert die Planung), B/C = Wettkämpfe unterwegs.
    priority: str = "A"
    race_date: date
    race_name: str | None
    goal_time: str | None
    plan_weeks: int | None
    plan_start_date: date | None
    total_weeks: int
    is_active: bool

    class Config:
        from_attributes = True


class RaceResultIn(BaseModel):
    race_date: date
    race_name: str
    sport: str
    distance: str
    location: str | None = None
    # Zeiten dürfen als "5:28:14" kommen — der Router rechnet sie in Sekunden um.
    finish_time: str | None = None
    swim_time: str | None = None
    t1_time: str | None = None
    bike_time: str | None = None
    t2_time: str | None = None
    run_time: str | None = None
    overall_rank: int | None = None
    age_group_rank: int | None = None
    age_group: str | None = None
    finishers: int | None = None
    notes: str | None = None


class RaceResultOut(BaseModel):
    id: int
    race_date: date
    race_name: str
    sport: str
    distance: str
    label: str
    location: str | None
    finish_time_s: int | None
    swim_time_s: int | None
    t1_time_s: int | None
    bike_time_s: int | None
    t2_time_s: int | None
    run_time_s: int | None
    overall_rank: int | None
    age_group_rank: int | None
    age_group: str | None
    finishers: int | None
    notes: str | None
    image_file: str | None = None

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
    phase: str | None = None
    # Saison vorbei? Dann zeigt die Oberfläche Off Season statt einer
    # Wochennummer, die auf ein bereits gelaufenes Rennen hinzählt.
    # base_period = Ziel gesetzt, Aufbau beginnt erst später
    season_state: str = "preparation"   # base_period | preparation | race_week | off_season
    plan_start_date: date | None = None
    race_date: date | None = None
    total_weeks: int | None = None
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
