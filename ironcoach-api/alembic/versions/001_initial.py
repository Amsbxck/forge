"""Initial schema with athlete profile seed

Revision ID: 001
Revises:
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "athlete_profile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String),
        sa.Column("ftp_watts", sa.Integer, default=238),
        sa.Column("max_hr", sa.Integer, default=212),
        sa.Column("z1_hr_max", sa.Integer, default=138),
        sa.Column("z2_hr_min", sa.Integer, default=139),
        sa.Column("z2_hr_max", sa.Integer, default=173),
        sa.Column("z3_hr_min", sa.Integer, default=174),
        sa.Column("z3_hr_max", sa.Integer, default=189),
        sa.Column("z4_hr_min", sa.Integer, default=190),
        sa.Column("z4_hr_max", sa.Integer, default=210),
        sa.Column("race_date", sa.Date, default="2026-08-31"),
        sa.Column("race_goal", sa.String, default="sub 5:30h 70.3"),
        sa.Column("plan_start_date", sa.Date, default="2025-12-22"),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("discipline", sa.String, nullable=False),
        sa.Column("duration_min", sa.Integer),
        sa.Column("distance_km", sa.Float),
        sa.Column("avg_hr", sa.Integer),
        sa.Column("max_hr", sa.Integer),
        sa.Column("avg_watts", sa.Integer),
        sa.Column("normalized_power", sa.Integer),
        sa.Column("avg_pace_min_km", sa.Float),
        sa.Column("tss", sa.Float),
        sa.Column("rpe", sa.Integer),
        sa.Column("hr_zones", JSONB),
        sa.Column("strava_activity_id", sa.BigInteger),
        sa.Column("notes", sa.Text),
        sa.Column("fit_file_path", sa.String),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "hrv_measurements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("measured_at", sa.Date, nullable=False),
        sa.Column("rmssd", sa.Float, nullable=False),
        sa.Column("hrv_status", sa.String),
        sa.Column("readiness_score", sa.Integer),
        sa.Column("notes", sa.Text),
    )

    op.create_table(
        "weekly_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("week_end", sa.Date, nullable=False),
        sa.Column("plan_phase", sa.String),
        sa.Column("plan_content", JSONB, nullable=False),
        sa.Column("plan_text", sa.Text),
        sa.Column("claude_prompt", sa.Text),
        sa.Column("adjustments_applied", ARRAY(sa.Text)),
        sa.Column("generated_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("context_week", sa.Integer),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "strava_credentials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("athlete_id", sa.Integer, nullable=False),
        sa.Column("access_token", sa.String, nullable=False),
        sa.Column("refresh_token", sa.String, nullable=False),
        sa.Column("expires_at", sa.BigInteger, nullable=False),
        sa.Column("scope", sa.String, default="activity:read_all"),
        sa.Column("connected_at", sa.DateTime, default=sa.func.now()),
    )

    # Seed: Athletenprofil mit Amirs Werten vorbelegen
    op.execute("""
        INSERT INTO athlete_profile (
            name, ftp_watts, max_hr,
            z1_hr_max, z2_hr_min, z2_hr_max,
            z3_hr_min, z3_hr_max, z4_hr_min, z4_hr_max,
            race_date, race_goal, plan_start_date, updated_at
        ) VALUES (
            'Amir', 238, 212,
            138, 139, 173,
            174, 189, 190, 210,
            '2026-08-31', 'sub 5:30h 70.3', '2026-01-19', NOW()
        ) ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("strava_credentials")
    op.drop_table("chat_messages")
    op.drop_table("weekly_plans")
    op.drop_table("hrv_measurements")
    op.drop_table("training_sessions")
    op.drop_table("athlete_profile")
