"""Doppelt angelegte Testwochen entfernen.

Bei einem echten Onboarding wurde „Testwoche planen" zweimal gedrückt, und
beide Anfragen legten einen Plan an: Die Prüfung auf einen bestehenden Plan
las und schrieb ohne Sperre dazwischen (behoben in
`services/benchmark.create_benchmark_plan`). Die Produktionsdatenbank ist von
außen nicht erreichbar — das Doppel lässt sich nur hier beseitigen, beim
nächsten Deploy.

Entfernt wird **nur** ein echtes Doppel: gleicher Athlet, gleiche Woche,
Phase „Benchmark", byte-gleicher Planinhalt und unangetastet
(`adjustments_applied = ['Benchmark-Woche']`). Eine angepasste Testwoche trägt
dieselbe Phase, aber eine längere Änderungsliste — sie ist eine gewollte
neue Fassung und bleibt.

Welches Exemplar bleibt: das mit dem meisten Fortschritt (erledigte oder
zugeordnete Einheiten), dann das mit den meisten geplanten Einheiten, bei
Gleichstand das jüngere. Fortschritt zuerst, weil eine erledigte Einheit,
die im bleibenden Exemplar keinen passenden Platz hat, sonst verloren ginge. Normalerweise hat nur das jüngere Einheiten, weil
die zweite Projektion die Zeilen der ersten löscht — bei echter Gleichzeitigkeit
können aber beide welche haben. Fortschritt und Zuordnungen des entfernten
Exemplars werden vorher auf das bleibende übertragen, damit kein bereits
absolvierter Test verloren geht.

Obsidian bleibt unberührt: Beide Exemplare schreiben dieselbe Notiz.

Revision ID: 036
Revises: 035
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

FORTSCHRITT = (
    "status", "matched_session_id", "replacement", "replacement_min",
    "replacement_discipline", "replacement_intensity", "moved_from_date",
)


def doppelte_testwochen(conn) -> list[tuple[int, int]]:
    """Paare (entfernen, behalten) — leer, wenn es kein Doppel gibt."""
    zeilen = conn.execute(sa.text(
        """
        WITH k AS (
          SELECT wp.id, wp.user_id, wp.week_start, wp.plan_content,
                 wp.generated_at,
                 (SELECT count(*) FROM planned_sessions ps
                   WHERE ps.plan_id = wp.id) AS n,
                 (SELECT count(*) FROM planned_sessions ps
                   WHERE ps.plan_id = wp.id
                     AND (ps.status <> 'planned'
                          OR ps.matched_session_id IS NOT NULL)) AS fortschritt
            FROM weekly_plans wp
           WHERE wp.plan_phase = 'Benchmark'
             AND wp.adjustments_applied = ARRAY['Benchmark-Woche']::text[]
        ), r AS (
          SELECT id,
                 first_value(id) OVER w AS bleibt,
                 row_number()    OVER w AS rang
            FROM k
          WINDOW w AS (
            PARTITION BY user_id, week_start, plan_content
            ORDER BY fortschritt DESC, n DESC, generated_at DESC, id DESC
          )
        )
        SELECT id, bleibt FROM r WHERE rang > 1
        """
    )).fetchall()
    return [(z[0], z[1]) for z in zeilen]


def _vorhandene_spalten(conn) -> set[str]:
    """Nur Spalten übertragen, die es in dieser Datenbank gibt — die
    Ersatz-Felder kamen erst mit Migration 035."""
    return {
        z[0] for z in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'planned_sessions'"
        ))
    }


def bereinigen(conn) -> int:
    paare = doppelte_testwochen(conn)
    if not paare:
        logger.info("Keine doppelten Testwochen gefunden.")
        return 0

    felder = [f for f in FORTSCHRITT if f in _vorhandene_spalten(conn)]
    zuweisung = ", ".join(f"{f} = w.{f}" for f in felder)

    for weg, bleibt in paare:
        # 1. Fortschritt übertragen — nur auf Zeilen, die selbst noch keinen
        #    haben, damit nichts Erledigtes überschrieben wird.
        if zuweisung:
            conn.execute(sa.text(
                f"""
                UPDATE planned_sessions b SET {zuweisung}
                  FROM planned_sessions w
                 WHERE w.plan_id = :weg AND b.plan_id = :bleibt
                   AND b.planned_date = w.planned_date
                   AND b.discipline = w.discipline
                   AND b.day_index IS NOT DISTINCT FROM w.day_index
                   AND b.status = 'planned' AND b.matched_session_id IS NULL
                   AND (w.status <> 'planned' OR w.matched_session_id IS NOT NULL)
                """
            ), {"weg": weg, "bleibt": bleibt})

        # 2. Echte Einheiten, die auf das entfernte Exemplar zeigten, auf die
        #    passende Zeile des bleibenden umhängen.
        conn.execute(sa.text(
            """
            UPDATE training_sessions t SET planned_session_id = b.id
              FROM planned_sessions w, planned_sessions b
             WHERE t.planned_session_id = w.id
               AND w.plan_id = :weg AND b.plan_id = :bleibt
               AND b.planned_date = w.planned_date
               AND b.discipline = w.discipline
               AND b.day_index IS NOT DISTINCT FROM w.day_index
            """
        ), {"weg": weg, "bleibt": bleibt})

        # 3. Fortschritt ohne passenden Platz im bleibenden Exemplar umhängen
        #    statt mitzulöschen. Bei byte-gleichem Inhalt haben beide dieselben
        #    Tage, und das hier trifft nichts — aber wenn doch, geht damit
        #    kein absolvierter Test verloren, und die echte Einheit behält
        #    ihre Zuordnung.
        conn.execute(sa.text(
            """
            UPDATE planned_sessions w SET plan_id = :bleibt
             WHERE w.plan_id = :weg
               AND (w.status <> 'planned' OR w.matched_session_id IS NOT NULL)
               AND NOT EXISTS (
                     SELECT 1 FROM planned_sessions b
                      WHERE b.plan_id = :bleibt
                        AND b.planned_date = w.planned_date
                        AND b.discipline = w.discipline
                        AND b.day_index IS NOT DISTINCT FROM w.day_index)
            """
        ), {"weg": weg, "bleibt": bleibt})

        # 4. Entfernen — die übrigen geplanten Einheiten folgen über
        #    ON DELETE CASCADE.
        conn.execute(sa.text("DELETE FROM weekly_plans WHERE id = :weg"),
                     {"weg": weg})

    logger.info("Doppelte Testwochen entfernt: %s %s", len(paare), paare)
    return len(paare)


def upgrade() -> None:
    bereinigen(op.get_bind())


def downgrade() -> None:
    # Entfernte Doppel werden nicht wiederhergestellt — sie waren identisch
    # mit dem bleibenden Exemplar.
    pass
