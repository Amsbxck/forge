"""Strava: ein Athlet je Konto, gelöschte Aktivitäten merken, Platzhalter-FTP.

Fünf Änderungen aus der Code-Prüfung vom 18.10.2026:

1. **`strava_credentials.athlete_id` eindeutig.** Derselbe Strava-Athlet ließ
   sich an zwei Konten hängen. Der Webhook nahm dann irgendeines, und der
   stündliche Abgleich des anderen scheiterte jede Stunde an der doppelten
   Aktivitätsnummer — mit einem Fehler, der (bis zur Korrektur im Scheduler)
   auch alle folgenden Athleten aufhielt. Vorhandene Doppel werden aufgelöst:
   Es bleibt die jüngste Verbindung, die älteren werden entfernt (ihr Abgleich
   lief ohnehin ins Leere). Eingelesene Einheiten bleiben unberührt.

2. **Tabelle `geloeschte_strava_aktivitaeten`.** Endgültig gelöschte
   Aktivitäten kamen beim nächsten Abgleich zurück. Hier wird vermerkt, was
   der Athlet nicht mehr sehen will.

3. **Platzhalter-FTPs nicht mehr als „manual".** Migration 031 hat jede FTP
   ohne Testwoche als von Hand eingetragen markiert — auch die 200-W-
   Vorgabe frischer Konten. Für solche Werte verweigerte die Ableitung danach
   große Korrekturen nach unten, als hätte der Athlet sie selbst gesetzt.
   Zurückgesetzt wird nur, was eindeutig ein Platzhalter ist: Zonen noch auf
   „default" und die FTP auf dem Modellwert.

4. **`training_sessions.obsidian_fehlversuche`.** Zählt abgelehnte
   Vault-Schreibversuche; nach fünf hört die Outbox auf.

5. **Obsidian-Schlüssel verschlüsselt** (`core/geheim.py`).

Revision ID: 039
Revises: 038
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PLATZHALTER_FTP = 200


def doppelte_verbindungen_aufloesen(conn) -> int:
    zeilen = conn.execute(sa.text(
        """
        SELECT id FROM (
          SELECT id,
                 row_number() OVER (PARTITION BY athlete_id
                                    ORDER BY connected_at DESC NULLS LAST, id DESC) AS rang
            FROM strava_credentials
        ) r WHERE rang > 1
        """
    )).fetchall()
    ids = [z[0] for z in zeilen]
    if ids:
        conn.execute(sa.text("DELETE FROM strava_credentials WHERE id = ANY(:ids)"), {"ids": ids})
        logger.info("Doppelte Strava-Verbindungen entfernt: %s", ids)
    return len(ids)


def platzhalter_ftp_zuruecksetzen(conn) -> int:
    ergebnis = conn.execute(sa.text(
        """
        UPDATE athlete_profile
           SET ftp_source = NULL
         WHERE ftp_source = 'manual'
           AND COALESCE(zones_source, 'default') = 'default'
           AND ftp_watts = :ftp
        """
    ), {"ftp": PLATZHALTER_FTP})
    anzahl = ergebnis.rowcount or 0
    if anzahl:
        logger.info("Platzhalter-FTP nicht mehr als manuell markiert: %s Profile", anzahl)
    return anzahl


def obsidian_schluessel_verschluesseln(conn) -> int:
    """Bestehende Obsidian-Schlüssel verschlüsseln (`core/geheim.py`)."""
    from core.geheim import KENNUNG, verschluesseln

    zeilen = conn.execute(sa.text(
        "SELECT id, obsidian_api_key FROM athlete_profile "
        "WHERE obsidian_api_key IS NOT NULL AND obsidian_api_key NOT LIKE :k"
    ), {"k": KENNUNG + "%"}).fetchall()
    anzahl = 0
    for zeile_id, klartext in zeilen:
        neu = verschluesseln(klartext)
        if neu != klartext:
            conn.execute(sa.text("UPDATE athlete_profile SET obsidian_api_key = :w WHERE id = :i"),
                         {"w": neu, "i": zeile_id})
            anzahl += 1
    if anzahl:
        logger.info("Obsidian-Schlüssel verschlüsselt: %s", anzahl)
    return anzahl


def upgrade() -> None:
    conn = op.get_bind()

    doppelte_verbindungen_aufloesen(conn)
    op.create_unique_constraint(
        "uq_strava_credentials_athlete_id", "strava_credentials", ["athlete_id"]
    )

    op.create_table(
        "geloeschte_strava_aktivitaeten",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("strava_activity_id", sa.BigInteger, nullable=False),
        sa.Column("geloescht_am", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "strava_activity_id",
                            name="uq_geloeschte_strava_nutzer_aktivitaet"),
    )
    op.create_index("ix_geloeschte_strava_aktivitaeten_user_id",
                    "geloeschte_strava_aktivitaeten", ["user_id"])
    op.create_index("ix_geloeschte_strava_aktivitaeten_strava_activity_id",
                    "geloeschte_strava_aktivitaeten", ["strava_activity_id"])

    platzhalter_ftp_zuruecksetzen(conn)

    # Abgelehnte Vault-Schreibversuche zählen, damit die Outbox nicht für
    # immer stündlich gegen dieselbe Ablehnung läuft.
    op.add_column("training_sessions", sa.Column(
        "obsidian_fehlversuche", sa.Integer, nullable=False, server_default="0"))

    obsidian_schluessel_verschluesseln(conn)


def downgrade() -> None:
    op.drop_column("training_sessions", "obsidian_fehlversuche")
    op.drop_index("ix_geloeschte_strava_aktivitaeten_strava_activity_id",
                  table_name="geloeschte_strava_aktivitaeten")
    op.drop_index("ix_geloeschte_strava_aktivitaeten_user_id",
                  table_name="geloeschte_strava_aktivitaeten")
    op.drop_table("geloeschte_strava_aktivitaeten")
    op.drop_constraint("uq_strava_credentials_athlete_id", "strava_credentials", type_="unique")
