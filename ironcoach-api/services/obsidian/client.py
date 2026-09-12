"""HTTP-Client für die Obsidian Local REST API.

Grundregel: Obsidian ist eine Nebenwirkung, nie ein Blocker. Der Vault kann
zu sein, der Rechner schlafen, Tailscale down — der Strava-Ingest muss
trotzdem durchlaufen. Deshalb kurze Timeouts, wenige Retries und ein
Circuit Breaker, damit ein Reconcile-Lauf nicht bei jeder Einheit erneut
in dieselbe Zeitüberschreitung rennt.

Alle Pfade sind relativ zur Vault-Wurzel — der Vault-Name kommt nicht vor.
"""

import ipaddress
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlsplit, urlunsplit

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class ObsidianUnavailable(RuntimeError):
    """Obsidian ist gerade nicht erreichbar — Aufrufer soll es später erneut versuchen."""


class ObsidianError(RuntimeError):
    """Obsidian hat geantwortet, aber mit einem Fehler (4xx außer 404)."""


@dataclass
class _CircuitBreaker:
    """Nach wiederholten Fehlern für eine Weile gar nicht erst anfragen."""

    threshold: int = 3
    cooldown_s: float = 120.0
    failures: int = 0
    opened_at: float | None = field(default=None)

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown_s:
            # Cooldown vorbei — einen Versuch zulassen (half-open).
            self.opened_at = None
            self.failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.warning(
                "Obsidian-Circuit geöffnet nach %s Fehlern — pausiere %.0fs",
                self.failures, self.cooldown_s,
            )


_breaker = _CircuitBreaker()


class ObsidianClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        verify: bool | None = None,
        proxy: str | None = None,
    ):
        # Kein Rückfall mehr auf die Umgebungskonfiguration: Sie zeigt auf
        # genau einen Vault — den der Installation. Solange es diesen Rückfall
        # gab, genügte ein `ObsidianClient()` ohne Argumente irgendwo im Code,
        # damit die Notizen aller Athleten dort landeten. Genau das ist an zwei
        # Stellen passiert, ohne dass es jemandem auffiel.
        #
        # Die Anbindung kommt jetzt ausschließlich aus dem Profil des
        # Athleten, über `client_for_profile`. Wer keine hinterlegt hat, hat
        # keine — und der Sync meldet sich als abgeschaltet.
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout if timeout is not None else settings.OBSIDIAN_TIMEOUT_S
        self.verify = verify if verify is not None else settings.OBSIDIAN_VERIFY_TLS
        # Der Weg ins private Netz, falls einer eingerichtet ist. Die Adresse
        # des Athleten liegt dann nicht im öffentlichen Netz, sondern im
        # Tailnet — ohne diesen Proxy läuft die Anfrage ins Leere.
        self.proxy = proxy if proxy is not None else settings.OBSIDIAN_PROXY

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, *, retries: int = 2, **kwargs) -> httpx.Response:
        if not self.enabled:
            raise ObsidianUnavailable("Obsidian ist nicht konfiguriert (BASE_URL/API_KEY fehlen)")
        if _breaker.is_open:
            raise ObsidianUnavailable("Obsidian-Circuit offen — Anfrage übersprungen")

        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        # Auth wird hier zentral gesetzt, nicht in den einzelnen Methoden —
        # sonst vergisst ein Aufrufer den Header und bekommt ein stilles 200
        # mit authenticated: false zurück.
        kwargs["headers"] = self._headers(kwargs.get("headers"))

        for attempt in range(retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    verify=self.verify,
                    # Ohne Proxy verhält sich der Client wie bisher.
                    proxy=self.proxy or None,
                ) as client:
                    response = client.request(method, url, **kwargs)
            except httpx.HTTPError as e:
                last_error = e
                if attempt < retries:
                    time.sleep(0.4 * (2 ** attempt))
                    continue
                _breaker.record_failure()
                raise ObsidianUnavailable(f"{method} {path} fehlgeschlagen: {e}") from e

            # 5xx ist ein Infrastrukturproblem und darf erneut versucht werden,
            # 4xx ist ein Aufruferfehler und wird sofort durchgereicht.
            if response.status_code >= 500 and attempt < retries:
                time.sleep(0.4 * (2 ** attempt))
                continue

            _breaker.record_success()
            return response

        _breaker.record_failure()
        raise ObsidianUnavailable(f"{method} {path} fehlgeschlagen: {last_error}")

    # --- Lesen -------------------------------------------------------------

    def ping(self) -> dict:
        """Status inkl. authenticated-Flag. Der Root-Endpoint antwortet auch
        ohne gültigen Key mit 200 — deshalb wird das Flag ausgewertet."""
        response = self._request("GET", "/", retries=0)
        data = response.json()
        if not data.get("authenticated"):
            raise ObsidianError("Obsidian erreichbar, aber API-Key wird abgelehnt")
        return data

    def get_note(self, path: str) -> str | None:
        """Note-Inhalt, oder None wenn sie nicht existiert."""
        response = self._request(
            "GET", f"/vault/{path}", headers=self._headers({"Accept": "text/markdown"})
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ObsidianError(f"GET {path}: {response.status_code} {response.text[:200]}")
        return response.text

    def list_dir(self, path: str = "") -> list[str]:
        suffix = f"{path.rstrip('/')}/" if path else ""
        response = self._request("GET", f"/vault/{suffix}", headers=self._headers())
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise ObsidianError(f"LIST {path}: {response.status_code}")
        return response.json().get("files", [])

    def search(self, query: str, context_length: int = 200) -> list[dict]:
        response = self._request(
            "POST", "/search/simple/",
            headers=self._headers(),
            params={"query": query, "contextLength": context_length},
        )
        if response.status_code >= 400:
            raise ObsidianError(f"SEARCH: {response.status_code} {response.text[:200]}")
        return response.json()

    # --- Schreiben ---------------------------------------------------------

    def put_note(self, path: str, content: str) -> None:
        """Note anlegen oder vollständig ersetzen.

        Ersetzt kompromisslos — Aufrufer müssen vorher mergen. Der Schutz
        vor überschriebenem Freitext liegt bewusst in notes.merge_note()
        und nicht hier, damit diese Schicht dumm und testbar bleibt.
        """
        response = self._request(
            "PUT", f"/vault/{path}",
            headers=self._headers({"Content-Type": "text/markdown"}),
            content=content.encode("utf-8"),
        )
        if response.status_code >= 400:
            raise ObsidianError(f"PUT {path}: {response.status_code} {response.text[:200]}")

    def append_note(self, path: str, content: str) -> None:
        response = self._request(
            "POST", f"/vault/{path}",
            headers=self._headers({"Content-Type": "text/markdown"}),
            content=content.encode("utf-8"),
        )
        if response.status_code >= 400:
            raise ObsidianError(f"APPEND {path}: {response.status_code} {response.text[:200]}")

    def delete_note(self, path: str) -> bool:
        """Note löschen. True wenn sie weg ist, False wenn sie nie existierte.

        Wird nur für Korrekturen benutzt (falsch klassifizierte Einheit, deren
        Note im falschen Ordner liegt) — nie im regulären Sync-Pfad.
        """
        response = self._request("DELETE", f"/vault/{path}")
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise ObsidianError(f"DELETE {path}: {response.status_code} {response.text[:200]}")
        return True

    def patch_heading(self, path: str, heading: str, content: str, operation: str = "replace") -> None:
        """Nur einen Abschnitt unter einer Überschrift ersetzen.

        Genau das braucht der Wochenplan: den "Diese Woche"-Abschnitt
        aktualisieren, ohne den Rest der Note anzufassen.
        """
        response = self._request(
            "PATCH", f"/vault/{path}",
            headers=self._headers({
                "Content-Type": "text/markdown",
                "Operation": operation,
                "Target-Type": "heading",
                "Target": heading,
            }),
            content=content.encode("utf-8"),
        )
        if response.status_code >= 400:
            raise ObsidianError(f"PATCH {path} [{heading}]: {response.status_code} {response.text[:200]}")


def client_for_profile(profile) -> ObsidianClient:
    """Client mit den Zugangsdaten eines Athleten.

    Bewusst **ohne** Rückfall auf die Umgebungskonfiguration: die zeigt auf
    genau einen Vault, und ein neu angelegter Athlet hätte sonst in fremde
    Notizen geschrieben, ohne je etwas eingerichtet zu haben. Wer keine
    eigenen Zugangsdaten hinterlegt hat, hat schlicht keine Anbindung.
    """
    if profile is None:
        return ObsidianClient(base_url="", api_key="")
    basis = profile.obsidian_base_url or ""
    return ObsidianClient(
        base_url=basis,
        api_key=profile.obsidian_api_key or "",
        verify=pruefung_noetig(basis, getattr(profile, "obsidian_verify_tls", None)),
    )


# Die Standardports des Local-REST-API-Plugins. HTTPS ist der aktive, HTTP
# muss im Plugin erst eingeschaltet werden und lauscht dann nur lokal.
PLUGIN_PORT_HTTPS = 27124
PLUGIN_PORT_HTTP = 27123


def normalisiere_adresse(eingabe: str) -> str:
    """Aus dem, was jemand einfügt, eine vollständige Adresse machen.

    In der Tailscale-App steht eine nackte Adresse — `100.84.12.7` oder
    `rechner.tailnet.ts.net`. Wer sie herauskopiert, fügt genau das ein.
    Verlangt man zusätzlich `https://` davor und `:27124` dahinter, scheitert
    die Einrichtung an zwei Angaben, die für jede Installation gleich sind
    und die niemand raten kann.

    Ergänzt wird nur, was fehlt. Eine vollständig eingegebene Adresse bleibt
    unangetastet, auch mit abweichendem Port oder Pfad.
    """
    text = (eingabe or "").strip().strip("/")
    if not text:
        return ""

    # Ein IPv6-Literal muss in Klammern, sonst liest jeder URL-Parser die
    # letzte Zifferngruppe als Portnummer. Die Tailscale-App zeigt die
    # Adresse ohne Klammern an, also kommen sie von hier.
    try:
        if isinstance(ipaddress.ip_address(text), ipaddress.IPv6Address):
            text = f"[{text}]"
    except ValueError:
        pass

    if "://" not in text:
        text = f"https://{text}"

    teile = urlsplit(text)
    if teile.port is None:
        vorgabe = PLUGIN_PORT_HTTP if teile.scheme == "http" else PLUGIN_PORT_HTTPS
        teile = teile._replace(netloc=f"{teile.netloc}:{vorgabe}")

    return urlunsplit(teile).rstrip("/")


def pruefung_noetig(base_url: str, vorgabe: bool | None) -> bool:
    """Soll das Zertifikat der Gegenstelle geprüft werden?

    Die Entscheidung hängt an der Adresse, nicht am Athleten. Entscheidend
    ist, wer am anderen Ende das Zertifikat ausgestellt hat:

    * `rechner.tailnet.ts.net` — `tailscale serve` steht davor und hält ein
      echtes Zertifikat. Hier wird geprüft.
    * `100.72.215.32`, `localhost`, `macbook.local` — das ist das
      Obsidian-Plugin selbst, und dessen Zertifikat ist selbstsigniert. Eine
      Prüfung schlägt dort immer fehl; der Athlet stünde vor einem Fehler,
      den er nicht beheben kann, obwohl seine Adresse richtig ist.

    Der Verzicht ist vertretbar, weil die Verbindung ohnehin im Tailnet
    liegt: Der WireGuard-Tunnel ist beidseitig authentifiziert und
    verschlüsselt, das TLS darüber ist die zweite Lage. Sie wegzulassen
    öffnet den Weg nicht — es verzichtet auf eine doppelte Absicherung
    innerhalb eines bereits geschlossenen Netzes.

    `vorgabe` ist die Festlegung des Athleten und schlägt alles: True/False
    gelten, None heißt „entscheide selbst".
    """
    if vorgabe is not None:
        return vorgabe

    host = (urlparse(base_url).hostname or "").strip().lower()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return False        # nackte IP → Plugin direkt → selbstsigniert
    except ValueError:
        pass
    # Ein Name ohne öffentliche Endung (`localhost`) oder mit `.local` kommt
    # nicht aus einer Zertifizierungsstelle. Das ist zugleich der lokale
    # Entwicklungsfall: bis hierher galt `OBSIDIAN_VERIFY_TLS = False` für
    # alle, und `https://localhost:27124` funktionierte. Das darf eine
    # Automatik nicht nebenbei kaputt machen.
    if "." not in host or host.endswith(".local"):
        return False
    return True


DEFAULT_VAULT_SUBDIR = "Training"


def vault_subdir_for(profile) -> str:
    if profile is not None and profile.obsidian_vault_subdir:
        return profile.obsidian_vault_subdir
    return DEFAULT_VAULT_SUBDIR


# Bewusst keine Abkürzung wie `get_client()`: Eine parameterlose Funktion
# lädt dazu ein, sie irgendwo aufzurufen, wo der Athlet bekannt wäre. Wer
# einen Client braucht, geht über `client_for_profile(profile)`.
