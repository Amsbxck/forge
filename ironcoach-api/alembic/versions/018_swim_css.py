"""Schwellenpace im Wasser (CSS)

Revision ID: 018
Revises: 017
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Die Spalte gibt es schon — Migration 008 hat sie als Integer angelegt.
    # Hier stand `add_column`, was auf einer frisch aufgebauten Datenbank
    # zwangsläufig mit "column already exists" abbricht. Lokal fiel das nie
    # auf, weil die Kette dort nie von null lief; erst der erste Serverstart
    # hat es sichtbar gemacht.
    #
    # Gewollt war eine Typänderung: Eine CSS-Pace von 1:45,5 je 100 m lässt
    # sich in ganzen Sekunden nicht abbilden, und ein halber Sekundenfehler
    # je 100 m summiert sich über 1,9 km auf rund zehn Sekunden.
    op.alter_column(
        "athlete_profile",
        "css_pace_s_per_100m",
        type_=sa.Float,
        existing_type=sa.Integer,
        existing_nullable=True,
    )
    op.add_column("athlete_profile", sa.Column("css_source", sa.String, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_t400_s", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_t200_s", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profile", "css_t200_s")
    op.drop_column("athlete_profile", "css_t400_s")
    op.drop_column("athlete_profile", "css_source")
    # Nicht löschen — die Spalte stammt aus 008 und gehört dorthin zurück.
    op.alter_column(
        "athlete_profile",
        "css_pace_s_per_100m",
        type_=sa.Integer,
        existing_type=sa.Float,
        existing_nullable=True,
    )
