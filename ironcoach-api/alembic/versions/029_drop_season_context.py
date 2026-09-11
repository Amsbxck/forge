"""Saisonkontext entfernen.

Die Tabelle nahm hochgeladene Referenzpläne und Saisonnotizen auf, die dem
Coach als zusätzlicher Kontext dienen sollten. Der Weg dorthin war nie
erreichbar — der Router war nicht eingebunden —, und die Funktion wird auch
nicht gebraucht: Die Pläne entstehen in der App selbst, aus dem eigenen
Trainingsverlauf. Ein fremder Referenzplan daneben wäre ein zweiter, nicht
abgestimmter Maßstab.

Die Tabelle ist leer; es geht nichts verloren.

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("season_context")


def downgrade() -> None:
    op.create_table(
        "season_context",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("filename", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )
