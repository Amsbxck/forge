"""Persönliche HRV-Spanne

Revision ID: 021
Revises: 020
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("hrv_green_min", sa.Float, nullable=True))
    op.add_column("athlete_profile", sa.Column("hrv_red_below", sa.Float, nullable=True))
    op.add_column("athlete_profile", sa.Column("hrv_range_source", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "hrv_range_source")
    op.drop_column("athlete_profile", "hrv_red_below")
    op.drop_column("athlete_profile", "hrv_green_min")
