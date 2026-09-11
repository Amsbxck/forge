"""Add planned_sessions + Ist/Soll- und Obsidian-Felder auf training_sessions

Revision ID: 005
Revises: 004
Create Date: 2026-08-11

Hinweis: Der Unique-Index auf strava_activity_id ist partiell (WHERE NOT NULL),
damit manuell angelegte Einheiten ohne Strava-ID weiterhin erlaubt sind.
Er schlägt fehl, falls bereits doppelte Aktivitäten in der Tabelle stehen —
vor dem Upgrade prüfen:

    SELECT strava_activity_id, count(*) FROM training_sessions
    WHERE strava_activity_id IS NOT NULL AND deleted_at IS NULL
    GROUP BY 1 HAVING count(*) > 1;
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer,
            sa.ForeignKey("weekly_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("planned_date", sa.Date, nullable=False),
        sa.Column("day_name", sa.String, nullable=True),
        sa.Column("discipline", sa.String, nullable=False),
        sa.Column("training_type", sa.String, nullable=True),
        sa.Column("duration_min", sa.Integer, nullable=True),
        sa.Column("target_tss", sa.Float, nullable=True),
        sa.Column("target_watts_low", sa.Integer, nullable=True),
        sa.Column("target_watts_high", sa.Integer, nullable=True),
        sa.Column("target_pace_low_s_per_km", sa.Integer, nullable=True),
        sa.Column("target_pace_high_s_per_km", sa.Integer, nullable=True),
        sa.Column("target_hr_zone", sa.String, nullable=True),
        sa.Column("target_distance_km", sa.Float, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="planned"),
        sa.Column("moved_from_date", sa.Date, nullable=True),
        sa.Column("matched_session_id", sa.Integer, nullable=True),
        sa.Column("day_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_planned_sessions_plan_id", "planned_sessions", ["plan_id"])
    op.create_index("ix_planned_sessions_date", "planned_sessions", ["planned_date"])
    op.create_index("ix_planned_sessions_week", "planned_sessions", ["week_number"])

    # Ist/Soll-Abgleich
    op.add_column("training_sessions", sa.Column("actual_type", sa.String, nullable=True))
    op.add_column("training_sessions", sa.Column("planned_session_id", sa.Integer, nullable=True))
    op.add_column("training_sessions", sa.Column("match_confidence", sa.Float, nullable=True))
    op.add_column("training_sessions", sa.Column("deviation_note", sa.Text, nullable=True))

    # Obsidian-Sync
    op.add_column("training_sessions", sa.Column("obsidian_path", sa.String, nullable=True))
    op.add_column("training_sessions", sa.Column("obsidian_synced_at", sa.DateTime, nullable=True))
    op.add_column("training_sessions", sa.Column("obsidian_content_hash", sa.String, nullable=True))

    # Zyklische FKs erst nach Anlage beider Tabellen
    op.create_foreign_key(
        "fk_training_sessions_planned_session",
        "training_sessions",
        "planned_sessions",
        ["planned_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_planned_sessions_matched_session",
        "planned_sessions",
        "training_sessions",
        ["matched_session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Idempotenz auf DB-Ebene: Webhook und Reconcile-Job können dieselbe
    # Aktivität nicht doppelt anlegen, auch nicht bei paralleler Ausführung.
    op.create_index(
        "uq_training_sessions_strava_activity_id",
        "training_sessions",
        ["strava_activity_id"],
        unique=True,
        postgresql_where=sa.text("strava_activity_id IS NOT NULL"),
    )
    op.create_index(
        "ix_training_sessions_obsidian_pending",
        "training_sessions",
        ["obsidian_synced_at"],
        postgresql_where=sa.text("obsidian_synced_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_training_sessions_obsidian_pending", table_name="training_sessions")
    op.drop_index("uq_training_sessions_strava_activity_id", table_name="training_sessions")
    op.drop_constraint("fk_planned_sessions_matched_session", "planned_sessions", type_="foreignkey")
    op.drop_constraint("fk_training_sessions_planned_session", "training_sessions", type_="foreignkey")

    for col in (
        "obsidian_content_hash",
        "obsidian_synced_at",
        "obsidian_path",
        "deviation_note",
        "match_confidence",
        "planned_session_id",
        "actual_type",
    ):
        op.drop_column("training_sessions", col)

    op.drop_index("ix_planned_sessions_week", table_name="planned_sessions")
    op.drop_index("ix_planned_sessions_date", table_name="planned_sessions")
    op.drop_index("ix_planned_sessions_plan_id", table_name="planned_sessions")
    op.drop_table("planned_sessions")
