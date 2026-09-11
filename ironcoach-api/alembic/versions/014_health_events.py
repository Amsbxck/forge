"""Krankheits- und Verletzungsereignisse

Revision ID: 014
Revises: 013
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("kind", sa.String, nullable=False, server_default="illness"),
        sa.Column("severity", sa.String, nullable=False, server_default="mild"),
        sa.Column("fever", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    # Zwei offene Krankmeldungen gleichzeitig ergeben keinen Sinn und würden
    # die Auswertung mehrdeutig machen.
    op.create_index(
        "ix_health_events_open",
        "health_events",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_health_events_open", table_name="health_events")
    op.drop_table("health_events")
