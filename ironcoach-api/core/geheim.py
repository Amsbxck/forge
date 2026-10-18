"""Geheimnisse in der Datenbank verschlüsselt ablegen.

Der Obsidian-Schlüssel eines Athleten stand im Klartext in der Datenbank. Wer
eine Sicherung oder einen Datenbankzugang bekam, hatte damit Schreibzugriff
auf die Vaults aller Athleten — auf deren eigenen Rechnern.

Jetzt liegt er verschlüsselt (Fernet: AES-128-CBC mit HMAC-SHA256). Der
Schlüssel kommt aus `DATA_ENCRYPTION_KEY`, ersatzweise aus `JWT_SECRET`.
Wird er gewechselt, lassen sich alte Werte nicht mehr lesen; sie gelten dann
als nicht gesetzt, und der Athlet trägt den Obsidian-Schlüssel neu ein.

Altwerte ohne Kennung werden unverändert gelesen und beim nächsten Speichern
verschlüsselt.
"""

import base64
import hashlib
import logging

from sqlalchemy.types import String, TypeDecorator

from core.config import settings

logger = logging.getLogger(__name__)

KENNUNG = "enc:v1:"


def _fernet():
    from cryptography.fernet import Fernet

    quelle = settings.DATA_ENCRYPTION_KEY or settings.JWT_SECRET
    if not quelle:
        return None
    schluessel = base64.urlsafe_b64encode(hashlib.sha256(quelle.encode()).digest())
    return Fernet(schluessel)


def verschluesseln(klartext: str | None) -> str | None:
    if not klartext or klartext.startswith(KENNUNG):
        return klartext
    f = _fernet()
    if f is None:
        # Ohne Geheimnis (lokale Entwicklung) bleibt es beim Klartext — der
        # Start verlangt im Betrieb ohnehin ein JWT_SECRET.
        return klartext
    return KENNUNG + f.encrypt(klartext.encode()).decode()


def entschluesseln(wert: str | None) -> str | None:
    if not wert or not wert.startswith(KENNUNG):
        return wert
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(wert[len(KENNUNG):].encode()).decode()
    except Exception:
        logger.warning("Verschlüsselter Wert nicht lesbar — Schlüssel gewechselt?")
        return None


class VerschluesselterText(TypeDecorator):
    """Spalte, die beim Schreiben ver- und beim Lesen entschlüsselt."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return verschluesseln(value)

    def process_result_value(self, value, dialect):
        return entschluesseln(value)
