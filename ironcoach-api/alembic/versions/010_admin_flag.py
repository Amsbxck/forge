"""Betreiber-Kennzeichen am Nutzer

Revision ID: 010
Revises: 009
Create Date: 2026-09-02

Der Strava-Webhook gilt für die gesamte Anwendung — Strava erlaubt genau eine
Subscription. Ohne diese Unterscheidung könnte jeder Athlet die Registrierung
für alle anderen ändern.

Der erste Nutzer ist der Betreiber; neue Konten sind es nicht.
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute("UPDATE users SET is_admin = true WHERE id = (SELECT min(id) FROM users)")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
