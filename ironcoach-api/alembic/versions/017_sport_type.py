"""Ursprüngliche Sportart von Strava behalten

Revision ID: 017
Revises: 016
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

BEKANNT = ("bike", "run", "swim", "gym", "brick", "hike", "rest")


def upgrade() -> None:
    op.add_column("training_sessions", sa.Column("sport_type", sa.String, nullable=True))

    # Bisher landete eine unbekannte Sportart roh in `discipline` — dort steht
    # dann etwa "stairstepper", womit weder Auswertung noch Anzeige umgehen
    # können. Der Rohwert zieht in die neue Spalte um, die Kategorie wird
    # "other".
    bekannt = ", ".join(f"'{d}'" for d in BEKANNT)
    op.execute(f"""
        UPDATE training_sessions
        SET sport_type = discipline, discipline = 'other'
        WHERE discipline IS NOT NULL AND discipline NOT IN ({bekannt})
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE training_sessions
        SET discipline = sport_type
        WHERE discipline = 'other' AND sport_type IS NOT NULL
    """)
    op.drop_column("training_sessions", "sport_type")
