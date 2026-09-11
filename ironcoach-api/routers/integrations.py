"""Externe Anbindungen einrichten: Strava und Obsidian.

Beide gehören zum Athleten, nicht zur Installation. Obsidian läuft auf dem
Rechner des Athleten — es gibt keinen zentralen Vault, den die App bedienen
könnte, deshalb hinterlegt jeder seine eigene Adresse und seinen eigenen
Schlüssel.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.deps import get_profile, require_user
from database import get_db
from models import StravaCredentials, User
from services.obsidian.client import DEFAULT_VAULT_SUBDIR

logger = logging.getLogger(__name__)
router = APIRouter()


class ObsidianSettings(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    vault_subdir: str | None = None


def _mask(secret: str | None) -> str | None:
    """Schlüssel nie vollständig zurückgeben — auch nicht an den Besitzer.

    Wer ihn eingetragen hat, hat ihn; wer die Antwort abfängt, soll ihn nicht
    bekommen.
    """
    if not secret:
        return None
    return f"…{secret[-4:]}" if len(secret) > 4 else "…"


@router.get("/integrations")
def integrations(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Zustand beider Anbindungen — ohne Netzwerkzugriff."""
    profile = get_profile(db, user)
    creds = db.query(StravaCredentials).first()

    # Nur das Profil zählt — dieselbe Regel wie im Client. Die Umgebung als
    # Rückfall zu melden wäre irreführend: der Athlet würde "eingerichtet"
    # lesen, obwohl seine Notizen nirgendwo landen.
    base_url = (profile.obsidian_base_url if profile else None) or None
    api_key = (profile.obsidian_api_key if profile else None) or None

    return {
        "strava": {
            "connected": creds is not None,
            "athlete_id": creds.athlete_id if creds else None,
            "connected_at": creds.connected_at.isoformat() if creds and creds.connected_at else None,
        },
        "obsidian": {
            "configured": bool(base_url and api_key),
            "base_url": base_url,
            "api_key_hint": _mask(api_key),
            "vault_subdir": (
                (profile.obsidian_vault_subdir if profile else None)
                or DEFAULT_VAULT_SUBDIR
            ),
        },
    }


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
        url = body.base_url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="Adresse muss mit http:// oder https:// beginnen")
        profile.obsidian_base_url = url or None
    if body.api_key is not None:
        # Leerer String löscht den Schlüssel, statt ihn auf "" zu setzen.
        profile.obsidian_api_key = body.api_key.strip() or None
    if body.vault_subdir is not None:
        profile.obsidian_vault_subdir = body.vault_subdir.strip().strip("/") or None

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
        client = ObsidianClient(
            base_url=body.base_url or (profile.obsidian_base_url if profile else None),
            api_key=body.api_key or (profile.obsidian_api_key if profile else None),
        )
    else:
        client = client_for_profile(profile)

    if not client.enabled:
        return {"ok": False, "error": "Adresse oder Schlüssel fehlen"}

    try:
        info = client.ping()
        return {
            "ok": True,
            "authenticated": bool(info.get("authenticated")),
            "plugin_version": info.get("versions", {}).get("self"),
            "vault_root": client.list_dir()[:12],
        }
    except ObsidianError as e:
        # Erreichbar, aber abgelehnt — meist ein falscher Schlüssel.
        return {"ok": False, "reachable": True, "error": str(e)}
    except ObsidianUnavailable as e:
        return {"ok": False, "reachable": False, "error": str(e)}


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
    suggested = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")

    return {
        **status,
        "can_manage": bool(getattr(user, "is_admin", False)),
        "public_base_url": settings.PUBLIC_BASE_URL or None,
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

    base = (body.public_base_url or settings.PUBLIC_BASE_URL or str(request.base_url)).strip()
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Adresse muss mit http:// oder https:// beginnen")
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
def disconnect_strava(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Strava trennen. Bereits eingelesene Einheiten bleiben erhalten."""
    creds = db.query(StravaCredentials).all()
    for entry in creds:
        db.delete(entry)
    db.commit()
    return {"disconnected": len(creds)}
