"""Herkunft der FTP festhalten.

Für Schwellenpuls, Schwimm-Schwelle und CSS gibt es je ein Herkunftsfeld,
für die FTP nicht. Angezeigt wurde stattdessen `zones_source` — ein Flag
für das ganze Profil. Wer seine FTP aus einem Zwift-Stufentest einträgt und
später die Laufzonen aus der Testwoche ableitet, bekam sie dadurch als
"gemessen" ausgewiesen, obwohl sie von Hand stammt.

Und umgekehrt: Ohne eigenes Feld lässt sich eine eingetragene FTP nicht vor
dem Überschreiben schützen.

Werte: "manual" (eingetragen, etwa aus einem Stufentest am Smart Trainer),
"benchmark" (aus dem 20-Minuten-Test abgeleitet), leer (Voreinstellung).

Revision ID: 031
Revises: 030
"""

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("ftp_source", sa.String(), nullable=True))
    # Bestehende Profile: Was aus einer Testwoche stammt, ist auch bei der
    # FTP daraus abgeleitet — alles andere wurde eingetragen.
    op.execute("""
        UPDATE athlete_profile
           SET ftp_source = CASE WHEN zones_source = 'benchmark'
                                 THEN 'benchmark' ELSE 'manual' END
         WHERE ftp_source IS NULL AND ftp_watts IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("athlete_profile", "ftp_source")
