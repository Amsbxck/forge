"""Arbeitswege als solche kennzeichnen.

Ein Commute ist echtes Radfahren — er trägt Last und gehört in die Formkurve.
Er ist aber nicht die geplante Einheit, und genau so wurde er behandelt: Die
Zuordnung vergibt 0.5 Punkte für dieselbe Sportart und 0.3 für denselben Tag,
die Schwelle liegt bei 0.5. Eine 20-Minuten-Fahrt zur Arbeit erreichte damit
0.8 und galt als die geplante Ausfahrt über 90 Minuten: Der Tag wurde grün, die
Vorgabe als erfüllt verbucht, und die Belastbarkeitsrechnung meldete einen
massiven Rückstand — woraufhin der Coach das Volumen senkt.

Strava führt das Kennzeichen selbst (`commute` an der Aktivität), es wurde
bisher nur nicht ausgelesen.

Revision ID: 034
Revises: 033
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_sessions",
        sa.Column("is_commute", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("training_sessions", "is_commute")
