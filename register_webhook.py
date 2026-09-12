"""Strava-Webhook anmelden, auflisten und löschen.

Es gibt **eine** Anmeldung je Strava-Anwendung. Zeigt sie noch auf eine alte
Adresse, muss sie weg, bevor eine neue angelegt werden kann.

Alle Werte kommen aus der Umgebung oder aus `.env` — hier standen sie einmal
fest im Code, inklusive des Client-Secrets. Die Datei liegt in einem
öffentlichen Repository; das Secret war damit für jeden lesbar und musste
ausgetauscht werden. Deshalb gibt es hier keine Vorgabewerte mehr, auch keine
scheinbar harmlosen: Sobald ein Geheimnis einmal im Quelltext steht, wandert
es in die Versionsgeschichte und ist dort nicht mehr einzufangen.

    python register_webhook.py                 # anmelden
    python register_webhook.py --list          # bestehende anzeigen
    python register_webhook.py --delete <id>   # eine entfernen

Die Rückrufadresse kommt aus CALLBACK_URL, ersatzweise aus PUBLIC_API_URL
plus "/webhook".
"""

import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.strava.com/api/v3/push_subscriptions"


def aus_env_datei(pfad: str = ".env") -> None:
    """`.env` nachladen, ohne vorhandene Umgebungsvariablen zu überschreiben.

    Wer die Werte per `export` gesetzt hat, meint das auch so — die Datei ist
    nur der Rückfall.
    """
    if not os.path.exists(pfad):
        return
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            schluessel, _, wert = zeile.partition("=")
            os.environ.setdefault(schluessel.strip(), wert.strip())


def pflicht(name: str) -> str:
    wert = os.environ.get(name, "").strip()
    if not wert:
        sys.exit(
            f"{name} fehlt. Setze die Variable oder trage sie in .env ein — "
            "in den Quelltext gehört sie nicht."
        )
    return wert


def anfrage(methode: str, url: str, felder: dict | None = None) -> tuple[int, str]:
    daten = urllib.parse.urlencode(felder).encode() if felder else None
    req = urllib.request.Request(url, data=daten, method=methode)
    if daten:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as antwort:
            return antwort.status, antwort.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> None:
    aus_env_datei()
    client_id = pflicht("STRAVA_CLIENT_ID")
    client_secret = pflicht("STRAVA_CLIENT_SECRET")
    zugang = {"client_id": client_id, "client_secret": client_secret}

    args = sys.argv[1:]

    if args and args[0] == "--list":
        code, text = anfrage("GET", f"{API}?{urllib.parse.urlencode(zugang)}")
        print(f"HTTP {code}\n{text}")
        return

    if args and args[0] == "--delete":
        if len(args) < 2:
            sys.exit("Aufruf: python register_webhook.py --delete <id>")
        code, text = anfrage(
            "DELETE", f"{API}/{args[1]}?{urllib.parse.urlencode(zugang)}"
        )
        print(f"HTTP {code}" + (f"\n{text}" if text.strip() else " — gelöscht"))
        return

    verify_token = pflicht("STRAVA_VERIFY_TOKEN")
    callback = os.environ.get("CALLBACK_URL", "").strip()
    if not callback:
        basis = os.environ.get("PUBLIC_API_URL", "").strip().rstrip("/")
        if not basis:
            sys.exit(
                "CALLBACK_URL fehlt. Beispiel:\n"
                "  export CALLBACK_URL=https://deine-adresse/webhook"
            )
        callback = f"{basis}/webhook"

    # Strava ruft die Adresse sofort auf und erwartet den Verify-Token zurück.
    # Sie muss also öffentlich erreichbar sein, bevor das hier läuft — und der
    # Token muss mit dem übereinstimmen, den der Server in seiner Umgebung hat.
    print(f"Melde an: {callback}")
    code, text = anfrage("POST", API, {
        **zugang,
        "callback_url": callback,
        "verify_token": verify_token,
    })
    print(f"HTTP {code}\n{text}")
    if code >= 400:
        print(
            "\nHäufigste Ursachen:\n"
            "  • Es besteht bereits eine Anmeldung — erst --list, dann --delete\n"
            "  • STRAVA_VERIFY_TOKEN stimmt nicht mit dem des Servers überein\n"
            "  • Die Adresse ist von außen nicht erreichbar oder nicht HTTPS"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
