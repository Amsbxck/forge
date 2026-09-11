"""A-, B- und C-Rennen

Revision ID: 016
Revises: 015
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "race_goals",
        sa.Column("priority", sa.String, nullable=False, server_default="A"),
    )
    # Bestehende Ziele sind Saisonziele: sie haben die Planung bisher
    # verankert und müssen das weiter tun.
    op.execute("UPDATE race_goals SET priority = 'A'")


def downgrade() -> None:
    op.drop_column("race_goals", "priority")
