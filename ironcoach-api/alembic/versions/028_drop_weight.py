"""Gewicht wieder entfernen.

Eingeführt in 026 für Watt pro Kilo. Der Wert ist für die Planung entbehrlich:
Jede Vorgabe entsteht aus FTP, Schwellenpace und Puls, und keine davon braucht
das Körpergewicht. Watt pro Kilo war eine zusätzliche Anzeige, kein Eingang in
eine Entscheidung.

Damit fällt zugleich der Anlass weg, im Trainingsplan überhaupt über den Körper
zu sprechen — die entsprechende Schutzregel im Prompt wird mit entfernt, weil
sie ohne den Wert ins Leere zielt.

Revision ID: 028
Revises: 027
"""

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("athlete_profile", "weight_kg")


def downgrade() -> None:
    op.add_column("athlete_profile", sa.Column("weight_kg", sa.Float(), nullable=True))
