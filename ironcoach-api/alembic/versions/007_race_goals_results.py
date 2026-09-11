"""Wettkampfziele und Rennergebnisse

Revision ID: 007
Revises: 006
Create Date: 2026-09-02

Das Ziel stand bisher als zwei Felder im Profil (race_date, race_goal) und
die Saisonstruktur als Konstanten im Code. Mit einer eigenen Tabelle lassen
sich Sportart und Distanz wählen, mehrere Ziele nacheinander verfolgen und
absolvierte Rennen festhalten.

Das bestehende Ziel wird aus dem Profil übernommen, damit die laufende
Vorbereitung nahtlos weiterläuft. Die Profilfelder bleiben vorerst bestehen —
sie werden erst entfernt, wenn kein Codepfad sie mehr liest.
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "race_goals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sport", sa.String, nullable=False),
        sa.Column("distance", sa.String, nullable=False),
        sa.Column("race_date", sa.Date, nullable=False),
        sa.Column("race_name", sa.String, nullable=True),
        sa.Column("goal_time", sa.String, nullable=True),
        sa.Column("plan_weeks", sa.Integer, nullable=True),
        sa.Column("plan_start_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_race_goals_user_id", "race_goals", ["user_id"])

    op.create_table(
        "race_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("goal_id", sa.Integer, sa.ForeignKey("race_goals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("race_date", sa.Date, nullable=False),
        sa.Column("race_name", sa.String, nullable=False),
        sa.Column("sport", sa.String, nullable=False),
        sa.Column("distance", sa.String, nullable=False),
        sa.Column("location", sa.String, nullable=True),
        sa.Column("finish_time_s", sa.Integer, nullable=True),
        sa.Column("swim_time_s", sa.Integer, nullable=True),
        sa.Column("t1_time_s", sa.Integer, nullable=True),
        sa.Column("bike_time_s", sa.Integer, nullable=True),
        sa.Column("t2_time_s", sa.Integer, nullable=True),
        sa.Column("run_time_s", sa.Integer, nullable=True),
        sa.Column("overall_rank", sa.Integer, nullable=True),
        sa.Column("age_group_rank", sa.Integer, nullable=True),
        sa.Column("age_group", sa.String, nullable=True),
        sa.Column("finishers", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_race_results_user_id", "race_results", ["user_id"])

    # Bestehendes Ziel aus dem Profil übernehmen. Die Distanz wird aus dem
    # Zieltext erraten; trifft nichts zu, bleibt es bei der Mitteldistanz,
    # weil das dem bisherigen 70.3-Aufbau entspricht.
    connection = op.get_bind()
    profile = connection.execute(
        sa.text(
            "SELECT user_id, race_date, race_goal, plan_start_date "
            "FROM athlete_profile ORDER BY id LIMIT 1"
        )
    ).mappings().first()

    if profile and profile["race_date"]:
        goal_text = (profile["race_goal"] or "").lower()
        if "140.6" in goal_text or "ironman" in goal_text and "70.3" not in goal_text:
            distance = "full"
        elif "olymp" in goal_text:
            distance = "olympic"
        elif "sprint" in goal_text:
            distance = "sprint"
        elif "marathon" in goal_text and "halb" not in goal_text:
            distance = "marathon"
        elif "halbmarathon" in goal_text or "half" in goal_text:
            distance = "half_marathon"
        else:
            distance = "middle"

        sport = "running" if distance in ("10k", "half_marathon", "marathon") else "triathlon"

        connection.execute(
            sa.text(
                "INSERT INTO race_goals "
                "(user_id, sport, distance, race_date, goal_time, plan_start_date, plan_weeks, is_active) "
                "VALUES (:uid, :sport, :dist, :rdate, :goal, :pstart, :weeks, true)"
            ),
            {
                "uid": profile["user_id"],
                "sport": sport,
                "dist": distance,
                "rdate": profile["race_date"],
                "goal": profile["race_goal"],
                "pstart": profile["plan_start_date"],
                # Aus dem tatsächlichen Zeitraum ableiten, nicht aus der
                # Empfehlung — der laufende Plan soll seine Wochenzählung behalten.
                "weeks": (
                    (profile["race_date"] - profile["plan_start_date"]).days // 7 + 1
                    if profile["plan_start_date"] else None
                ),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_race_results_user_id", table_name="race_results")
    op.drop_table("race_results")
    op.drop_index("ix_race_goals_user_id", table_name="race_goals")
    op.drop_table("race_goals")
