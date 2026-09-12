"""E-Mail-Versand, über SMTP oder über HTTPS.

Grundregel wie bei Obsidian: **Mail darf nie blockieren.** Eine Registrierung
scheitert nicht daran, dass ein Mailserver klemmt — der Versand läuft im
Hintergrund und Fehler landen im Log, nicht beim Nutzer.

Ursprünglich sprach dieses Modul nur SMTP, bewusst ohne Anbieter-Bindung:
SMTP versteht jeder Dienst, von Gmail bis Postmark. Das hielt genau bis zum
ersten Deployment. Railway sperrt ausgehendes SMTP auf allen Tarifen
unterhalb von Pro — der Versuch, smtp.gmail.com auf Port 587 zu erreichen,
endet dort mit "Network is unreachable", noch bevor irgendein Mailserver
antwortet. Es gibt keine Einstellung, die das behebt; der Weg ist zu.

Deshalb zusätzlich der Versand über HTTPS. Port 443 ist nirgends gesperrt,
und die Zustellung aus einem Rechenzentrum landet über einen echten
Versanddienst seltener im Spam als über ein privates Gmail-Konto.

SMTP bleibt vollwertig: lokal, auf eigenen Servern und überall, wo Port 587
offen ist, ist es der einfachere Weg ohne zusätzliches Konto.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# Brevo, weil es als einziger der gängigen Dienste ohne eigene Domain
# auskommt: Es genügt, eine einzelne Absenderadresse per Klick zu
# bestätigen. Wer eine Domain hat, kann sie hinterlegen, muss aber nicht.
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _provider() -> str:
    """Welcher Weg wird benutzt — ausdrücklich gesetzt oder abgeleitet."""
    gesetzt = (settings.MAIL_PROVIDER or "").strip().lower()
    if gesetzt:
        return gesetzt
    # Ohne ausdrückliche Angabe entscheidet, was konfiguriert ist. Das hält
    # bestehende Installationen am Laufen, die nur MAIL_HOST kennen.
    if settings.MAIL_API_KEY:
        return "brevo"
    return "smtp"


def mail_configured() -> bool:
    if not settings.MAIL_FROM:
        return False
    if _provider() == "brevo":
        return bool(settings.MAIL_API_KEY)
    return bool(settings.MAIL_HOST)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Eine Mail versenden. Gibt zurück, ob es geklappt hat — wirft nie."""
    if not mail_configured():
        logger.info("Mailversand übersprungen (nicht konfiguriert): %r an %s", subject, to)
        return False

    if _provider() == "brevo":
        return _send_brevo(to, subject, text, html)
    return _send_smtp(to, subject, text, html)


def _send_brevo(to: str, subject: str, text: str, html: str | None) -> bool:
    nutzlast = {
        "sender": {
            "email": settings.MAIL_FROM,
            "name": settings.MAIL_FROM_NAME or "IronCoach",
        },
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        nutzlast["htmlContent"] = html

    try:
        response = httpx.post(
            BREVO_URL,
            headers={
                # Abgeschnitten, weil ein Schlüssel fast immer über die
                # Zwischenablage in ein Eingabefeld wandert und dabei gern ein
                # Zeilenumbruch oder Leerzeichen mitkommt. Brevo antwortet dann
                # mit "Key not found" — einer Meldung, die jeden dazu bringt,
                # den Schlüssel neu zu erzeugen statt ihn anzusehen.
                "api-key": settings.MAIL_API_KEY.strip(),
                "accept": "application/json",
            },
            json=nutzlast,
            timeout=15,
        )
    except httpx.HTTPError as e:
        logger.warning("Mailversand fehlgeschlagen (%r an %s): %s", subject, to, e)
        return False

    if response.status_code >= 300:
        # Den Antworttext mitloggen: Brevo schreibt den eigentlichen Grund
        # dort hinein — nicht bestätigter Absender, Tageskontingent
        # erschöpft, Schlüssel abgelaufen. Ohne ihn steht im Log nur eine
        # Zahl, und die Suche beginnt von vorn.
        logger.warning(
            "Mailversand abgelehnt (%r an %s): %s %s%s",
            subject, to, response.status_code, response.text[:300],
            _schluessel_hinweis() if response.status_code == 401 else "",
        )
        return False

    logger.info("Mail verschickt: %r an %s", subject, to)
    return True


def _schluessel_hinweis() -> str:
    """Bei 401 sagen, welcher Schlüssel eingetragen ist.

    Brevo legt SMTP- und API-Schlüssel auf dieselbe Seite, und für die v3-API
    taugt nur der zweite. Wer den falschen erwischt, bekommt "Key not found"
    — eine Meldung, die nach einem ungültigen Schlüssel klingt, nicht nach
    einem Schlüssel der falschen Art. Das Präfix ist nicht geheim und
    beendet die Suche sofort.
    """
    key = (settings.MAIL_API_KEY or "").strip()
    if key.startswith("xsmtpsib-"):
        return (
            " — Hinweis: Das ist ein SMTP-Schlüssel (xsmtpsib-…). Für den "
            "Versand über HTTPS wird der API-Schlüssel gebraucht (xkeysib-…), "
            "in Brevo unter SMTP & API → Reiter API Keys."
        )
    if not key.startswith("xkeysib-"):
        return f" — Hinweis: Schlüssel beginnt mit {key[:9]!r}, erwartet wird 'xkeysib-'."
    return ""


def _send_smtp(to: str, subject: str, text: str, html: str | None) -> bool:
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
