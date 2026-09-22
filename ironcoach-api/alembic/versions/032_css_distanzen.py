"""Welche Strecken der CSS-Test hatte.

Bis hierher war der Test fest auf 400 m und 200 m gelegt — die Spalten
heissen entsprechend `css_t400_s` und `css_t200_s`. Für geübte Schwimmer
ist das richtig, für Anfänger nicht: Wer 400 m nicht am Stück maximal
schwimmen kann, produziert dort keinen Messwert, sondern eine Einbruchskurve.

Die Formel verlangt die feste Distanz gar nicht, nur die Differenz:

    CSS = (t_lang − t_kurz) / ((d_lang − d_kurz) / 100)

Damit sind auch 200/100 und 100/50 auswertbar. Welche Strecken es waren,
muss mitgespeichert werden — sonst lässt sich der Wert später nicht mehr
nachvollziehen und nicht nachrechnen.

Die Zeitspalten behalten ihre Namen. Sie umzubenennen hiesse, sie an einem
Dutzend Stellen anzufassen; der Gewinn wäre kosmetisch. Was sie bedeuten,
steht jetzt in den Distanzspalten daneben.

Revision ID: 032
Revises: 031
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("css_dist_lang_m", sa.Integer(), nullable=True))
    op.add_column("athlete_profile", sa.Column("css_dist_kurz_m", sa.Integer(), nullable=True))
    # Bestehende Werte stammen alle aus dem 400/200-Protokoll.
    op.execute("""
        UPDATE athlete_profile
           SET css_dist_lang_m = 400, css_dist_kurz_m = 200
         WHERE css_t400_s IS NOT NULL AND css_t200_s IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("athlete_profile", "css_dist_kurz_m")
    op.drop_column("athlete_profile", "css_dist_lang_m")
