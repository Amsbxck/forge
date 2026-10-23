"""intervals.icu per OAuth verbinden, gebaut wie die Strava-Freigabe.

Für alle Athleten, die keinen Schlüssel kopieren sollen: Knopf drücken, bei
intervals.icu bestätigen, fertig. Das setzt voraus, dass intervals.icu die
FORGE-App freigeschaltet hat (`INTERVALS_CLIENT_ID`/`_SECRET`). Bis dahin
antwortet `/api/intervals/auth` mit 409, und die Kachel bietet nur den
Schlüsselweg.

Ablauf wie bei Strava (`routers/strava_webhook.py`, dort steht das Warum):

1. `GET /api/intervals/auth`: Adresse mit `state` als 10-Minuten-Zwecktoken.
2. intervals.icu leitet ohne Anmeldung zurück an `/api/intervals/callback`.
   Der Code wird **sofort** getauscht (intervals.icu lässt dafür nur zwei
   Minuten), verbunden wird aber noch nicht: Der Vorgang wartet.
3. `POST /api/intervals/bestaetigen` aus dem angemeldeten Browser. Erst
   jetzt kommt der Token ans Profil. Ein fremder Freigabelink hängt so kein
   fremdes Konto an.
"""

import logging
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.deps import get_profile, require_user
from database import get_db

logger = logging.getLogger(__name__)

# Ohne Anmeldung (Rückleitung) und mit Anmeldung (alles andere), wie Strava.
router = APIRouter()
api_router = APIRouter()

OAUTH_ZWECK = "intervals_oauth"
AUSSTEHEND_MINUTEN = 10
_ausstehend: dict[str, dict] = {}


def _aufraeumen() -> None:
    grenze = datetime.utcnow() - timedelta(minutes=AUSSTEHEND_MINUTEN)
    for schluessel in [k for k, v in _ausstehend.items() if v["am"] < grenze]:
        _ausstehend.pop(schluessel, None)


def _rueckleitung(request: Request) -> str:
    from core.urls import api_url

    return f"{api_url(str(request.base_url))}/api/intervals/callback"


@api_router.get("/api/intervals/auth")
def intervals_auth(request: Request, user=Depends(require_user)):
    from core.security import create_purpose_token
    from services.intervals_icu import oauth_adresse, oauth_bereit

    if not oauth_bereit():
        raise HTTPException(
            status_code=409,
            detail="Die Anmeldung über intervals.icu ist noch nicht freigeschaltet. "
                   "Bitte den API-Schlüssel nehmen.",
        )
    state = create_purpose_token(user.id, OAUTH_ZWECK)
    return {"auth_url": oauth_adresse(_rueckleitung(request), state)}


@router.get("/api/intervals/callback")
async def intervals_callback(code: str | None = None, state: str | None = None,
                             error: str | None = None, db: Session = Depends(get_db)):
    from core.security import purpose_token_payload, token_issued_after
    from core.urls import app_pfad
    from models import User
    from services.intervals_icu import IntervalsFehler, code_tauschen

    def fehler(grund: str):
        return RedirectResponse(app_pfad("/connect", intervals="fehler", grund=grund), status_code=303)

    if error or not code:
        return fehler("Die Freigabe bei intervals.icu wurde nicht erteilt.")

    payload = purpose_token_payload(state, OAUTH_ZWECK)
    user = None
    if payload:
        try:
            user = db.get(User, int(payload["sub"]))
        except (KeyError, TypeError, ValueError):
            user = None
    if user is None or not user.is_active or not token_issued_after(payload, user.tokens_valid_from):
        return fehler("Die Freigabe ist abgelaufen oder gehört zu keiner gültigen Anmeldung. "
                      "Bitte starte die Verbindung erneut.")

    try:
        daten = await code_tauschen(code)
    except IntervalsFehler:
        # Fester Text: Die Antwort von intervals.icu könnte den Code spiegeln.
        logger.warning("intervals.icu-OAuth für Nutzer %s fehlgeschlagen", user.id)
        return fehler("intervals.icu hat die Freigabe nicht bestätigt. Bitte erneut versuchen.")

    _aufraeumen()
    vorgang = secrets.token_urlsafe(24)
    _ausstehend[vorgang] = {"user_id": user.id, "daten": daten, "am": datetime.utcnow()}
    return RedirectResponse(app_pfad("/connect", intervals="bestaetigen", vorgang=vorgang),
                            status_code=303)


@api_router.post("/api/intervals/bestaetigen")
def intervals_bestaetigen(body: dict, db: Session = Depends(get_db), user=Depends(require_user)):
    from services.intervals_sync import anstossen

    _aufraeumen()
    schluessel = str(body.get("vorgang") or "")
    eintrag = _ausstehend.get(schluessel)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Dieser Verbindungsvorgang ist abgelaufen. Bitte neu starten.")
    if eintrag["user_id"] != user.id:
        raise HTTPException(
            status_code=403,
            detail="Diese Freigabe wurde für ein anderes Konto gestartet und wird hier nicht übernommen.",
        )
    _ausstehend.pop(schluessel, None)

    profile = get_profile(db, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="Kein Athletenprofil")
    profile.intervals_athlete_id = eintrag["daten"]["athlete_id"]
    profile.intervals_token = eintrag["daten"]["token"]
    # Ein Zugang zur Zeit, siehe `connect_intervals`.
    profile.intervals_api_key = None
    profile.intervals_verbunden_am = datetime.utcnow()
    profile.intervals_letzter_fehler = None
    db.commit()

    heute = date.today()
    anstossen(db, user.id, [heute, heute + timedelta(days=7)])
    return {"status": "ok", "athlete_id": profile.intervals_athlete_id}
