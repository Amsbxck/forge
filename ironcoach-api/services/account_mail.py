"""Mails rund um das Konto: Adresse bestätigen, Passwort zurücksetzen.

Beide Mails tragen einen Einmal-Link. Der Text bleibt knapp und nennt die
Gültigkeitsdauer — wer eine solche Mail bekommt, ohne sie angefordert zu
haben, soll sofort erkennen, dass nichts zu tun ist.
"""

import logging

from core.config import settings
from services.mail import send_mail

logger = logging.getLogger(__name__)

VERIFY_HOURS = 48
RESET_HOURS = 2


def _app_url() -> str:
    return (settings.PUBLIC_BASE_URL or "http://localhost:3000").rstrip("/")


def _rahmen(titel: str, absaetze: list[str], knopf_text: str, knopf_link: str, fuss: str) -> str:
    text_absaetze = "".join(
        f'<p style="color:#8a909e;font:400 14px/1.7 Helvetica,Arial,sans-serif;margin:12px 0 0">{a}</p>'
        for a in absaetze
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#07080f">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#07080f;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#111318;border:1px solid #1e2228;border-radius:12px;padding:28px">
        <tr><td>
          <div style="color:#00d4ff;font:800 26px/1 Helvetica,Arial,sans-serif;letter-spacing:.14em">FORGE</div>
          <div style="color:#3a3f4a;font:400 10px/1 Helvetica,Arial,sans-serif;letter-spacing:.2em;margin-top:6px">IRONCOACH AI</div>

          <p style="color:#e8eaf0;font:600 17px/1.4 Helvetica,Arial,sans-serif;margin:26px 0 0">{titel}</p>
          {text_absaetze}

          <a href="{knopf_link}" style="display:inline-block;margin-top:22px;background:#00d4ff20;
                    border:1px solid #00d4ff44;color:#00d4ff;text-decoration:none;border-radius:8px;
                    padding:11px 20px;font:700 13px/1 Helvetica,Arial,sans-serif;letter-spacing:.08em">{knopf_text}</a>

          <p style="color:#3a3f4a;font:400 11px/1.6 Helvetica,Arial,sans-serif;margin:24px 0 0">
            Falls der Knopf nicht funktioniert, kopiere diese Adresse in den Browser:<br>
            <span style="color:#8a909e;word-break:break-all">{knopf_link}</span>
          </p>
          <p style="color:#3a3f4a;font:400 11px/1.6 Helvetica,Arial,sans-serif;margin:16px 0 0">{fuss}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send_verification(email: str, name: str | None, token: str) -> bool:
    link = f"{_app_url()}/verify?token={token}"
    anrede = f"Hallo {name}" if name else "Hallo"

    text = f"""{anrede},

bitte bestätige deine E-Mail-Adresse für IronCoach:

{link}

Der Link gilt {VERIFY_HOURS} Stunden. Hast du dich nicht angemeldet, ignoriere
diese Nachricht — ohne Bestätigung passiert nichts.
"""
    html = _rahmen(
        "E-Mail-Adresse bestätigen",
        [
            f"{anrede}, bitte bestätige deine Adresse, damit dein Konto vollständig nutzbar ist.",
            f"Der Link gilt {VERIFY_HOURS} Stunden.",
        ],
        "ADRESSE BESTÄTIGEN",
        link,
        "Hast du dich nicht angemeldet, ignoriere diese Nachricht — ohne Bestätigung passiert nichts.",
    )
    return send_mail(email, "Bestätige deine E-Mail-Adresse", text, html)


def send_password_reset(email: str, name: str | None, token: str) -> bool:
    link = f"{_app_url()}/reset?token={token}"
    anrede = f"Hallo {name}" if name else "Hallo"

    text = f"""{anrede},

hier ist dein Link, um ein neues Passwort zu setzen:

{link}

Der Link gilt {RESET_HOURS} Stunden und lässt sich einmal verwenden.

Hast du das nicht angefordert, ist nichts passiert — dein bisheriges Passwort
gilt unverändert weiter. In dem Fall musst du nichts tun.
"""
    html = _rahmen(
        "Neues Passwort setzen",
        [
            f"{anrede}, über den folgenden Link kannst du ein neues Passwort vergeben.",
            f"Der Link gilt {RESET_HOURS} Stunden und lässt sich einmal verwenden.",
            "Hast du das nicht angefordert, ist nichts passiert — dein bisheriges Passwort gilt "
            "unverändert weiter.",
        ],
        "PASSWORT SETZEN",
        link,
        "Nach dem Zurücksetzen werden alle angemeldeten Geräte abgemeldet.",
    )
    return send_mail(email, "Neues Passwort für IronCoach", text, html)


def send_budget_warning(email: str, name: str | None, rest: float, guthaben: float,
                        aufgebraucht: bool = False) -> bool:
    """Hinweis, dass das Guthaben zur Neige geht — oder leer ist.

    Verschickt wird einmal beim Unterschreiten, nicht bei jedem Aufruf: Eine
    Mail nach jedem Wochenplan wäre nach zwei Wochen Spam und würde beim
    tatsächlichen Ende nicht mehr gelesen.
    """
    url = _app_url()
    anrede = f"Hallo {name}" if name else "Hallo"
    prozent = int(round(rest / guthaben * 100)) if guthaben else 0

    # Beträge einzeln formatieren statt im fertigen Satz Punkte zu ersetzen —
    # sonst wird auch der Satzpunkt zum Komma.
    def euro(betrag: float) -> str:
        return f"{betrag:.2f}".replace(".", ",")

    if aufgebraucht:
        titel = "Dein Guthaben ist aufgebraucht"
        betreff = "IronCoach: Guthaben aufgebraucht"
        kern = (
            "neue Wochenpläne und Chat-Antworten sind erst nach dem Aufladen "
            "wieder möglich."
        )
    else:
        titel = "Dein Guthaben geht zur Neige"
        betreff = f"IronCoach: noch {euro(rest)} € Guthaben"
        kern = (
            f"es sind noch {euro(rest)} € übrig, also rund {prozent} % deines "
            f"Guthabens von {euro(guthaben)} €."
        )

    text = f"""{anrede},

{kern[0].upper() + kern[1:]}

Ein Wochenplan kostet etwa 6 Cent, eine Frage an den Coach rund 1,5 Cent.
Alles andere — deine Einheiten, die Auswertung, Reflexionen und der
Strava-Abgleich — läuft unabhängig davon weiter.

Stand ansehen: {url}/profile
"""
    html = _rahmen(
        titel,
        [
            f"{anrede}, {kern}",
            "Ein Wochenplan kostet etwa 6 Cent, eine Frage an den Coach rund "
            "1,5 Cent.",
            "Alles andere — Einheiten, Auswertung, Reflexionen und der "
            "Strava-Abgleich — läuft unabhängig davon weiter.",
        ],
        "STAND ANSEHEN",
        f"{url}/profile",
        "Diese Nachricht kommt einmalig beim Unterschreiten der Schwelle.",
    )
    return send_mail(email, betreff, text, html)
