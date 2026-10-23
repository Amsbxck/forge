"""HRV automatisch aus Garmin Connect (Personal API).

Bis hierher kam die HRV nur von Hand ins Dashboard, und die Normalspanne aus
Garmin wurde ebenfalls abgetippt. Beides holt FORGE jetzt selbst ab, mit dem
persönlichen API-Schlüssel des Athleten.

1. **Profil: Garmin-Anbindung je Athlet.** Der Schlüssel liegt verschlüsselt
   wie der Obsidian-Schlüssel (`core/geheim.py`). Dazu der Zeitpunkt der
   Verbindung, der letzte erfolgreiche Abruf und ein fester Fehlertext für die
   Kachel.

2. **`hrv_measurements.quelle`.** "garmin" oder "manual". Bestehende Zeilen
   bleiben bewusst NULL und gelten als manuell: Nachträglich eine Herkunft
   einzutragen hieße zu raten.

`hrv_range_source` bekommt den neuen Wert "garmin"; die Spalte ist ein freier
Text, dafür braucht es keine Schemaänderung.

Revision ID: 040
Revises: 039
"""

import sqlalchemy as sa
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("garmin_api_key", sa.String(), nullable=True))
    op.add_column("athlete_profile", sa.Column("garmin_verbunden_am", sa.DateTime(), nullable=True))
    op.add_column("athlete_profile", sa.Column("garmin_letzter_abruf", sa.DateTime(), nullable=True))
    op.add_column("athlete_profile", sa.Column("garmin_letzter_fehler", sa.String(), nullable=True))
    op.add_column("hrv_measurements", sa.Column("quelle", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("hrv_measurements", "quelle")
    op.drop_column("athlete_profile", "garmin_letzter_fehler")
    op.drop_column("athlete_profile", "garmin_letzter_abruf")
    op.drop_column("athlete_profile", "garmin_verbunden_am")
    op.drop_column("athlete_profile", "garmin_api_key")
