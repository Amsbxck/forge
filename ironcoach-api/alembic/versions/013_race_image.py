"""Foto am Rennergebnis

Revision ID: 013
Revises: 012
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("race_results", sa.Column("image_file", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("race_results", "image_file")
