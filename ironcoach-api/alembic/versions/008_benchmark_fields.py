"""Aus Benchmark-Tests abgeleitete Werte im Profil

Revision ID: 008
Revises: 007
Create Date: 2026-09-02

Neue Athleten haben keine FTP und keine Zonen. Statt sie schätzen zu lassen,
absolvieren sie in Woche 1 Testeinheiten, aus denen die Werte gemessen
hervorgehen. Die HF-Zonen stehen bereits im Profil; hier kommt dazu, was
sich nicht in Herzschlägen ausdrücken lässt.

zones_source hält fest, ob die Zonen gemessen oder von Hand gesetzt wurden —
ohne diese Unterscheidung überschreibt ein Benchmark-Lauf stillschweigend
Werte, die jemand bewusst korrigiert hat.
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profile", sa.Column("threshold_pace_s_per_km", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("css_pace_s_per_100m", sa.Integer, nullable=True))
    op.add_column("athlete_profile", sa.Column("zones_source", sa.String, nullable=True))
    op.add_column("athlete_profile", sa.Column("zones_updated_at", sa.DateTime, nullable=True))

    # Bestehende Zonen sind von Hand gepflegt — das soll ein späterer
    # Benchmark-Lauf wissen, bevor er sie ersetzt.
    op.execute("UPDATE athlete_profile SET zones_source = 'manual' WHERE zones_source IS NULL")


def downgrade() -> None:
    for column in ("zones_updated_at", "zones_source", "css_pace_s_per_100m", "threshold_pace_s_per_km"):
        op.drop_column("athlete_profile", column)
