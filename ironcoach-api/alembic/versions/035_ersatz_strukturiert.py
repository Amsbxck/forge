"""Ersatzeinheit mit Sportart und Intensität statt nur Freitext.

Bisher trug ein Ersatz einen Satz ("bin mit Freunden wandern gewesen") und
optional eine Dauer. Für den Menschen genügt das, für die Planung nicht: Aus
"war schwimmen" lässt sich nicht ablesen, ob das eine Stunde locker oder
zwanzig Minuten hart war — und beides bedeutet für die nächste Woche etwas
anderes.

Der Freitext bleibt: Er trägt weiterhin die Beschreibung, und bestehende
Einträge haben nur ihn. Die beiden neuen Spalten kommen daneben, nullable —
ein alter Ersatz ohne Sportart ist kein Fehler, nur weniger genau.

Revision ID: 035
Revises: 034
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planned_sessions", sa.Column("replacement_discipline", sa.String(), nullable=True))
    op.add_column("planned_sessions", sa.Column("replacement_intensity", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("planned_sessions", "replacement_intensity")
    op.drop_column("planned_sessions", "replacement_discipline")
