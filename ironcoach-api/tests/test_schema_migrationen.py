"""Das Schema der Migrationen und das der Modelle sind dasselbe.

Die Tests bauen ihre Tabellen mit `create_all` aus den Modellen; im Betrieb
entsteht das Schema aus den Alembic-Migrationen. Lief beides auseinander,
prüften die Tests ein anderes Schema als das, auf dem die App läuft: NOT NULL
gab es nur im Test, ein eindeutiger Index auf offenen Krankmeldungen nur im
Betrieb. Dieser Test baut eine leere Datenbank über die Migrationen auf und
vergleicht Tabellen, Spalten und NULL-Regeln (`scripts/schema_vergleich.py`).
"""

import os

import pytest
from sqlalchemy import create_engine, text


def test_migrationen_und_modelle_stimmen_ueberein():
    url = os.environ["DATABASE_URL"]
    if not url.startswith("postgresql"):
        pytest.skip("nur mit Postgres")
    basis, _, name = url.rpartition("/")
    ziel = f"{name}_schema"
    wartung = create_engine(f"{basis}/postgres", isolation_level="AUTOCOMMIT")
    with wartung.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{ziel}"'))
        conn.execute(text(f'CREATE DATABASE "{ziel}"'))

    alt = os.environ["DATABASE_URL"]
    try:
        from scripts.schema_vergleich import unterschiede

        meldungen = unterschiede(f"{basis}/{ziel}")
    finally:
        os.environ["DATABASE_URL"] = alt
        with wartung.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{ziel}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(text(f'DROP DATABASE IF EXISTS "{ziel}"'))
        wartung.dispose()

    assert not meldungen, "\n".join(meldungen)
