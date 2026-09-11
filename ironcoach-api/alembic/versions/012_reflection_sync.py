"""Abgleichsmarke für die Reflexion

Revision ID: 012
Revises: 011
Create Date: 2026-09-02

Die Reflexion kann an zwei Orten entstehen: in der App und in der Note. Ohne
festzuhalten, welche Fassung zuletzt abgeglichen wurde, ließe sich nicht
erkennen, welche Seite sich geändert hat — die jeweils andere ginge verloren.
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_sessions", sa.Column("reflection_sync_hash", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("training_sessions", "reflection_sync_hash")
