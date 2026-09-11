"""Schwellenpace im Wasser (CSS)

Revision ID: 018
Revises: 017
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("css_pace_s_per_100m", sa.Float, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_source", sa.String, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_t400_s", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_t200_s", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "css_t200_s")
    op.drop_column("athlete_profile", "css_t400_s")
    op.drop_column("athlete_profile", "css_source")
    op.drop_column("athlete_profile", "css_pace_s_per_100m")
