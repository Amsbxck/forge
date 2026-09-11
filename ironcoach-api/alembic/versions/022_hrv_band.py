"""Oberes Ende des grünen HRV-Bereichs

Revision ID: 022
Revises: 021
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("hrv_band_high", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "hrv_band_high")
