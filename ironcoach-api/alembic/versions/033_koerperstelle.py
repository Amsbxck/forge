"""Welche Körperstelle bei einer Verletzung betroffen ist.

Eine Meldung trug bisher Art, Schweregrad, Fieber und einen Freitext. Damit
liess sich nicht unterscheiden, **wo** es weh tut — und genau davon hängt ab,
was der Plan ändern muss. Ein Schienbeinproblem verlangt Gehpausen im Lauf und
lässt Rad und Schwimmen unberührt; eine Schulter ist umgekehrt. Ohne die Stelle
blieb nur, entweder alles zu drosseln oder nichts.

Bis hierher stand die Lauf-Anpassung deshalb fest im Prompt: Gehpausen für
jeden Athleten, immer, auch ohne jede Beschwerde. Das war die Vorgeschichte
eines einzelnen Athleten, in Beton gegossen.

Freitext zu durchsuchen wäre die bequeme Lösung gewesen, aber "Schienbein"
trifft und "Tibiakantensyndrom" nicht. Eine Schutzregel, die bei einem
Formulierungsdetail still durchfällt, ist schlimmer als keine.

Nullable und ohne Vorbelegung: Krankheiten haben keine Körperstelle, und
bestehende Verletzungsmeldungen nachträglich zu erraten hiesse, Daten zu
erfinden.

Revision ID: 033
Revises: 032
"""

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("health_events", sa.Column("body_part", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("health_events", "body_part")
