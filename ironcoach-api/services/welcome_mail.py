"""Begrüßungsmail nach der Registrierung.

Sie soll zwei Dinge leisten: einen freundlichen Empfang, und die vier
Schritte nennen, die vor dem ersten Wochenplan stehen. Ohne diese Reihenfolge
sieht ein neuer Athlet eine leere Oberfläche und muss raten, wo er anfängt.

Der Text ist bewusst kurz. Was ausführlich erklärt werden muss, gehört in die
Anwendung — eine Mail, die niemand zu Ende liest, hilft nicht.
"""

import logging

from core.config import settings
from services.mail import send_mail

logger = logging.getLogger(__name__)

STEPS = [
    ("Ziel wählen",
     "Sportart und Distanz — vom Sprint-Triathlon bis zum Marathon. "
     "Daraus ergeben sich Planlänge und Trainingsphasen."),
    ("Strava verbinden",
     "Ein Klick unter „Connect“. Deine Einheiten kommen danach automatisch an, "
     "mit Runden, Leistung und Herzfrequenz."),
    ("Testwoche absolvieren",
     "Eine Woche mit Testeinheiten. Daraus misst die App deine FTP, "
     "Schwellenpace und Herzfrequenzzonen — statt sie zu schätzen."),
    ("Ersten Wochenplan erstellen",
     "Ab hier plant der Coach auf Basis deiner echten Werte und passt "
     "nach jeder Einheit an."),
]


def _app_url() -> str:
    return (settings.PUBLIC_BASE_URL or "http://localhost:3000").rstrip("/")


def build_welcome(name: str | None, verify_token: str | None = None) -> tuple[str, str, str]:
    """Betreff, Text- und HTML-Fassung.

    Liegt ein Bestätigungstoken vor, führt der Knopf dorthin statt in die App:
    zwei getrennte Mails direkt nach der Registrierung wären eine zu viel,
    und die Bestätigung ist der nächste Schritt.
    """
    anrede = f"Hallo {name}" if name else "Hallo"
    url = _app_url()
    ziel = f"{url}/verify?token={verify_token}" if verify_token else url
    knopf = "ADRESSE BESTÄTIGEN" if verify_token else "ZUR APP"

    subject = "Willkommen bei IronCoach"

    text_steps = "\n\n".join(
        f"{i}. {title}\n   {body}" for i, (title, body) in enumerate(STEPS, 1)
    )
    text = f"""{anrede},

schön, dass du da bist. IronCoach plant dein Training nicht nach Schema F,
sondern anhand dessen, was du tatsächlich tust: jede Einheit wird mit dem
Plan abgeglichen, und was abweicht, fließt in die nächste Woche ein.

So kommst du zum ersten Plan:

{text_steps}

Ein Hinweis, der dir Frust erspart: Trag deine Werte nicht selbst ein, wenn
du sie nicht sicher kennst. Die Testwoche misst sie — geschätzte Zonen machen
jede spätere Vorgabe wertlos.

{"Bestätige zuerst deine E-Mail-Adresse:" if verify_token else "Los geht's:"} {ziel}

Viel Erfolg beim Training.
"""

    html_steps = "".join(
        f'''<tr>
              <td style="padding:0 14px 18px 0;vertical-align:top;width:28px">
                <div style="width:24px;height:24px;border-radius:12px;background:#00d4ff1f;
                            border:1px solid #00d4ff40;color:#00d4ff;font:700 12px/24px
                            Helvetica,Arial,sans-serif;text-align:center">{i}</div>
              </td>
              <td style="padding:0 0 18px 0;vertical-align:top">
                <div style="color:#e8eaf0;font:600 15px/1.4 Helvetica,Arial,sans-serif">{title}</div>
                <div style="color:#8a909e;font:400 13px/1.6 Helvetica,Arial,sans-serif;margin-top:3px">{body}</div>
              </td>
            </tr>'''
        for i, (title, body) in enumerate(STEPS, 1)
    )

    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#07080f">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#07080f;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#111318;border:1px solid #1e2228;border-radius:12px;padding:28px">
        <tr><td>
          <div style="color:#00d4ff;font:800 30px/1 Helvetica,Arial,sans-serif;letter-spacing:.14em">FORGE</div>
          <div style="color:#3a3f4a;font:400 10px/1 Helvetica,Arial,sans-serif;letter-spacing:.2em;margin-top:6px">IRONCOACH AI</div>

          <p style="color:#e8eaf0;font:400 15px/1.6 Helvetica,Arial,sans-serif;margin:26px 0 0">{anrede},</p>
          <p style="color:#8a909e;font:400 14px/1.7 Helvetica,Arial,sans-serif;margin:12px 0 0">
            schön, dass du da bist. IronCoach plant dein Training nicht nach Schema F, sondern
            anhand dessen, was du tatsächlich tust: jede Einheit wird mit dem Plan abgeglichen,
            und was abweicht, fließt in die nächste Woche ein.
          </p>

          <div style="color:#8a909e;font:600 10px/1 Helvetica,Arial,sans-serif;letter-spacing:.18em;margin:28px 0 16px">
            SO KOMMST DU ZUM ERSTEN PLAN
          </div>
          <table role="presentation" cellpadding="0" cellspacing="0" width="100%">{html_steps}</table>

          <div style="border-left:2px solid #00d4ff40;padding:2px 0 2px 12px;margin:6px 0 26px">
            <span style="color:#8a909e;font:400 13px/1.6 Helvetica,Arial,sans-serif">
              Trag deine Werte nicht selbst ein, wenn du sie nicht sicher kennst. Die Testwoche
              misst sie — geschätzte Zonen machen jede spätere Vorgabe wertlos.
            </span>
          </div>

          <a href="{ziel}" style="display:inline-block;background:#00d4ff20;border:1px solid #00d4ff44;
                    color:#00d4ff;text-decoration:none;border-radius:8px;padding:11px 20px;
                    font:700 13px/1 Helvetica,Arial,sans-serif;letter-spacing:.08em">{knopf}</a>

          <p style="color:#3a3f4a;font:400 11px/1.6 Helvetica,Arial,sans-serif;margin:26px 0 0">
            Diese Nachricht wurde einmalig zur Registrierung verschickt.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

    return subject, text, html


def send_welcome(email: str, name: str | None = None, verify_token: str | None = None) -> bool:
    subject, text, html = build_welcome(name, verify_token)
    return send_mail(email, subject, text, html)
