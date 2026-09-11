"""Merker für die Guthabenwarnung

Revision ID: 024
Revises: 023
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("api_warned_at", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "api_warned_at")
