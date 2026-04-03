"""Add season_context table

Revision ID: 004
Revises: 003
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "season_context",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("content_type", sa.String, default="text"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("filename", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("season_context")
