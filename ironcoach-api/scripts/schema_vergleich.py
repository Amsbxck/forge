"""Schema aus den Migrationen gegen das Schema der Modelle vergleichen.

    DATABASE_URL=postgresql://…/leere_db python -m scripts.schema_vergleich

Führt `alembic upgrade head` auf der angegebenen (leeren) Datenbank aus und
meldet Tabellen, Spalten, NOT NULL und eindeutige Indizes, die nur auf einer
Seite stehen. Die Tests bauen ihr Schema mit `create_all` aus den Modellen —
was nur in den Migrationen steht, sehen sie nicht.
"""

import os
import sys

from sqlalchemy import create_engine, inspect


def unterschiede(url: str) -> list[str]:
    from alembic import command
    from alembic.config import Config

    from database import Base
    import models  # noqa: F401

    os.environ["DATABASE_URL"] = url
    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    cfg.set_main_option("script_location",
                        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic"))
    command.upgrade(cfg, "head")

    insp = inspect(create_engine(url))
    meldungen: list[str] = []
    db_tabellen = set(insp.get_table_names()) - {"alembic_version"}
    modell_tabellen = set(Base.metadata.tables)
    for t in sorted(modell_tabellen - db_tabellen):
        meldungen.append(f"Tabelle nur im Modell: {t}")
    for t in sorted(db_tabellen - modell_tabellen):
        meldungen.append(f"Tabelle nur in der Migration: {t}")

    for name in sorted(modell_tabellen & db_tabellen):
        tabelle = Base.metadata.tables[name]
        db_spalten = {c["name"]: c for c in insp.get_columns(name)}
        for spalte in tabelle.columns:
            if spalte.name not in db_spalten:
                meldungen.append(f"{name}.{spalte.name}: nur im Modell")
                continue
            if not spalte.primary_key and bool(spalte.nullable) != bool(db_spalten[spalte.name]["nullable"]):
                meldungen.append(
                    f"{name}.{spalte.name}: NULL im Modell {spalte.nullable}, "
                    f"in der Migration {db_spalten[spalte.name]['nullable']}"
                )
        for extra in set(db_spalten) - {c.name for c in tabelle.columns}:
            meldungen.append(f"{name}.{extra}: nur in der Migration")
    return meldungen


if __name__ == "__main__":
    zeilen = unterschiede(os.environ["DATABASE_URL"])
    print("\n".join(zeilen) or "keine Unterschiede")
    sys.exit(1 if zeilen else 0)
