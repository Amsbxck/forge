"""Erstaufnahme: Körperdaten und der Merker für das Willkommensfenster.

Wer schon mit einer Uhr trainiert, kennt seine Werte. Sie beim Einstieg
abzufragen erspart ihm, sechs Wochen lang gegen geschätzte Zonen zu
trainieren, bis die Testwoche gelaufen ist.

`intake_done_at` ist ausdrücklich ein gespeicherter Merker und keine
Ableitung aus den Daten — anders als die übrigen Onboarding-Schritte. Wer
das Fenster überspringt, hinterlässt nichts, woraus sich „schon gesehen"
erschließen ließe; ohne den Merker ginge es bei jedem Aufruf wieder auf.

Revision ID: 026
Revises: 025
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Freitext statt Aufzählung: Eine feste Liste aus zwei Werten schließt
    # Menschen aus, und für den einzigen fachlichen Zweck — die Einordnung
    # der HRV-Normwerte — genügt die Angabe, sofern sie gemacht wird.
    op.add_column("athlete_profile", sa.Column("gender", sa.String(), nullable=True))
    op.add_column("athlete_profile", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.add_column(
        "athlete_profile", sa.Column("intake_done_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("athlete_profile", "intake_done_at")
    op.drop_column("athlete_profile", "weight_kg")
    op.drop_column("athlete_profile", "gender")
