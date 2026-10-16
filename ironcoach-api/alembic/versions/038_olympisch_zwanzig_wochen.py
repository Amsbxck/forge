"""Olympische Distanz: 20 statt 16 Wochen — auch für Ziele, die noch nicht laufen.

Die Vorgabe in `core/race_types.py` steht jetzt auf 20 Wochen. Sie wirkt aber
nur auf neue Ziele: Beim Anlegen wird die Dauer ins Ziel geschrieben
(`race_goals.plan_weeks`), und alles danach — Phasen, Deload, Wochenzählung —
liest diesen gespeicherten Wert.

Bestehende Ziele umzurechnen ist nur sicher, solange ihre Vorbereitung noch
nicht begonnen hat. Danach verrutschen die Wochennummern, und
`services/plan_projection.project_plan` löscht geplante Einheiten **über die
Wochennummer** — eine neu erzeugte „Woche 3" träfe die alte Woche 3 einer
anderen Kalenderwoche.

Umgestellt wird deshalb nur ein Olympisch-A-Ziel, das

  * noch die alte Vorgabe trägt (`plan_weeks = 16`) — wer die Dauer bewusst
    anders gesetzt hat, behält sie,
  * dessen **neuer** Start frühestens am kommenden Montag liegt, und
  * für dessen Athleten es ab diesem neuen Start noch keinen Wochenplan gibt.
    Geprüft ab dem neuen Start, nicht ab dem alten: Der neue liegt vier Wochen
    früher, und ein Plan in genau diesen vier Wochen würde sonst seine
    Nummer verlieren. Ausgenommen sind Testwochen — sie liegen vor dem
    Aufbau und tragen keine Phase, die sich verschieben könnte.

Revision ID: 038
Revises: 037
"""

import logging
from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

ALT = 16
NEU = 20


def _montag_von(tag: date) -> date:
    return tag - timedelta(days=tag.weekday())


def _start(renntag: date, wochen: int) -> date:
    # Dieselbe Rechnung wie `core.race_types.plan_start_for` — hier abgeschrieben,
    # damit die Migration nicht an Anwendungscode hängt, der sich später ändert.
    return _montag_von(renntag) - timedelta(weeks=wochen - 1)


def olympisch_umstellen(conn, heute: date | None = None) -> list[int]:
    """Die umstellbaren Ziele umstellen. Gibt ihre IDs zurück."""
    heute = heute or date.today()
    naechster_montag = heute + timedelta(days=7 - heute.weekday())

    ziele = conn.execute(sa.text(
        """
        SELECT id, user_id, race_date
          FROM race_goals
         WHERE sport = 'triathlon' AND distance = 'olympic'
           AND priority = 'A' AND is_active
           AND plan_weeks = :alt
        """
    ), {"alt": ALT}).fetchall()

    umgestellt = []
    for ziel_id, user_id, renntag in ziele:
        neu_start = _start(renntag, NEU)
        if neu_start < naechster_montag:
            continue
        vorhanden = conn.execute(sa.text(
            """
            SELECT 1 FROM weekly_plans
             WHERE user_id = :uid AND week_start >= :ab
               AND COALESCE(plan_phase, '') <> 'Benchmark'
             LIMIT 1
            """
        ), {"uid": user_id, "ab": neu_start}).first()
        if vorhanden:
            continue
        conn.execute(sa.text(
            "UPDATE race_goals SET plan_weeks = :neu, plan_start_date = :start "
            "WHERE id = :id"
        ), {"neu": NEU, "start": neu_start, "id": ziel_id})
        umgestellt.append(ziel_id)

    logger.info("Olympisch auf %s Wochen umgestellt: %s Ziel(e) %s",
                NEU, len(umgestellt), umgestellt)
    return umgestellt


def upgrade() -> None:
    olympisch_umstellen(op.get_bind())


def downgrade() -> None:
    # Nicht zurückgedreht: Inzwischen erzeugte Pläne rechnen mit dem neuen
    # Start. Eine Rückkehr auf 16 Wochen wäre dieselbe Verschiebung, vor der
    # diese Migration sich hütet.
    pass
