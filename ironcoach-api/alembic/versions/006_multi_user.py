"""Mandantenfähigkeit: users-Tabelle und user_id auf allen Tabellen

Revision ID: 006
Revises: 005
Create Date: 2026-08-16

Bis hierher ging die App von genau einem Athleten aus — `AthleteProfile.first()`
stand an 17 Stellen. Diese Migration legt das Fundament für mehrere Nutzer,
ohne bestehende Daten anzufassen: der vorhandene Bestand wird Nutzer 1
zugeordnet, alles andere bleibt wie es ist.

Die Spalten sind bewusst nullable. Ein NOT NULL würde erzwingen, dass jeder
künftige Schreibpfad die user_id kennt, bevor die Anmeldung überhaupt steht —
das wird in einer späteren Migration nachgezogen, sobald alle Pfade sie setzen.
"""
import os

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

# Tabellen, die einem Nutzer gehören
USER_TABLES = [
    "training_sessions",
    "hrv_measurements",
    "weekly_plans",
    "planned_sessions",
    "chat_messages",
    "season_context",
    "strava_credentials",
]

DEFAULT_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "laxerju@gmail.com")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=True),
        sa.Column("password_hash", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.add_column("athlete_profile", sa.Column("user_id", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("coaching_constraints", sa.Text, nullable=True))
    for table in USER_TABLES:
        op.add_column(table, sa.Column("user_id", sa.Integer, nullable=True))

    # Bestandsnutzer aus dem vorhandenen Profil anlegen und alles zuordnen.
    connection = op.get_bind()
    name = connection.execute(
        sa.text("SELECT name FROM athlete_profile ORDER BY id LIMIT 1")
    ).scalar()

    has_data = connection.execute(sa.text("SELECT count(*) FROM athlete_profile")).scalar()
    if has_data:
        user_id = connection.execute(
            sa.text(
                "INSERT INTO users (email, name, is_active) "
                "VALUES (:email, :name, true) RETURNING id"
            ),
            {"email": DEFAULT_EMAIL, "name": name or "Athlet"},
        ).scalar()

        connection.execute(
            sa.text("UPDATE athlete_profile SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": user_id},
        )
        for table in USER_TABLES:
            connection.execute(
                sa.text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )

    # Fremdschlüssel und Indizes erst nach dem Backfill.
    op.create_foreign_key(
        "fk_athlete_profile_user", "athlete_profile", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("uq_athlete_profile_user", "athlete_profile", ["user_id"], unique=True)

    for table in USER_TABLES:
        op.create_foreign_key(
            f"fk_{table}_user", table, "users", ["user_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:
    for table in USER_TABLES:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_constraint(f"fk_{table}_user", table, type_="foreignkey")
        op.drop_column(table, "user_id")

    op.drop_index("uq_athlete_profile_user", table_name="athlete_profile")
    op.drop_constraint("fk_athlete_profile_user", "athlete_profile", type_="foreignkey")
    op.drop_column("athlete_profile", "coaching_constraints")
    op.drop_column("athlete_profile", "user_id")
    op.drop_table("users")
