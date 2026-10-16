"""E-Mail-Bestätigung wird Pflicht — ohne bestehende Konten auszusperren.

Wer seine Adresse nicht bestätigt hat, kommt künftig nicht mehr in die App,
sondern sieht ein Bestätigungsfenster. Vorher bestand Gefahr, Konten
auszusperren, die bisher problemlos liefen:

  * Migration 015 (10.09.2026) hat alle Konten, die damals existierten, als
    bestätigt markiert.
  * Wer sich danach registriert und den Link nie geklickt hat, wäre jetzt
    plötzlich gesperrt — und das, während der Mailversand über Brevo nicht
    zuverlässig läuft.

Deshalb gelten alle Konten, die vor dem Stichtag angelegt wurden, als
bestätigt, ebenso alle Admins. Der Stichtag 15.10.2026 00:00 UTC liegt vor der
Registrierung des neuesten Nutzers (16.10.) mit Abstand: `created_at` ist UTC,
und eine Registrierung kurz nach Mitternacht deutscher Zeit stünde sonst noch
auf dem 15.

Dazu zwei Spalten, die festhalten, ob die letzte Bestätigungsmail beim
Mailanbieter angenommen wurde.

Revision ID: 037
Revises: 036
"""

import logging
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

STICHTAG = datetime(2026, 10, 15, 0, 0, 0)


def altkonten_bestaetigen(conn, stichtag: datetime = STICHTAG) -> int:
    ergebnis = conn.execute(sa.text(
        """
        UPDATE users SET email_verified_at = COALESCE(created_at, NOW())
         WHERE email_verified_at IS NULL
           AND (is_admin OR created_at IS NULL OR created_at < :stichtag)
        """
    ), {"stichtag": stichtag})
    anzahl = ergebnis.rowcount or 0
    logger.info("Bestandskonten als bestätigt markiert: %s", anzahl)
    return anzahl


def upgrade() -> None:
    op.add_column("users", sa.Column("verify_mail_status", sa.String, nullable=True))
    op.add_column("users", sa.Column("verify_mail_at", sa.DateTime, nullable=True))
    altkonten_bestaetigen(op.get_bind())


def downgrade() -> None:
    # Die Bestätigung der Bestandskonten wird nicht zurückgedreht: Sie war
    # die Voraussetzung dafür, dass niemand ausgesperrt wurde.
    op.drop_column("users", "verify_mail_at")
    op.drop_column("users", "verify_mail_status")
