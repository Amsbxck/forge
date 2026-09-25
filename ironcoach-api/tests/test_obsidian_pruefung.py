"""Die Verbindungsprüfung darf nicht strenger sein als der Abgleich.

Beobachtet in Produktion: "Vault neu ordnen" schrieb 112 Notizen fehlerfrei,
während "Verbindung testen" im selben Moment einen Zeitablauf im
TLS-Handschlag meldete. Die Prüfung sagte also das Gegenteil der Wahrheit —
und genau daraufhin nimmt jemand eine funktionierende Adresse wieder heraus.
"""

import httpx
import pytest

from services.obsidian import client as client_mod
from services.obsidian.client import ObsidianClient, ObsidianUnavailable


@pytest.fixture(autouse=True)
def frische_unterbrecher():
    """Die Unterbrecher leben auf Modulebene — zwischen Tests leeren."""
    client_mod._breakers.clear()
    yield
    client_mod._breakers.clear()


def test_pruefung_bekommt_mehr_zeit_als_der_normale_aufruf():
    """5 s reichen für einen kalten Tunnel nicht: SOCKS5, Pfadsuche im
    Tailnet, dann TLS mit vollständiger Kette."""
    c = ObsidianClient(base_url="https://x.ts.net:27124", api_key="k")
    assert c.PING_TIMEOUT_S > c.timeout


def test_pruefung_versucht_es_ein_zweites_mal(monkeypatch):
    """Der erste Versuch baut den Pfad auf, der zweite gelingt — genau das
    tat der Abgleich, und nur deshalb lief er, während die Prüfung aufgab."""
    versuche = []

    class Antwort:
        status_code = 200

        @staticmethod
        def json():
            return {"authenticated": True, "versions": {"self": "3.0"}}

    def fake_request(self, method, url, **kwargs):
        versuche.append(kwargs.get("_"))
        if len(versuche) == 1:
            raise httpx.ConnectTimeout("handshake operation timed out")
        return Antwort()

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)

    c = ObsidianClient(base_url="https://x.ts.net:27124", api_key="k")
    assert c.ping()["authenticated"] is True
    assert len(versuche) == 2


def test_die_zeitgrenze_der_pruefung_kommt_beim_client_an(monkeypatch):
    gesehen = {}
    echt = httpx.Client.__init__

    def fake_init(self, *a, **kw):
        gesehen["timeout"] = kw.get("timeout")
        echt(self, *a, **kw)

    class Antwort:
        status_code = 200

        @staticmethod
        def json():
            return {"authenticated": True}

    monkeypatch.setattr(httpx.Client, "__init__", fake_init)
    monkeypatch.setattr(httpx.Client, "request", lambda self, m, u, **k: Antwort())

    c = ObsidianClient(base_url="https://x.ts.net:27124", api_key="k")
    c.ping()
    assert gesehen["timeout"].read == c.PING_TIMEOUT_S
    assert gesehen["timeout"].connect == c.PING_TIMEOUT_S


def test_ein_kaputter_vault_sperrt_nicht_den_anderen(monkeypatch):
    """Der Unterbrecher lag auf Modulebene: Taminas nicht erreichbare Adresse
    öffnete ihn im stündlichen Reconcile-Lauf — und Amirs einwandfreier Vault
    war zwei Minuten lang mitgesperrt, ohne dass er etwas getan hatte."""
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)

    def immer_fehler(self, method, url, **kwargs):
        raise httpx.ConnectTimeout("nicht erreichbar")

    monkeypatch.setattr(httpx.Client, "request", immer_fehler)

    kaputt = ObsidianClient(base_url="https://100.69.89.51:27124", api_key="k")
    # Drei Fehlschläge — die Schwelle des Unterbrechers.
    for _ in range(3):
        with pytest.raises(ObsidianUnavailable):
            kaputt.get_note("Training/x.md")

    assert client_mod._breaker_fuer(kaputt.base_url).is_open
    assert not client_mod._breaker_fuer("https://amirs-macbook-air.ts.net:27124").is_open


def test_aufbau_bekommt_mehr_zeit_als_das_lesen(monkeypatch):
    """Der TLS-Handschlag hängt am Netz, nicht am Plugin.

    Beobachtet in Produktion: Solange Tailscale eine direkte Verbindung
    hatte, lief der Abgleich. Sobald es auf einen Relay zurückfiel, scheiterte
    er reihenweise mit "handshake operation timed out" — bei unveränderter,
    einwandfrei erreichbarer Gegenstelle. Die 5-s-Grenze galt für alles,
    also auch für den Aufbau.
    """
    gesehen = {}
    echt = httpx.Client.__init__

    def fake_init(self, *a, **kw):
        gesehen["timeout"] = kw.get("timeout")
        echt(self, *a, **kw)

    class Antwort:
        status_code = 200
        text = "inhalt"

    monkeypatch.setattr(httpx.Client, "__init__", fake_init)
    monkeypatch.setattr(httpx.Client, "request", lambda self, m, u, **k: Antwort())

    c = ObsidianClient(base_url="https://x.ts.net:27124", api_key="k")
    c.get_note("Training/x.md")

    grenze = gesehen["timeout"]
    assert grenze.connect == c.CONNECT_TIMEOUT_S
    # Lesen bleibt kurz: ein hängender Vault darf den Ingest nicht aufhalten.
    assert grenze.read == c.timeout
    assert grenze.connect > grenze.read
