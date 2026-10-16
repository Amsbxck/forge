"""E-Mail-Bestätigung: Fenster statt Hinweis, und ein Versand, der Wahrheit sagt.

Ein unbestätigter Nutzer kommt nicht mehr in die App, sondern sieht ein
Bestätigungsfenster. Damit das trägt, mussten drei Dinge stimmen, die vorher
nicht stimmten:

  * Die Login-Antwort trug nichts über die Bestätigung — eine Sperre wäre beim
    Anmelden gar nicht angekommen.
  * „Erneut senden" lief im Hintergrund und meldete immer „verschickt", auch
    wenn der Mailanbieter ablehnte.
  * Ein gescheiterter neuer Versand entwertete trotzdem die alten Links.

Und es darf niemand Bestehendes ausgesperrt werden: Admins, Betrieb ohne
Mailversand und Konten vor dem Stichtag (Migration 037) bleiben frei.
"""

import importlib.util
import pathlib
from datetime import datetime, timedelta

import pytest

VERSIONEN = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"


@pytest.fixture
def mail_an(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "MAIL_FROM", "coach@test.local")
    monkeypatch.setattr(settings, "MAIL_API_KEY", "test-key")
    return settings


@pytest.fixture
def neuer(db):
    """Ein frisch registrierter, unbestätigter Nutzer."""
    from models import AuthAction, User

    nutzer = User(email=f"neu-{datetime.utcnow().timestamp()}@test.local",
                  name="Neu", email_verified_at=None)
    db.add(nutzer)
    db.commit()
    yield nutzer
    db.query(AuthAction).filter(AuthAction.user_id == nutzer.id).delete()
    db.delete(db.get(User, nutzer.id))
    db.commit()


def _kopf(nutzer):
    from core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(nutzer.id, nutzer.email)}"}


# ── Wer gesperrt ist ────────────────────────────────────────────────────────

def test_unbestaetigt_ist_gesperrt(client, neuer, mail_an):
    daten = client.get("/api/auth/me", headers=_kopf(neuer)).json()
    assert daten["bestaetigung_noetig"] is True


def test_admin_ist_nie_gesperrt(client, db, neuer, mail_an):
    """Er ist der Notschalter für alle anderen."""
    neuer.is_admin = True
    db.commit()
    assert client.get("/api/auth/me", headers=_kopf(neuer)).json()["bestaetigung_noetig"] is False


def test_ohne_mailversand_niemand_gesperrt(client, neuer, mail_an, monkeypatch):
    """Ohne Versand käme die Mail nie an — jeder neue Nutzer säße fest."""
    monkeypatch.setattr(mail_an, "MAIL_API_KEY", "")
    monkeypatch.setattr(mail_an, "MAIL_HOST", "", raising=False)
    assert client.get("/api/auth/me", headers=_kopf(neuer)).json()["bestaetigung_noetig"] is False


def test_ohne_anmeldung_niemand_gesperrt(neuer, mail_an, monkeypatch):
    from core.deps import bestaetigung_noetig

    monkeypatch.setattr(mail_an, "AUTH_REQUIRED", False)
    assert bestaetigung_noetig(neuer) is False


def test_login_antwort_traegt_die_sperre(client, db, mail_an):
    """Vorher fehlte das Feld — die Sperre kam beim Anmelden nie an."""
    from core.security import hash_password
    from models import User

    adresse = f"login-{datetime.utcnow().timestamp()}@test.local"
    nutzer = User(email=adresse, password_hash=hash_password("geheim-123456"))
    db.add(nutzer)
    db.commit()
    try:
        daten = client.post("/api/auth/login",
                            json={"email": adresse, "password": "geheim-123456"}).json()
        assert daten["bestaetigung_noetig"] is True
        assert daten["email_verified"] is False
    finally:
        db.delete(db.get(User, nutzer.id))
        db.commit()


# ── Erneut senden ───────────────────────────────────────────────────────────

def _alter_link(db, nutzer, minuten_alt=5):
    """Ein Willkommenslink, als wäre er vor ein paar Minuten verschickt worden."""
    from core.security import new_action_token
    from models import AuthAction

    klartext, token_hash = new_action_token()
    db.add(AuthAction(
        user_id=nutzer.id, kind="email_verify", token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_at=datetime.utcnow() - timedelta(minutes=minuten_alt),
    ))
    db.commit()
    return klartext


def test_gescheiterter_versand_wird_gemeldet_und_alter_link_bleibt(client, db, neuer, mail_an, monkeypatch):
    """Der Mailanbieter lehnt ab: Das Fenster muss es erfahren, und der alte
    Link — der vielleicht doch angekommen ist — darf nicht verfallen."""
    import routers.auth as auth

    alt = _alter_link(db, neuer)
    monkeypatch.setattr(auth, "send_verification", lambda *a, **k: False)

    daten = client.post("/api/auth/resend-verification", headers=_kopf(neuer)).json()
    assert daten["angenommen"] is False
    assert daten["status"] == "fehlgeschlagen"

    db.refresh(neuer)
    assert neuer.verify_mail_status == "fehlgeschlagen"
    # Der alte Link funktioniert weiterhin.
    antwort = client.post("/api/auth/verify-email", json={"token": alt})
    assert antwort.status_code == 200


def test_angenommener_versand_entwertet_alte_links(client, db, neuer, mail_an, monkeypatch):
    import routers.auth as auth

    alt = _alter_link(db, neuer)
    gesendet = {}

    def senden(email, name, token):
        gesendet["token"] = token
        return True

    monkeypatch.setattr(auth, "send_verification", senden)
    daten = client.post("/api/auth/resend-verification", headers=_kopf(neuer)).json()
    assert daten["angenommen"] is True

    assert client.post("/api/auth/verify-email", json={"token": alt}).status_code == 400
    assert client.post("/api/auth/verify-email",
                       json={"token": gesendet["token"]}).status_code == 200


def test_zweimal_hintereinander_wird_gebremst(client, db, neuer, mail_an, monkeypatch):
    """Synchroner Versand und ein Kontingent beim Anbieter — ein Doppelklick
    soll keine zweite Mail auslösen."""
    import routers.auth as auth

    monkeypatch.setattr(auth, "send_verification", lambda *a, **k: True)
    assert client.post("/api/auth/resend-verification", headers=_kopf(neuer)).status_code == 200
    zweite = client.post("/api/auth/resend-verification", headers=_kopf(neuer))
    assert zweite.status_code == 429
    assert "Minute" in zweite.json()["detail"]


def test_registrierung_haelt_den_versandstatus_fest(client, db, mail_an, monkeypatch):
    """Die Willkommensmail geht im Hintergrund raus. Scheitert sie, steht das
    am Konto — das Fenster sagt es dem Nutzer gleich."""
    import routers.auth as auth
    from models import AthleteProfile, AuthAction, User

    monkeypatch.setattr(auth, "send_welcome", lambda *a, **k: False)
    adresse = f"reg-{datetime.utcnow().timestamp()}@test.local"
    antwort = client.post("/api/auth/register",
                          json={"email": adresse, "password": "geheim-123456", "name": "R"})
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["bestaetigung_noetig"] is True

    db.expire_all()
    nutzer = db.query(User).filter(User.email == adresse).one()
    try:
        assert nutzer.verify_mail_status == "fehlgeschlagen"
        assert nutzer.verify_mail_at is not None
    finally:
        db.query(AuthAction).filter(AuthAction.user_id == nutzer.id).delete()
        db.query(AthleteProfile).filter(AthleteProfile.user_id == nutzer.id).delete()
        db.delete(nutzer)
        db.commit()


# ── Notschalter ─────────────────────────────────────────────────────────────

def test_admin_kann_ein_konto_von_hand_bestaetigen(client, db, neuer, mail_an):
    from models import User

    admin = User(email=f"admin-{datetime.utcnow().timestamp()}@test.local", is_admin=True,
                 email_verified_at=datetime.utcnow())
    db.add(admin)
    db.commit()
    try:
        antwort = client.post("/api/auth/admin/verify", headers=_kopf(admin),
                              json={"email": neuer.email.upper()})
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["status"] == "bestaetigt"
        db.refresh(neuer)
        assert neuer.email_verified_at is not None
    finally:
        db.delete(db.get(User, admin.id))
        db.commit()


def test_notschalter_nur_fuer_admins(client, db, neuer, mail_an):
    antwort = client.post("/api/auth/admin/verify", headers=_kopf(neuer),
                          json={"email": neuer.email})
    assert antwort.status_code == 403


# ── Migration 037: niemand Bestehendes wird ausgesperrt ────────────────────

def _m037():
    pfad = next(VERSIONEN.glob("037_*.py"))
    spec = importlib.util.spec_from_file_location("migration_037", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_migration_037_bestaetigt_altkonten(db):
    from models import User

    m037 = _m037()
    stichtag = datetime(2026, 10, 15)
    zeit = datetime.utcnow().timestamp()
    alt = User(email=f"alt-{zeit}@test.local", created_at=stichtag - timedelta(days=20))
    neu = User(email=f"neu37-{zeit}@test.local", created_at=stichtag + timedelta(hours=10))
    chef = User(email=f"chef-{zeit}@test.local", is_admin=True,
                created_at=stichtag + timedelta(hours=11))
    db.add_all([alt, neu, chef])
    db.commit()
    try:
        m037.altkonten_bestaetigen(db.connection(), stichtag)
        db.commit()
        for u in (alt, neu, chef):
            db.refresh(u)
        assert alt.email_verified_at == alt.created_at
        assert neu.email_verified_at is None          # muss bestätigen
        assert chef.email_verified_at is not None     # Admin nie gesperrt
    finally:
        for u in (alt, neu, chef):
            db.delete(db.get(User, u.id))
        db.commit()
