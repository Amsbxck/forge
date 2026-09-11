"""Ersatzeinheit: was stattdessen gemacht wurde.

Bisher kannte eine geplante Einheit nur „erledigt", „verschoben" oder gar
nichts. Wer statt des Intervalltrainings mit Freunden wandern geht, fiel
damit in dieselbe Kategorie wie jemand, der auf der Couch geblieben ist —
und der Plan reagierte auf beides gleich, nämlich mit Zurückfahren.

Das ist sachlich falsch: Eine dreistündige Wanderung ist Belastung, keine
Pause. Und es ist der häufigere Fall, nicht der Ausnahmefall — Sport mit
anderen Menschen ist ein Grund zu trainieren, nicht eine Störung des Plans.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Freitext statt Auswahlliste: Was jemand stattdessen macht, lässt sich
    # nicht vorab aufzählen. Der Coach liest es ohnehin als Sprache.
    op.add_column("planned_sessions", sa.Column("replacement", sa.Text(), nullable=True))
    # Getrennt von der Dauer der geplanten Einheit — sie ist der Grund,
    # warum der Ersatz als Belastung zählt oder eben nicht.
    op.add_column(
        "planned_sessions", sa.Column("replacement_min", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("planned_sessions", "replacement_min")
    op.drop_column("planned_sessions", "replacement")
