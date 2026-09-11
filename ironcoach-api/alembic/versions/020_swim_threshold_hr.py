"""Schwellenpuls im Wasser

Revision ID: 020
Revises: 019
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("swim_threshold_hr", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("swim_threshold_source", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "swim_threshold_source")
    op.drop_column("athlete_profile", "swim_threshold_hr")
