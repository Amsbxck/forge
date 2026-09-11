"""Kontosicherheit: Bestätigung, Sperre, Einmal-Token

Revision ID: 015
Revises: 014
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("tokens_valid_from", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("failed_logins", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime, nullable=True))

    # Bestehende Konten gelten als bestätigt: sie sind vor Einführung der
    # Bestätigung entstanden und würden sonst rückwirkend ausgesperrt.
    op.execute("UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL")

    op.create_table(
        "auth_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("token_hash", sa.String, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    # Der Hash ist der Suchschlüssel beim Einlösen eines Links.
    op.create_index("ix_auth_actions_token_hash", "auth_actions", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_auth_actions_token_hash", table_name="auth_actions")
    op.drop_table("auth_actions")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_logins")
    op.drop_column("users", "tokens_valid_from")
    op.drop_column("users", "email_verified_at")
