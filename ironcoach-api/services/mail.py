"""E-Mail-Versand über SMTP.

Bewusst ohne zusätzliche Abhängigkeit und ohne Anbieter-Bindung: SMTP spricht
jeder Dienst, von Gmail bis Postmark. Die Zugangsdaten stehen in der
Umgebung; fehlen sie, wird nichts versendet und nur protokolliert.

Grundregel wie bei Obsidian: **Mail darf nie blockieren.** Eine Registrierung
scheitert nicht daran, dass ein Mailserver klemmt — der Versand läuft im
Hintergrund und Fehler landen im Log, nicht beim Nutzer.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from core.config import settings

logger = logging.getLogger(__name__)


def mail_configured() -> bool:
    return bool(settings.MAIL_HOST and settings.MAIL_FROM)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Eine Mail versenden. Gibt zurück, ob es geklappt hat — wirft nie."""
    if not mail_configured():
        logger.info("Mailversand übersprungen (nicht konfiguriert): %r an %s", subject, to)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.MAIL_FROM_NAME or "IronCoach", settings.MAIL_FROM))
    message["To"] = to
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        if settings.MAIL_SSL:
            server = smtplib.SMTP_SSL(
                settings.MAIL_HOST, settings.MAIL_PORT, timeout=15,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(settings.MAIL_HOST, settings.MAIL_PORT, timeout=15)
        with server:
            if settings.MAIL_STARTTLS and not settings.MAIL_SSL:
                server.starttls(context=ssl.create_default_context())
            if settings.MAIL_USER:
                server.login(settings.MAIL_USER, settings.MAIL_PASSWORD)
            server.send_message(message)
        logger.info("Mail verschickt: %r an %s", subject, to)
        return True
    except Exception as e:  # pragma: no cover - Netzwerk
        logger.warning("Mailversand fehlgeschlagen (%r an %s): %s", subject, to, e)
        return False
