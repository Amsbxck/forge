"""Obsidian-Anbindung je Athlet

Revision ID: 009
Revises: 008
Create Date: 2026-09-02

Die Vault-Zugangsdaten standen in der .env und zeigten auf genau einen
Rechner. Mit mehreren Nutzern hätte jeder in denselben fremden Vault
geschrieben. Die Werte aus der Umgebung bleiben als Rückfallebene bestehen,
solange ein Athlet nichts eigenes hinterlegt hat — sonst verlöre die
bestehende Installation ihre Anbindung.
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("obsidian_base_url", sa.String, nullable=True))
    op.add_column("athlete_profile", sa.Column("obsidian_api_key", sa.String, nullable=True))
    op.add_column("athlete_profile", sa.Column("obsidian_vault_subdir", sa.String, nullable=True))


def downgrade() -> None:
    for column in ("obsidian_vault_subdir", "obsidian_api_key", "obsidian_base_url"):
        op.drop_column("athlete_profile", column)
