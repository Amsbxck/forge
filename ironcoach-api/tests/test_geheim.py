"""Der Obsidian-Schlüssel liegt verschlüsselt in der Datenbank."""

from sqlalchemy import text


def test_schluessel_liegt_verschluesselt_und_kommt_lesbar_zurueck(db):
    from core.geheim import KENNUNG
    from models import AthleteProfile

    profil = db.query(AthleteProfile).order_by(AthleteProfile.id.asc()).first()
    alt = profil.obsidian_api_key
    profil.obsidian_api_key = "geheimer-schluessel-123"
    db.commit()

    roh = db.execute(text("SELECT obsidian_api_key FROM athlete_profile WHERE id = :i"),
                     {"i": profil.id}).scalar()
    assert roh.startswith(KENNUNG)
    assert "geheimer-schluessel-123" not in roh

    db.expire_all()
    assert db.get(AthleteProfile, profil.id).obsidian_api_key == "geheimer-schluessel-123"

    profil = db.get(AthleteProfile, profil.id)
    profil.obsidian_api_key = alt
    db.commit()


def test_klartext_altwert_bleibt_lesbar():
    from core.geheim import entschluesseln

    assert entschluesseln("alter-klartext") == "alter-klartext"
