"""Reflexion an der Trainingseinheit

Revision ID: 011
Revises: 010
Create Date: 2026-09-02

Reflexionen lagen ausschließlich in Obsidian. Damit war ein Vault faktisch
Voraussetzung dafür, dass der Coach den subjektiven Teil überhaupt zu sehen
bekommt — wer keinen betreibt, bekam Pläne allein aus Messwerten.

Das Feld ist die Quelle für alle; Obsidian bleibt die angenehmere
Schreibfläche und gewinnt beim Abgleich, wenn dort etwas steht.
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_sessions", sa.Column("reflection", sa.Text, nullable=True))
    op.add_column("training_sessions", sa.Column("reflection_updated_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("training_sessions", "reflection_updated_at")
    op.drop_column("training_sessions", "reflection")
