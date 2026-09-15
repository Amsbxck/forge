"""Zwei Übergänge, an denen der Athlet nicht im Leeren stehen darf.

1. Das Willkommensfenster erscheint erst nach bestätigter E-Mail. Vorher
   fragte es nach Wettkampfziel, Zonen und Einschränkungen, während das
   Konto noch niemandem nachweislich gehörte.
2. Nach der Freigabe bei Strava steht ein Mensch vor einem Browserfenster.
   Der Callback antwortete mit JSON — der Athlet landete auf der API-Domain
   vor einer rohen Textzeile, ohne Weg zurück.
"""

from datetime import datetime

import pytest

from core.urls import app_pfad, app_url
from models import AthleteProfile, User


@pytest.fixture
def einzelplatz(monkeypatch):
    """Lokaler Betrieb ohne Anmeldeweg (AUTH_REQUIRED=false) — die Vorgabe
    der Testumgebung."""
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)


@pytest.fixture
def konto(db):
    profil = db.query(AthleteProfile).first()
    return db.query(User).filter(User.id == profil.user_id).one()


@pytest.fixture
def angemeldet(monkeypatch, konto):
    """Betrieb mit Anmeldung — Schalter um *und* ein gültiges Token dazu.

    Nur den Schalter umzulegen genügt nicht: Die Anfrage selbst wird damit
    anmeldepflichtig und endete mit 401, bevor der geprüfte Code überhaupt
    liefe.
    """
    from core.config import settings
    from core.security import create_access_token

    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    token = create_access_token(konto.id, konto.email)
    return {"Authorization": f"Bearer {token}"}


def test_willkommensfenster_wartet_auf_die_bestaetigung(client, db, konto, angemeldet):
    konto.email_verified_at = None
    db.commit()

    daten = client.get("/api/profile/intake", headers=angemeldet).json()
    assert daten["faellig"] is False
    # Die Oberfläche muss "noch gesperrt" von "schon erledigt" unterscheiden
    # können — sonst zeigt sie einfach nichts und erklärt nichts.
    assert daten["wartet_auf_bestaetigung"] is True


def test_nach_der_bestaetigung_erscheint_es(client, db, konto, angemeldet):
    konto.email_verified_at = datetime.utcnow()
    db.commit()
    profil = db.query(AthleteProfile).first()
    profil.intake_done_at = None
    db.commit()

    daten = client.get("/api/profile/intake", headers=angemeldet).json()
    assert daten["faellig"] is True
    assert daten["wartet_auf_bestaetigung"] is False


def test_erledigtes_fenster_kommt_nicht_wieder(client, db, konto, angemeldet):
    konto.email_verified_at = datetime.utcnow()
    profil = db.query(AthleteProfile).first()
    profil.intake_done_at = datetime.utcnow()
    db.commit()

    daten = client.get("/api/profile/intake", headers=angemeldet).json()
    assert daten["faellig"] is False
    assert daten["wartet_auf_bestaetigung"] is False


# --- Rückleitung von Strava ---------------------------------------------

def test_adresse_wird_kodiert_zusammengesetzt():
    """Eine Fehlermeldung von Strava kann Leerzeichen enthalten."""
    ziel = app_pfad("/connect", strava="fehler", grund="token ungültig & weg")
    assert ziel.startswith(f"{app_url()}/connect?")
    assert " " not in ziel
    assert "strava=fehler" in ziel


def test_callback_ohne_state_leitet_zurueck_statt_zu_scheitern(client):
    antwort = client.get(
        "/api/strava/callback?code=egal", follow_redirects=False
    )
    # 303: Der Browser soll das Ziel mit GET holen.
    assert antwort.status_code == 303
    ziel = antwort.headers["location"]
    assert ziel.startswith(app_url())
    assert "/connect" in ziel
    assert "strava=fehler" in ziel


def test_callback_mit_kaputtem_code_leitet_ebenfalls_zurueck(client, db, konto):
    """Kein roher Fehlerbildschirm auf der API-Domain."""
    from core.security import create_access_token

    state = create_access_token(konto.id, konto.email)
    antwort = client.get(
        f"/api/strava/callback?code=ungueltig&state={state}", follow_redirects=False
    )
    assert antwort.status_code == 303
    assert "strava=fehler" in antwort.headers["location"]
    assert "/connect" in antwort.headers["location"]


def test_lokaler_einzelplatzbetrieb_wird_nicht_ausgesperrt(client, db, konto, einzelplatz):
    """Ohne Anmeldeweg gibt es keine Adresse zu bestätigen.

    Die Sperre dürfte das Fenster dort sonst für immer zurückhalten — und
    lokal käme man nie zur Einrichtung.
    """
    konto.email_verified_at = None
    profil = db.query(AthleteProfile).first()
    profil.intake_done_at = None
    db.commit()

    daten = client.get("/api/profile/intake").json()
    assert daten["faellig"] is True
    assert daten["wartet_auf_bestaetigung"] is False
