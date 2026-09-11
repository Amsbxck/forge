"""Geschlecht wieder entfernen.

Eingeführt in 026 für die Einordnung der HRV-Normwerte. Dafür wird es nicht
gebraucht — die Normalspanne wird ohnehin aus den eigenen Messungen des
Athleten gebildet, nicht aus einer Vergleichsgruppe. Ein Feld, das erhoben,
gespeichert und nie gelesen wird, ist keine Vorsorge, sondern nur Datenhaltung
ohne Zweck.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("athlete_profile", "gender")


def downgrade() -> None:
    op.add_column("athlete_profile", sa.Column("gender", sa.String(), nullable=True))
