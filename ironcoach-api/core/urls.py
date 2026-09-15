"""Wohin der Browser des Athleten geschickt wird.

Eine Stelle für eine Frage, die an mehreren Orten auftaucht: Links in
E-Mails, die Rückleitung nach einer OAuth-Freigabe. Beide meinen dieselbe
Adresse — die des Frontends, nicht die der API.

Bis hierher stand die Auflösung nur im Mailmodul. Der Strava-Callback hatte
gar keine und lieferte stattdessen JSON aus: Der Athlet klickte bei Strava
auf „Autorisieren" und landete auf der API-Domain vor einer rohen
Textzeile — technisch erfolgreich, für den Nutzer ein Sackgassenbildschirm.
"""

from core.config import settings

# Vite im Entwicklungsbetrieb. Nur als Rückfall — im Betrieb ist
# PUBLIC_BASE_URL gesetzt, sonst verweigert die App beim Start den Dienst.
LOKALE_VORGABE = "http://localhost:3000"


def app_url() -> str:
    """Basisadresse des Frontends, ohne Schrägstrich am Ende.

    Drei Quellen, in dieser Reihenfolge:

    1. `FRONTEND_URL` — die ausdrückliche Angabe, falls gesetzt.
    2. `PUBLIC_BASE_URL` — bisher die einzige Quelle. Sie trägt in vielen
       Installationen die Frontend-Adresse, wird aber auch als Basis für die
       Webhook-Adresse benutzt, die auf die API zeigen muss. Wer beides
       getrennt braucht, setzt `FRONTEND_URL`.
    3. Der erste Eintrag aus `CORS_ORIGINS`. Das ist per Definition die
       Adresse, von der aus der Browser die API aufruft — also die des
       Frontends. Als Rückfall verlässlicher als eine Vermutung.
    """
    for kandidat in (settings.FRONTEND_URL, settings.PUBLIC_BASE_URL, *settings.cors_origins):
        if kandidat:
            return kandidat.rstrip("/")
    return LOKALE_VORGABE


def app_pfad(pfad: str, **parameter: str) -> str:
    """Vollständige Adresse einer Seite im Frontend.

    Die Parameter werden kodiert, nicht angehängt: Eine Fehlermeldung von
    Strava kann Leerzeichen und Sonderzeichen enthalten, und die zerlegten
    sonst die Adresse.
    """
    from urllib.parse import urlencode

    ziel = f"{app_url()}/{pfad.lstrip('/')}"
    return f"{ziel}?{urlencode(parameter)}" if parameter else ziel
