"""Add streams column to training_sessions

Revision ID: 002
Revises: 001
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_sessions", sa.Column("streams", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("training_sessions", "streams")
