"""Versandweg und Verhalten im Fehlerfall.

Der wichtigste Punkt steht im letzten Test: Ein gescheiterter Versand darf
nie nach oben durchschlagen. Eine Registrierung, die daran scheitert, dass
ein Mailserver klemmt, wäre der schlechteste Fehler von allen — der Nutzer
hätte ein halbes Konto und keine Erklärung.
"""

import httpx
import pytest

from core.config import settings
from services import mail


@pytest.fixture
def leere_konfiguration(monkeypatch):
    for feld, wert in [
        ("MAIL_PROVIDER", ""), ("MAIL_API_KEY", ""), ("MAIL_HOST", ""),
        ("MAIL_FROM", ""), ("MAIL_FROM_NAME", "IronCoach"),
    ]:
        monkeypatch.setattr(settings, feld, wert, raising=False)
    return monkeypatch


def test_weg_wird_aus_der_konfiguration_abgeleitet(leere_konfiguration):
    """Bestehende Installationen kennen nur MAIL_HOST — die bleiben bei SMTP."""
    leere_konfiguration.setattr(settings, "MAIL_HOST", "smtp.gmail.com")
    assert mail._provider() == "smtp"

    # Sobald ein Schlüssel da ist, geht es über HTTPS.
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    assert mail._provider() == "brevo"

    # Eine ausdrückliche Angabe schlägt die Ableitung.
    leere_konfiguration.setattr(settings, "MAIL_PROVIDER", "smtp")
    assert mail._provider() == "smtp"


def test_ohne_konfiguration_wird_nur_protokolliert(leere_konfiguration):
    assert mail.mail_configured() is False
    assert mail.send_mail("a@b.de", "Betreff", "Text") is False


def test_halbe_konfiguration_zaehlt_nicht(leere_konfiguration):
    """Schlüssel ohne Absender ist keine Konfiguration.

    Sonst liefe der Versand an und scheiterte erst beim Anbieter — mit einer
    Meldung, die nicht verrät, dass schlicht ein Feld fehlt.
    """
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    assert mail.mail_configured() is False

    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    assert mail.mail_configured() is True


def test_brevo_bekommt_absender_empfaenger_und_beide_formate(leere_konfiguration):
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    gesehen = {}

    def fake_post(url, **kwargs):
        gesehen["url"] = url
        gesehen["headers"] = kwargs["headers"]
        gesehen["json"] = kwargs["json"]
        return httpx.Response(201, json={"messageId": "1"})

    leere_konfiguration.setattr(mail.httpx, "post", fake_post)

    assert mail.send_mail("athlet@example.org", "Betreff", "Text", "<p>Text</p>") is True
    assert gesehen["url"] == mail.BREVO_URL
    assert gesehen["headers"]["api-key"] == "xkeysib-test"
    assert gesehen["json"]["sender"]["email"] == "coach@example.org"
    assert gesehen["json"]["to"] == [{"email": "athlet@example.org"}]
    assert gesehen["json"]["textContent"] == "Text"
    assert gesehen["json"]["htmlContent"] == "<p>Text</p>"


def test_ohne_html_kein_leeres_html_feld(leere_konfiguration):
    """Ein leeres htmlContent würde als leere Mail zugestellt."""
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    gesehen = {}

    leere_konfiguration.setattr(
        mail.httpx, "post",
        lambda url, **kw: (gesehen.update(kw["json"]), httpx.Response(201))[1],
    )
    mail.send_mail("a@b.de", "Betreff", "Nur Text")
    assert "htmlContent" not in gesehen


@pytest.mark.parametrize(
    "antwort",
    [
        lambda *a, **k: httpx.Response(400, text="sender not verified"),
        lambda *a, **k: httpx.Response(401, text="key expired"),
        lambda *a, **k: httpx.Response(429, text="daily limit"),
    ],
)
def test_ablehnung_wirft_nicht(leere_konfiguration, antwort):
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    leere_konfiguration.setattr(mail.httpx, "post", antwort)
    assert mail.send_mail("a@b.de", "Betreff", "Text") is False


def test_netzwerkfehler_wirft_nicht(leere_konfiguration):
    """Genau der Fall, der auf Railway auftrat: die Verbindung kommt nicht zustande."""
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "xkeysib-test")
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")

    def platzt(*a, **k):
        raise httpx.ConnectError("[Errno 101] Network is unreachable")

    leere_konfiguration.setattr(mail.httpx, "post", platzt)
    assert mail.send_mail("a@b.de", "Betreff", "Text") is False


@pytest.mark.parametrize(
    "key, erwartet_im_hinweis",
    [
        ("xsmtpsib-abc", "SMTP-Schlüssel"),
        ("abc123", "erwartet wird"),
        ("xkeysib-abc", ""),          # richtiger Typ — kein Hinweis
    ],
)
def test_hinweis_bei_401_nennt_den_schluesseltyp(leere_konfiguration, key, erwartet_im_hinweis, caplog):
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", key)
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    leere_konfiguration.setattr(
        mail.httpx, "post",
        lambda url, **kw: httpx.Response(401, text='{"message":"Key not found"}'),
    )
    with caplog.at_level("WARNING"):
        assert mail.send_mail("a@b.de", "Betreff", "Text") is False
    text = caplog.text
    if erwartet_im_hinweis:
        assert erwartet_im_hinweis in text
    else:
        assert "Hinweis" not in text


def test_leerzeichen_im_schluessel_wird_abgeschnitten(leere_konfiguration):
    """Der Zeilenumbruch aus der Zwischenablage darf nicht in den Header."""
    leere_konfiguration.setattr(settings, "MAIL_API_KEY", "  xkeysib-abc\n")
    leere_konfiguration.setattr(settings, "MAIL_FROM", "coach@example.org")
    gesehen = {}
    leere_konfiguration.setattr(
        mail.httpx, "post",
        lambda url, **kw: (gesehen.update(kw["headers"]), httpx.Response(201))[1],
    )
    mail.send_mail("a@b.de", "Betreff", "Text")
    assert gesehen["api-key"] == "xkeysib-abc"
