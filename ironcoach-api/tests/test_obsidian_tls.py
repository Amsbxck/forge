"""Wann wird das Zertifikat der Obsidian-Gegenstelle geprüft?

Die Regel entscheidet darüber, ob ein neuer Athlet seine Anbindung ohne
Terminal fertigbekommt. Ist sie zu streng, scheitert er an einem
selbstsignierten Zertifikat und nimmt eine richtige Adresse wieder heraus;
ist sie zu lax, fällt die Prüfung auch dort weg, wo es ein echtes
Zertifikat gibt.
"""

import pytest

from services.obsidian.client import client_for_profile, pruefung_noetig


class _Profil:
    """Nur die Felder, die der Client anfasst — kein DB-Zugriff nötig."""

    def __init__(self, base_url=None, verify=None):
        self.obsidian_base_url = base_url
        self.obsidian_api_key = "k"
        self.obsidian_verify_tls = verify


@pytest.mark.parametrize(
    "adresse, erwartet",
    [
        # `tailscale serve` — echtes Zertifikat, also prüfen.
        ("https://amirs-macbook-air.tail47caa9.ts.net:27124", True),
        # Nackte Tailnet-Adresse aus der App — das Plugin selbst, selbstsigniert.
        ("https://100.72.215.32:27124", False),
        ("https://[fd7a:115c::1]:27124", False),
        # Lokale Entwicklung. Bis zur Automatik galt OBSIDIAN_VERIFY_TLS=False
        # für alle; das darf hier nicht kippen.
        ("https://localhost:27124", False),
        ("http://127.0.0.1:27123", False),
        ("https://macbook.local:27124", False),
        # Eigener Reverse-Proxy unter echtem Namen — prüfen.
        ("https://vault.example.org", True),
        # Keine Adresse: nichts zu prüfen, und der Client ist ohnehin aus.
        ("", False),
    ],
)
def test_automatik_folgt_der_adresse(adresse, erwartet):
    assert pruefung_noetig(adresse, None) is erwartet


@pytest.mark.parametrize("vorgabe", [True, False])
def test_festlegung_schlaegt_automatik(vorgabe):
    """Wer sich festlegt, bekommt seine Festlegung — gegen jede Adresse."""
    assert pruefung_noetig("https://100.72.215.32:27124", vorgabe) is vorgabe
    assert pruefung_noetig("https://x.ts.net", vorgabe) is vorgabe


def test_client_uebernimmt_die_entscheidung():
    """Der Weg vom Profil bis zum httpx-Aufruf, nicht nur die Regel allein."""
    assert client_for_profile(_Profil("https://100.72.215.32:27124")).verify is False
    assert client_for_profile(_Profil("https://a.tail47caa9.ts.net:27124")).verify is True
    # Festlegung im Profil kommt durch.
    assert client_for_profile(_Profil("https://100.72.215.32:27124", verify=True)).verify is True


def test_ohne_profil_kein_zugriff():
    """Kein Profil heißt keine Anbindung — nicht etwa die des Betreibers."""
    client = client_for_profile(None)
    assert client.enabled is False
