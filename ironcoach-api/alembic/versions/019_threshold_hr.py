"""Schwellenpuls beim Laufen

Revision ID: 019
Revises: 018
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("threshold_hr", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("threshold_source", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "threshold_source")
    op.drop_column("athlete_profile", "threshold_hr")
