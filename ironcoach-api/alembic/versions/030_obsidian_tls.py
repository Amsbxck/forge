"""Zertifikatsprüfung für Obsidian je Athlet.

Bisher galt `OBSIDIAN_VERIFY_TLS` für die ganze Installation. Das ging nicht
auf, sobald mehrere Athleten ihre Vaults auf verschiedene Weise anbinden:

* Wer `tailscale serve` einrichtet, bekommt ein gültiges Zertifikat — dort
  soll geprüft werden.
* Wer nur die Tailnet-IP einträgt, spricht direkt mit dem Obsidian-Plugin,
  und dessen Zertifikat ist selbstsigniert. Eine Prüfung schlägt dort immer
  fehl.

Der zweite Weg ist der, den jemand ohne Terminal gehen kann: Adresse in der
Tailscale-App ablesen, eintragen, fertig. Damit er nicht an einer Einstellung
scheitert, von der er nichts weiß, entscheidet die Anwendung selbst — leeres
Feld heißt „automatisch".

Revision ID: 030
Revises: 029
"""

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bewusst nullable: NULL = automatisch entscheiden, True/False = der
    # Athlet hat sich festgelegt. Ein reines True/False hätte keinen Platz
    # für „noch nicht entschieden".
    op.add_column(
        "athlete_profile",
        sa.Column("obsidian_verify_tls", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("athlete_profile", "obsidian_verify_tls")
