"""Passwörter und Zugangstoken.

Bewusst schlank: bcrypt für Passwörter, ein signiertes JWT als Sitzung.
Kein Refresh-Token-Karussell — bei einer Trainings-App ist ein Token mit
mehrtägiger Laufzeit angemessen, und ein Logout löscht ihn lokal.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from core.config import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

# Ohne gesetztes Geheimnis wird eines erzeugt — dann gelten Tokens aber nur
# bis zum nächsten Neustart. Das ist für die Entwicklung richtig und im
# Betrieb ein Fehler, deshalb die Warnung.
_FALLBACK_SECRET = secrets.token_urlsafe(48)


def _secret() -> str:
    if settings.JWT_SECRET:
        return settings.JWT_SECRET
    logger.warning(
        "JWT_SECRET ist nicht gesetzt — es wird ein flüchtiges Geheimnis benutzt. "
        "Nach jedem Neustart müssen sich alle neu anmelden."
    )
    return _FALLBACK_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Passwort prüfen.

    Ein Konto ohne Hash gilt als nicht anmeldbar — sonst käme man in ein
    noch nicht übernommenes Altkonto ohne Passwort hinein.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:  # beschädigter Hash
        return False


def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        # Zusätzlich in Millisekunden: `iat` rundet auf ganze Sekunden ab,
        # und der Widerruf beim Abmelden fällt oft in dieselbe Sekunde wie
        # die Ausstellung. Ohne feinere Auflösung überlebt das Token seinen
        # eigenen Widerruf.
        "iat_ms": int(now.timestamp() * 1000),
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Token prüfen. None bei ungültig oder abgelaufen — nie eine Ausnahme
    nach außen, damit ein abgelaufenes Token als 401 endet und nicht als 500."""
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        logger.debug("Token abgelehnt: %s", e)
        return None


def user_id_from_token(token: str | None) -> int | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


# --- Einmal-Token für Links in E-Mails ---------------------------------------
#
# Der Klartext existiert nur im verschickten Link; gespeichert wird ein
# SHA-256-Hash. Damit lässt sich aus einem Datenbankleck kein Konto
# übernehmen. Kein bcrypt: der Wert ist bereits zufällig und lang genug,
# ein langsamer Hash brächte hier nichts außer Rechenzeit.

def new_action_token() -> tuple[str, str]:
    """Gibt (Klartext für den Link, Hash für die Datenbank) zurück."""
    klartext = secrets.token_urlsafe(32)
    return klartext, hash_action_token(klartext)


def hash_action_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, gespeichert: str) -> bool:
    """Vergleich in konstanter Zeit — sonst verrät die Dauer den Anfang des
    Tokens und lässt sich schrittweise erraten."""
    return hmac.compare_digest(hash_action_token(token), gespeichert)


# --- Sperre nach Fehlversuchen ----------------------------------------------
#
# Gestaffelt statt fest: die ersten Versuche sind ein Vertipper, ab dem
# fünften wird gewartet, und die Wartezeit verdoppelt sich. Nach zehn
# Versuchen bleibt es bei einer Stunde — ein dauerhaftes Sperren würde
# fremden Leuten erlauben, ein Konto durch bloßes Raten stillzulegen.

FEHLVERSUCHE_BIS_SPERRE = 5
MAX_SPERRE_MINUTEN = 60


def lock_duration(failed_logins: int) -> timedelta | None:
    """Wie lange nach diesem Fehlversuch gesperrt wird."""
    if failed_logins < FEHLVERSUCHE_BIS_SPERRE:
        return None
    stufe = failed_logins - FEHLVERSUCHE_BIS_SPERRE      # 0, 1, 2 …
    minuten = min(MAX_SPERRE_MINUTEN, 2 ** stufe)
    return timedelta(minutes=minuten)


def token_issued_after(payload: dict, valid_from: datetime | None) -> bool:
    """Wurde das Token nach dem letzten Widerruf ausgestellt?

    Ein JWT lässt sich nicht einsammeln. Beim Abmelden, beim Passwortwechsel
    und nach einem Zurücksetzen wird deshalb eine Marke am Konto gesetzt;
    alles, was davor ausgestellt wurde, gilt nicht mehr.

    Verglichen wird über `iat_ms`. Der Standardwert `iat` steht nur in
    Sekunden zur Verfügung und wäre zu grob: ein Abmelden in derselben
    Sekunde wie die Ausstellung würde das Token nicht erfassen.
    """
    if valid_from is None:
        return True

    vergleich = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=timezone.utc)
    grenze_ms = vergleich.timestamp() * 1000

    ausgestellt_ms = payload.get("iat_ms")
    if ausgestellt_ms is None:
        # Tokens ohne diesen Anspruch stammen aus der Zeit vor der Prüfung
        # und werden verworfen — sicherer, als sie durchzulassen.
        return False

    return float(ausgestellt_ms) >= grenze_ms
