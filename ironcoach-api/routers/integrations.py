"""Externe Anbindungen einrichten: Strava, Garmin Connect, intervals.icu und Obsidian.

Alle gehören zum Athleten, nicht zur Installation. Obsidian läuft auf dem
Rechner des Athleten — es gibt keinen zentralen Vault, den die App bedienen
könnte, deshalb hinterlegt jeder seine eigene Adresse und seinen eigenen
Schlüssel. Bei Garmin ebenso: Die Personal API kennt nur persönliche
Schlüssel, keinen Anwendungszugang wie Strava.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.deps import get_profile, require_user
from database import get_db
from models import StravaCredentials, User
from services.obsidian.client import (
    DEFAULT_VAULT_SUBDIR, normalisiere_adresse, pruefung_noetig,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ObsidianSettings(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    vault_subdir: str | None = None
    # Leer heißt „entscheide selbst" — siehe `pruefung_noetig` im Client.
    # Als Feld vorhanden, damit sich die Automatik übergehen lässt, aber
    # niemand sie setzen muss.
    verify_tls: bool | None = None


def _mask(secret: str | None) -> str | None:
    """Schlüssel nie vollständig zurückgeben — auch nicht an den Besitzer.

    Wer ihn eingetragen hat, hat ihn; wer die Antwort abfängt, soll ihn nicht
    bekommen.
    """
    if not secret:
        return None
    return f"…{secret[-4:]}" if len(secret) > 4 else "…"


def _zeitpunkt(wert: datetime | None) -> str | None:
    """Als UTC mit Versatz ausgeben.

    Gespeichert wird wie überall im Modell mit `datetime.utcnow()`, also ohne
    Zeitzone. Ohne Versatz liest der Browser die Zeichenkette als Ortszeit,
    und „Letzter Abruf" stünde ein bis zwei Stunden daneben.
    """
    if wert is None:
        return None
    return wert.replace(tzinfo=timezone.utc).isoformat()


def _garmin_zustand(profile) -> dict:
    from services.garmin_hrv import fehler_art

    api_key = (profile.garmin_api_key if profile else None) or None
    return {
        "configured": bool(api_key),
        "api_key_hint": _mask(api_key),
        "verbunden_am": _zeitpunkt(profile.garmin_verbunden_am if profile else None),
        "letzter_abruf": _zeitpunkt(profile.garmin_letzter_abruf if profile else None),
        "letzter_fehler": profile.garmin_letzter_fehler if profile else None,
        # "schluessel" | "vorruebergehend" | None. Die Kachel zeigt das Feld
        # für einen neuen Schlüssel nur, wenn der Schlüssel das Problem ist;
        # bei einem 429 oder einem Ausfall bei Garmin hilft ein neuer nicht.
        "fehler_art": fehler_art(profile.garmin_letzter_fehler if profile else None),
        # Die Kachel braucht das, damit sie nicht „jeden Morgen automatisch"
        # verspricht, wenn der Job auf dem Server gar nicht läuft.
        "sync_aktiv": settings.GARMIN_SYNC_ENABLED,
    }


def _intervals_zustand(profile) -> dict:
    from services.intervals_icu import oauth_bereit

    hat_token = bool(profile and profile.intervals_token)
    hat_schluessel = bool(profile and profile.intervals_api_key)
    return {
        "configured": bool(profile and profile.intervals_athlete_id and (hat_token or hat_schluessel)),
        "athlete_id": profile.intervals_athlete_id if profile else None,
        # "oauth" | "schluessel" | None
        "weg": "oauth" if hat_token else ("schluessel" if hat_schluessel else None),
        "api_key_hint": _mask(profile.intervals_api_key if profile else None),
        "verbunden_am": _zeitpunkt(profile.intervals_verbunden_am if profile else None),
        "letzter_abgleich": _zeitpunkt(profile.intervals_letzter_abgleich if profile else None),
        "letzter_fehler": profile.intervals_letzter_fehler if profile else None,
        # Ohne freigeschaltete App gibt es nur den Schlüsselweg.
        "oauth_bereit": oauth_bereit(),
    }


@router.get("/integrations")
def integrations(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Zustand aller Anbindungen — ohne Netzwerkzugriff."""
    profile = get_profile(db, user)
    creds = db.query(StravaCredentials).first()

    # Nur das Profil zählt — dieselbe Regel wie im Client. Die Umgebung als
    # Rückfall zu melden wäre irreführend: der Athlet würde "eingerichtet"
    # lesen, obwohl seine Notizen nirgendwo landen.
    base_url = (profile.obsidian_base_url if profile else None) or None
    api_key = (profile.obsidian_api_key if profile else None) or None
    verify_gesetzt = profile.obsidian_verify_tls if profile else None

    return {
        "strava": {
            "connected": creds is not None,
            "athlete_id": creds.athlete_id if creds else None,
            "connected_at": creds.connected_at.isoformat() if creds and creds.connected_at else None,
        },
        "garmin": _garmin_zustand(profile),
        "intervals": _intervals_zustand(profile),
        "obsidian": {
            "configured": bool(base_url and api_key),
            "base_url": base_url,
            "api_key_hint": _mask(api_key),
            "vault_subdir": (
                (profile.obsidian_vault_subdir if profile else None)
                or DEFAULT_VAULT_SUBDIR
            ),
            # Was gespeichert ist (meist nichts) und was daraus folgt. Die
            # Oberfläche zeigt nur das Ergebnis — wer eine IP einträgt, soll
            # nicht erst lernen müssen, was ein Zertifikat ist.
            "verify_tls": verify_gesetzt,
            "verify_tls_effective": pruefung_noetig(base_url or "", verify_gesetzt),
        },
    }


class GarminSettings(BaseModel):
    api_key: str


@router.put("/integrations/garmin")
async def connect_garmin(
    body: GarminSettings,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Garmin verbinden: Schlüssel prüfen, speichern, 30 Tage nachholen.

    **Zuerst** der Tausch gegen ein Token, erst danach wird gespeichert. Ein
    falscher Schlüssel landet so gar nicht erst in der Datenbank, und der
    Athlet sieht den Fehler sofort statt am nächsten Morgen.

    Danach sofort 30 Tage samt Spanne: So sieht der Athlet direkt Werte und
    muss nicht bis morgen bzw. Sonntag warten. Der eben getauschte Token wird
    dafür weiterverwendet, es bleibt bei einem Tausch.
    """
    from services import garmin_personal
    from services.garmin_hrv import abgleich_fuer
    from services.garmin_personal import (
        GarminRateLimit, GarminSchluesselUngueltig, GarminFehler,
    )

    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")
    # Leerraum und Nullbreiten-Zeichen am Rand sind Kopierreste und werden
    # still entfernt (`str.strip()` allein lässt U+200B stehen).
    schluessel = garmin_personal.schluessel_bereinigen(body.api_key)
    if not schluessel:
        raise HTTPException(status_code=422, detail="Bitte den API-Schlüssel aus Garmin Connect einfügen")
    if not garmin_personal.zeichen_gueltig(schluessel):
        # Vor dem Tausch prüfen: Ein „ü" oder ein Nullbreiten-Zeichen mitten
        # im Schlüssel ließ httpx mit einem UnicodeEncodeError abbrechen — ein
        # 500, dessen Ausnahmetext den vollen Schlüssel enthielt. Garmins
        # Schlüssel bestehen nur aus druckbarem ASCII.
        raise HTTPException(
            status_code=422,
            detail="Der Schlüssel enthält Zeichen, die in einem Garmin-Schlüssel nicht vorkommen. "
                   "Bitte direkt aus Garmin Connect kopieren.",
        )

    # Fehlertexte fest formuliert: Weder der Schlüssel noch Garmins Antwort
    # gehören in eine Meldung, die im Browser und in Protokollen landet.
    try:
        token = await garmin_personal.token_holen(schluessel)
    except GarminSchluesselUngueltig:
        raise HTTPException(
            status_code=422,
            detail="Garmin hat den Schlüssel abgelehnt. Ist er vollständig kopiert und noch gültig?",
        )
    except GarminRateLimit:
        raise HTTPException(
            status_code=503,
            detail="Garmin bremst gerade die Anfragen. Bitte in ein paar Minuten erneut versuchen.",
        )
    except GarminFehler:
        raise HTTPException(
            status_code=502,
            detail="Garmin Connect ist gerade nicht erreichbar. Bitte später erneut versuchen.",
        )

    profile.garmin_api_key = schluessel
    profile.garmin_verbunden_am = datetime.utcnow()
    profile.garmin_letzter_fehler = None
    db.commit()

    ergebnis = await abgleich_fuer(db, user, tage=30, mit_spanne=True, token=token)
    return {**integrations(db, user), "ergebnis": ergebnis}


@router.post("/integrations/garmin/abrufen")
async def garmin_abrufen(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Knopf „Jetzt abrufen": 7 Tage, ohne Spanne (die kommt sonntags).

    Funktioniert auch, wenn der Morgen-Job auf dem Server nicht läuft.
    """
    from services.garmin_hrv import abgleich_fuer

    profile = get_profile(db, user)
    if profile is None or not profile.garmin_api_key:
        raise HTTPException(status_code=409, detail="Garmin ist nicht verbunden")
    ergebnis = await abgleich_fuer(db, user, tage=7, mit_spanne=False)
    return {**integrations(db, user), "ergebnis": ergebnis}


@router.delete("/integrations/garmin")
def disconnect_garmin(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Garmin trennen. Schlüssel und Statusfelder leeren, Messungen bleiben.

    `hrv_range_source` bleibt bewusst auf "garmin" mit den letzten Werten,
    bis wieder verbunden wird: Eine Trennung soll die Ampel nicht still auf
    die berechnete Spanne umstellen. Ein Athlet, der nur den Schlüssel
    tauscht, sähe sonst für einen Moment andere Farben und einen anderen
    Plan-Kontext, ohne dass sich an seiner HRV etwas geändert hat.
    """
    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")
    profile.garmin_api_key = None
    profile.garmin_verbunden_am = None
    profile.garmin_letzter_abruf = None
    profile.garmin_letzter_fehler = None
    db.commit()
    return integrations(db, user)


class IntervalsSettings(BaseModel):
    athlete_id: str
    api_key: str


def _intervals_ausloesen(db: Session, user_id: int) -> dict:
    """Laufende und kommende Woche abgleichen, im Hintergrund."""
    from datetime import date, timedelta

    from services.intervals_sync import anstossen

    heute = date.today()
    faden = anstossen(db, user_id, [heute, heute + timedelta(days=7)])
    return {"abgleich": faden is not None}


@router.put("/integrations/intervals")
async def connect_intervals(
    body: IntervalsSettings,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """intervals.icu mit dem persönlichen Schlüssel verbinden.

    Wie bei Garmin **zuerst** prüfen, dann speichern: Ein falscher Schlüssel
    oder eine fremde Athleten-ID landet so gar nicht erst in der Datenbank.
    Danach gehen die Läufe der laufenden und der kommenden Woche raus.
    """
    from services import intervals_icu
    from services.garmin_personal import schluessel_bereinigen, zeichen_gueltig
    from services.intervals_icu import IntervalsFehler, IntervalsZugangUngueltig, Zugang

    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")
    athlete_id = schluessel_bereinigen(body.athlete_id)
    if not intervals_icu.athleten_id_gueltig(athlete_id):
        raise HTTPException(
            status_code=422,
            detail="Die Athleten-ID sieht aus wie i12345. Sie steht in intervals.icu unter Settings.",
        )
    schluessel = schluessel_bereinigen(body.api_key)
    if not schluessel or not zeichen_gueltig(schluessel):
        raise HTTPException(
            status_code=422,
            detail="Bitte den API-Schlüssel aus intervals.icu (Settings → Developer Settings) einfügen.",
        )

    try:
        await intervals_icu.athlet_pruefen(Zugang(athlete_id, api_key=schluessel))
    except IntervalsZugangUngueltig:
        raise HTTPException(
            status_code=422,
            detail="intervals.icu hat den Schlüssel abgelehnt. Passen Schlüssel und Athleten-ID zusammen?",
        )
    except IntervalsFehler:
        raise HTTPException(
            status_code=502,
            detail="intervals.icu ist gerade nicht erreichbar. Bitte später erneut versuchen.",
        )

    profile.intervals_athlete_id = athlete_id
    profile.intervals_api_key = schluessel
    # Ein Schlüssel ersetzt eine frühere OAuth-Verbindung: Zwei Zugänge
    # nebeneinander ließen offen, welcher gerade schreibt.
    profile.intervals_token = None
    profile.intervals_verbunden_am = datetime.utcnow()
    profile.intervals_letzter_fehler = None
    db.commit()
    return {**integrations(db, user), **_intervals_ausloesen(db, user.id)}


@router.post("/integrations/intervals/abgleichen")
def intervals_abgleichen(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Knopf „Sync now": laufende und kommende Woche sofort abgleichen.

    Hier im Vordergrund statt im Faden: Der Athlet wartet auf das Ergebnis.
    Bewusst synchron (`def`): Der Abgleich nimmt die Sperre des Athleten, und
    die darf keinen Event-Loop anhalten. FastAPI führt die Route im
    Threadpool aus.
    """
    from datetime import date, timedelta

    from core.wochen import montag_von
    from services.intervals_sync import abgleichen

    profile = get_profile(db, user)
    if profile is None or not _intervals_zustand(profile)["configured"]:
        raise HTTPException(status_code=409, detail="intervals.icu ist nicht verbunden")
    heute = date.today()
    ergebnisse = abgleichen(db, user.id, [montag_von(heute), montag_von(heute + timedelta(days=7))])
    summe = {k: sum(e.get(k, 0) for e in ergebnisse) for k in ("angelegt", "ersetzt", "geloescht", "unveraendert")}
    fehler = next((e["fehler"] for e in ergebnisse if e.get("fehler")), None)
    return {**integrations(db, user), "ergebnis": {**summe, "fehler": fehler}}


@router.delete("/integrations/intervals")
def disconnect_intervals(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """intervals.icu trennen.

    Vorher die FORGE-Workouts ab heute dort löschen: Sonst stünden sie weiter
    in Garmins Kalender und auf der Uhr, und keiner räumte sie mehr ab, wenn
    sich der Plan ändert. Schlägt das fehl, wird trotzdem getrennt. Der
    Athlet will die Verbindung los sein, die Workouts löscht er dann selbst.
    """
    from services.intervals_sync import alles_entfernen

    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")

    aufgeraeumt = alles_entfernen(db, user.id)

    profile.intervals_athlete_id = None
    profile.intervals_api_key = None
    profile.intervals_token = None
    profile.intervals_verbunden_am = None
    profile.intervals_letzter_abgleich = None
    profile.intervals_letzter_fehler = None
    db.commit()
    return {**integrations(db, user), "aufgeraeumt": aufgeraeumt}


@router.patch("/integrations/obsidian")
def update_obsidian(
    body: ObsidianSettings,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")

    if body.base_url is not None:
        # Schema und Port ergänzen, statt sie zu verlangen: In der
        # Tailscale-App steht eine nackte Adresse, und genau die fügt jemand
        # hier ein.
        url = normalisiere_adresse(body.base_url)
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="Adresse ist unlesbar")
        from services.obsidian.client import adresse_gesperrt
        grund = adresse_gesperrt(url) if url else None
        if grund:
            raise HTTPException(status_code=422, detail=grund)
        # Eine neue Adresse hebt eine frühere Festlegung auf: Die Entscheidung
        # über das Zertifikat gehörte zur alten Adresse. Ohne das bliebe ein
        # einmal gesetztes Flag für immer kleben — und es gibt keinen Weg
        # zurück auf „automatisch", weil ein fehlendes Feld hier „unverändert"
        # heißt.
        if url != (profile.obsidian_base_url or ""):
            profile.obsidian_verify_tls = None
        profile.obsidian_base_url = url or None
    if body.api_key is not None:
        # Leerer String löscht den Schlüssel, statt ihn auf "" zu setzen.
        profile.obsidian_api_key = body.api_key.strip() or None
    if body.vault_subdir is not None:
        profile.obsidian_vault_subdir = body.vault_subdir.strip().strip("/") or None
    if body.verify_tls is not None:
        profile.obsidian_verify_tls = body.verify_tls

    db.commit()
    return integrations(db, user)


@router.post("/integrations/obsidian/test")
def test_obsidian(
    body: ObsidianSettings | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Verbindung prüfen — mit den übergebenen oder den gespeicherten Daten.

    Erlaubt es, vor dem Speichern zu testen; sonst trägt jemand einen
    falschen Schlüssel ein und sucht den Fehler später woanders.
    """
    from services.obsidian.client import ObsidianClient, ObsidianError, ObsidianUnavailable, client_for_profile

    profile = get_profile(db, user)
    if body and (body.base_url or body.api_key):
        # Auch hier normalisieren: Der Test läuft vor dem Speichern, mit dem,
        # was im Feld steht. Ohne das scheiterte er an einer Adresse, die
        # gespeichert funktioniert hätte.
        basis = normalisiere_adresse(
            body.base_url or (profile.obsidian_base_url if profile else None) or ""
        )
        client = ObsidianClient(
            base_url=basis,
            api_key=body.api_key or (profile.obsidian_api_key if profile else None),
            # Dieselbe Entscheidung wie beim späteren Abgleich. Ohne sie
            # scheiterte der Test an einem selbstsignierten Zertifikat,
            # während der gespeicherte Zugang funktioniert — der Athlet
            # würde eine richtige Adresse wieder herausnehmen.
            verify=pruefung_noetig(
                basis,
                body.verify_tls if body.verify_tls is not None
                else (profile.obsidian_verify_tls if profile else None),
            ),
        )
    else:
        client = client_for_profile(profile)
    basis = client.base_url

    if not client.enabled:
        return {"ok": False, "error": "Adresse oder Schlüssel fehlen"}
    from services.obsidian.client import adresse_gesperrt
    grund = adresse_gesperrt(basis)
    if grund:
        return {"ok": False, "reachable": False, "error": grund, "base_url": basis}

    try:
        info = client.ping()
        return {
            "ok": True,
            # Die vervollständigte Adresse zurückgeben, damit die Oberfläche
            # sie sofort ins Feld schreiben kann. Sonst ergänzt das Backend
            # `https://` und den Port zwar korrekt, der Athlet sieht davon
            # aber erst nach dem Speichern etwas — und hält die Automatik
            # für kaputt, während sie längst funktioniert hat.
            "base_url": basis,
            "authenticated": bool(info.get("authenticated")),
            "plugin_version": info.get("versions", {}).get("self"),
            "vault_root": client.list_dir()[:12],
        }
    except ObsidianError as e:
        # Erreichbar, aber abgelehnt — meist ein falscher Schlüssel.
        return {"ok": False, "reachable": True, "error": str(e), "base_url": basis}
    except ObsidianUnavailable as e:
        return {"ok": False, "reachable": False, "error": str(e), "base_url": basis}


class WebhookSettings(BaseModel):
    public_base_url: str | None = None


def _callback_url(base: str) -> str:
    return f"{base.rstrip('/')}/webhook"


def _require_admin(user: User) -> None:
    """Der Webhook gilt für die ganze Anwendung.

    Ohne diese Schranke könnte jeder Athlet die Registrierung für alle
    anderen ändern — Strava lässt nur eine Subscription zu.
    """
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Der Webhook gilt für die gesamte Installation und wird vom Betreiber verwaltet",
        )


@router.get("/integrations/strava/webhook")
async def webhook_status(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Zustand des Webhooks samt der Adresse, die Strava erreichen muss.

    Der Webhook gilt für die gesamte Installation, nicht je Athlet: Strava
    erlaubt genau eine Subscription pro Anwendung. Die Zuordnung zum Konto
    passiert später über die Athleten-ID im Event.
    """
    from services.reconcile import check_subscription

    status = await check_subscription(db)
    # Die öffentliche Adresse kennt nur die Installation — aus der Anfrage
    # abgeleitet käme beim Deployment hinter einem Proxy Unsinn heraus.
    from core.urls import api_url

    suggested = api_url(str(request.base_url))

    return {
        **status,
        "can_manage": bool(getattr(user, "is_admin", False)),
        "public_base_url": settings.API_BASE_URL or settings.PUBLIC_BASE_URL or None,
        "suggested_callback_url": _callback_url(suggested),
        "verify_token_set": bool(settings.STRAVA_VERIFY_TOKEN),
        "note": (
            "Eine Subscription je Strava-Anwendung — sie bedient alle Athleten "
            "dieser Installation."
        ),
    }


@router.post("/integrations/strava/webhook")
async def register_webhook(
    body: WebhookSettings,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Webhook registrieren. Ersetzt eine bestehende Subscription."""
    from services.reconcile import check_subscription
    from services.strava_service import StravaService

    _require_admin(user)
    if not settings.STRAVA_VERIFY_TOKEN:
        raise HTTPException(status_code=400, detail="STRAVA_VERIFY_TOKEN ist nicht gesetzt")

    from core.urls import api_url, app_url

    base = (body.public_base_url or api_url(str(request.base_url)) or "").strip()
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Adresse muss mit http:// oder https:// beginnen")
    # Nicht aufs Frontend registrieren: Dort antwortet die Seite mit
    # `index.html`, Strava lehnt ab — und die laufende Subscription wäre
    # vorher schon gelöscht. Gilt nur, wenn Frontend und API getrennt
    # eingetragen sind; liegen beide unter einer Adresse, ist das richtig.
    if settings.FRONTEND_URL and base.rstrip("/") == app_url() and base.rstrip("/") != (settings.API_BASE_URL or "").rstrip("/"):
        raise HTTPException(
            status_code=422,
            detail=f"{base} ist die Adresse des Frontends. Der Webhook braucht die "
                   f"API-Adresse — API_BASE_URL setzen oder hier angeben.",
        )
    callback = _callback_url(base)

    service = StravaService(db)

    # Strava lässt nur eine Subscription zu — eine bestehende muss weg, bevor
    # eine neue angelegt werden kann. Ein atomarer Tausch ist damit unmöglich,
    # deshalb wird die alte Adresse gemerkt und bei einem Fehlschlag wieder
    # eingetragen. Sonst kostet ein Tippfehler die funktionierende Anbindung.
    existing = await check_subscription(db)
    previous = [s.get("callback_url") for s in existing.get("subscriptions", []) if s.get("callback_url")]
    for entry in existing.get("subscriptions", []):
        try:
            await service.delete_push_subscription(entry["id"])
        except Exception as e:
            logger.warning("Alte Subscription %s nicht entfernt: %s", entry.get("id"), e)

    try:
        created = await service.create_push_subscription(callback, settings.STRAVA_VERIFY_TOKEN)
    except ValueError as e:
        restored = None
        for old in previous:
            if old == callback:
                continue
            try:
                await service.create_push_subscription(old, settings.STRAVA_VERIFY_TOKEN)
                restored = old
                break
            except Exception:
                logger.warning("Vorherige Subscription %s ließ sich nicht wiederherstellen", old)

        detail = (
            f"Strava konnte {callback} nicht erreichen oder hat abgelehnt. "
            f"Ist die Adresse von außen erreichbar? Antwort: {e}"
        )
        detail += (
            f" Die vorherige Registrierung auf {restored} wurde wiederhergestellt."
            if restored else
            " Es ist jetzt keine Subscription registriert."
        )
        raise HTTPException(status_code=400, detail=detail)

    return {"created": created, "callback_url": callback}


@router.delete("/integrations/strava/webhook")
async def remove_webhook(db: Session = Depends(get_db), user: User = Depends(require_user)):
    _require_admin(user)
    from services.reconcile import check_subscription
    from services.strava_service import StravaService

    service = StravaService(db)
    existing = await check_subscription(db)
    removed = 0
    for entry in existing.get("subscriptions", []):
        await service.delete_push_subscription(entry["id"])
        removed += 1
    return {"removed": removed}


@router.delete("/integrations/strava")
async def disconnect_strava(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Strava trennen. Bereits eingelesene Einheiten bleiben erhalten.

    Auch bei Strava selbst: Vorher wurden nur die Zugangsdaten hier gelöscht,
    und bei Strava blieb die App als autorisiert stehen.
    """
    from services.strava_service import StravaService

    creds = db.query(StravaCredentials).filter(StravaCredentials.user_id == user.id).all()
    service = StravaService(db)
    widerrufen = 0
    for entry in creds:
        if await service.deauthorize(entry.athlete_id):
            widerrufen += 1
    for entry in creds:
        db.delete(entry)
    db.commit()
    return {"disconnected": len(creds), "bei_strava_widerrufen": widerrufen}
