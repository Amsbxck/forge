from datetime import date, datetime
from sqlalchemy import Integer, String, Float, Date, DateTime, Text, BigInteger, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    ftp_watts: Mapped[int] = mapped_column(Integer, default=238)
    max_hr: Mapped[int] = mapped_column(Integer, default=212)
    z1_hr_max: Mapped[int] = mapped_column(Integer, default=138)
    z2_hr_min: Mapped[int] = mapped_column(Integer, default=139)
    z2_hr_max: Mapped[int] = mapped_column(Integer, default=173)
    z3_hr_min: Mapped[int] = mapped_column(Integer, default=174)
    z3_hr_max: Mapped[int] = mapped_column(Integer, default=189)
    z4_hr_min: Mapped[int] = mapped_column(Integer, default=190)
    z4_hr_max: Mapped[int] = mapped_column(Integer, default=210)
    race_date: Mapped[date] = mapped_column(Date, default=date(2026, 8, 31))
    race_goal: Mapped[str] = mapped_column(String, default="sub 5:30h 70.3")
    plan_start_date: Mapped[date] = mapped_column(Date, default=date(2026, 1, 19))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    discipline: Mapped[str] = mapped_column(String, nullable=False)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)
    avg_watts: Mapped[int | None] = mapped_column(Integer)
    normalized_power: Mapped[int | None] = mapped_column(Integer)
    avg_pace_min_km: Mapped[float | None] = mapped_column(Float)
    tss: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[int | None] = mapped_column(Integer)
    hr_zones: Mapped[dict | None] = mapped_column(JSONB)
    strava_activity_id: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    fit_file_path: Mapped[str | None] = mapped_column(String)
    streams: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HrvMeasurement(Base):
    __tablename__ = "hrv_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    measured_at: Mapped[date] = mapped_column(Date, nullable=False)
    rmssd: Mapped[float] = mapped_column(Float, nullable=False)
    hrv_status: Mapped[str | None] = mapped_column(String)
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    plan_phase: Mapped[str | None] = mapped_column(String)
    plan_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_text: Mapped[str | None] = mapped_column(Text)
    claude_prompt: Mapped[str | None] = mapped_column(Text)
    adjustments_applied: Mapped[list | None] = mapped_column(ARRAY(Text))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_week: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SeasonContext(Base):
    __tablename__ = "season_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)  # z.B. "33-Wochen-Plan", "Schwimmplan KW1-5"
    content_type: Mapped[str] = mapped_column(String, default="text")  # "text" | "pdf"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StravaCredentials(Base):
    __tablename__ = "strava_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(Integer, nullable=False)
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope: Mapped[str] = mapped_column(String, default="activity:read_all")
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
