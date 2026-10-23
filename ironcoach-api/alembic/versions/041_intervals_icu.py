"""Geplante Läufe über intervals.icu auf die Garmin-Uhr.

Garmin nimmt selbst keine Workouts an: Die Personal API ist nur lesend, und
Garmin Connect importiert keine Workout-Dateien. intervals.icu dagegen nimmt
geplante Workouts über seine API an und schiebt sie in den Garmin-Kalender.

Profil: Zugang je Athlet, entweder persönlicher Schlüssel mit Athleten-ID oder
OAuth-Token, beide verschlüsselt (`core/geheim.py`). Dazu Zeitpunkt der
Verbindung, letzter erfolgreicher Abgleich und ein fester Fehlertext.

An `planned_sessions` kommt bewusst nichts: Die Projektion ersetzt die Zeilen
einer Woche bei jeder Neuplanung, eine dort gemerkte Event-ID ginge verloren.
Der Abgleich erkennt seine Events an der `external_id`.

Revision ID: 041
Revises: 040
"""

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("intervals_athlete_id", sa.String(), nullable=True))
    op.add_column("athlete_profile", sa.Column("intervals_api_key", sa.String(), nullable=True))
    op.add_column("athlete_profile", sa.Column("intervals_token", sa.String(), nullable=True))
    op.add_column("athlete_profile", sa.Column("intervals_verbunden_am", sa.DateTime(), nullable=True))
    op.add_column("athlete_profile", sa.Column("intervals_letzter_abgleich", sa.DateTime(), nullable=True))
    op.add_column("athlete_profile", sa.Column("intervals_letzter_fehler", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "intervals_letzter_fehler")
    op.drop_column("athlete_profile", "intervals_letzter_abgleich")
    op.drop_column("athlete_profile", "intervals_verbunden_am")
    op.drop_column("athlete_profile", "intervals_token")
    op.drop_column("athlete_profile", "intervals_api_key")
    op.drop_column("athlete_profile", "intervals_athlete_id")
