import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import AthleteProfile, TrainingSession
from schemas import StravaAuthUrl, StravaConnected
from services.strava_service import StravaService
from services.plan_generator import get_week_for_date
from core.config import settings
from core.deps import require_user

logger = logging.getLogger(__name__)

# Zwei Router mit Absicht: der Webhook muss ohne Anmeldung erreichbar sein,
# weil Strava ihn aufruft. Alles andere unter /api/strava/ gehört hinter die
# Anmeldung — sonst könnte jeder einen Abgleich auslösen oder den Zustand
# der Verbindung auslesen.
router = APIRouter()          # offen: nur /webhook
api_router = APIRouter()      # geschützt: /api/strava/*


@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == settings.STRAVA_VERIFY_TOKEN:
        return {"hub.challenge": params.get("hub.challenge")}
    raise HTTPException(status_code=403, detail="Invalid verify token")


# Die ID der eigenen Subscription, sobald bekannt (aus dem stündlichen
# Prüfjob, `remember_subscription`). Strava signiert seine Ereignisse nicht —
# wer eine verknüpfte Athleten-ID kannte, konnte beliebige Abrufe auslösen und
# das Strava-Kontingent der ganzen Installation verbrauchen. Ein Ereignis mit
# fremder Subscription-ID wird deshalb verworfen. Ist die eigene noch
# unbekannt (kurz nach dem Start), wird nicht geprüft.
_eigene_subscription: dict = {"id": None}


def remember_subscription(subscriptions: list[dict]) -> None:
    if subscriptions:
        _eigene_subscription["id"] = subscriptions[0].get("id")


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    eigene = _eigene_subscription["id"]
    if eigene is not None and payload.get("subscription_id") not in (None, eigene):
        logger.warning("Webhook mit fremder Subscription %s verworfen", payload.get("subscription_id"))
        return {"status": "ignored"}

    objekt = payload.get("object_type")
    art = payload.get("aspect_type")
    athlete_id = payload.get("owner_id")
    if objekt == "activity" and art in ("create", "update", "delete"):
        # Vorher nur `create`. Eine nachträglich als Arbeitsweg markierte oder
        # bei Strava gelöschte Aktivität blieb in FORGE, wie sie war.
        background_tasks.add_task(process_strava_event, art, payload["object_id"], athlete_id)
    elif objekt == "athlete" and (payload.get("updates") or {}).get("authorized") == "false":
        # Der Athlet hat FORGE bei Strava die Freigabe entzogen. Die
        # Zugangsdaten blieben bisher liegen: Die Seite zeigte „verbunden",
        # und der Token-Refresh scheiterte jede Stunde.
        background_tasks.add_task(process_strava_deauth, athlete_id)

    return {"status": "ok"}


async def process_strava_deauth(athlete_id: int):
    from models import StravaCredentials
    from core.tenancy import SKIP_OPTION

    db = SessionLocal()
    try:
        weg = (
            db.query(StravaCredentials)
            .filter(StravaCredentials.athlete_id == athlete_id)
            .execution_options(**{SKIP_OPTION: True})
            .all()
        )
        for creds in weg:
            db.delete(creds)
        db.commit()
        logger.info("Strava-Freigabe für Athlet %s entzogen — Verbindung entfernt", athlete_id)
    except Exception as e:
        db.rollback()
        logger.error("Deautorisierung für Athlet %s nicht verarbeitet: %s", athlete_id, e)
    finally:
        db.close()


async def process_strava_event(art: str, activity_id: int, athlete_id: int):
    """Anlegen, Ändern, Löschen — über denselben Ingest wie der Abgleich."""
    if art == "create":
        return await process_new_strava_activity(activity_id, athlete_id)

    db = SessionLocal()
    try:
        from models import StravaCredentials
        from services.ingest import aktualisieren, entfernen
        from core.tenancy import SKIP_OPTION, acting_as

        creds = (
            db.query(StravaCredentials)
            .filter(StravaCredentials.athlete_id == athlete_id)
            .execution_options(**{SKIP_OPTION: True})
            .first()
        )
        if creds is None:
            return
        with acting_as(creds.user_id):
            if art == "update":
                result = await aktualisieren(db, activity_id, athlete_id)
            else:
                result = entfernen(db, activity_id)
        logger.info("Webhook %s %s (Nutzer %s): %s", art, activity_id, creds.user_id, result)
    except Exception as e:
        db.rollback()
        logger.error("Strava-Ereignis %s für %s fehlgeschlagen: %s", art, activity_id, e)
    finally:
        db.close()


async def process_new_strava_activity(activity_id: int, athlete_id: int):
    """Webhook-Pfad — nutzt denselben Ingest wie der Reconcile-Job.

    Zwei getrennte Implementierungen würden auseinanderdriften; hier gibt es
    nur eine, inklusive Duplikat-Matching und Obsidian-Sync.
    """
    db = SessionLocal()
    try:
        from models import StravaCredentials
        from services.ingest import ingest_activity
        from core.tenancy import SKIP_OPTION, acting_as

        # Strava ruft ohne Token an und nennt nur die Athleten-ID. Ohne diese
        # Auflösung liefe der Ingest ohne Nutzerkontext und ordnete die
        # Aktivität irgendeinem Konto zu — bei mehreren Athleten dem falschen.
        creds = (
            db.query(StravaCredentials)
            .filter(StravaCredentials.athlete_id == athlete_id)
            .execution_options(**{SKIP_OPTION: True})
            .first()
        )
        if creds is None:
            logger.warning("Webhook für unbekannten Strava-Athleten %s ignoriert", athlete_id)
            return

        with acting_as(creds.user_id):
            result = await ingest_activity(db, activity_id, athlete_id)
        logger.info(f"Webhook-Ingest {activity_id} (Nutzer {creds.user_id}): {result}")
    except Exception as e:
        # Verloren ist nichts: der Reconcile-Job zieht die Aktivität nach.
        logger.error(f"Failed to process Strava activity {activity_id}: {e}")
    finally:
        db.close()


@api_router.get("/api/strava/auth", response_model=StravaAuthUrl)
def strava_auth(request: Request, user=Depends(require_user)):
    """Autorisierungs-URL mit Nutzerbezug im state-Parameter.

    Strava ruft den Callback später ohne Token auf. Ohne diesen Umweg wüsste
    er nicht, für wen die Verbindung gilt.

    Der `state` ist ein Zwecktoken mit zehn Minuten Laufzeit — vorher das
    volle Zugangstoken, das mit der Adresse in Verlauf und Logs landete."""
    from core.security import create_purpose_token

    redirect_uri = str(request.base_url) + "api/strava/callback"
    state = create_purpose_token(user.id, OAUTH_ZWECK)
    service = StravaService(None)
    return StravaAuthUrl(auth_url=service.get_auth_url(redirect_uri, state=state))


OAUTH_ZWECK = "strava_oauth"
# Zwischen Callback und Bestätigung: Wer die Freigabe erteilt hat, steht fest,
# aber noch nicht, ob der angemeldete Browser derselbe Mensch ist.
#
# Warum der Umweg: Der `state` ist an das Konto gebunden, nicht an den
# Browser. Wer jemandem seinen eigenen Freigabelink schickt, bekäme dessen
# Strava an das eigene Konto gehängt — samt aller Aktivitäten. Jetzt wird erst
# verbunden, wenn das angemeldete Konto im Browser bestätigt; schickt jemand
# einen fremden Link, passt das Konto nicht, und es passiert nichts.
#
# Im Speicher genügt: Der Vorgang lebt Sekunden bis Minuten, und nach einem
# Neustart beginnt man die Verbindung eben neu.
AUSSTEHEND_MINUTEN = 10
_ausstehend: dict[str, dict] = {}


def _aufraeumen() -> None:
    from datetime import datetime, timedelta

    grenze = datetime.utcnow() - timedelta(minutes=AUSSTEHEND_MINUTEN)
    for schluessel in [k for k, v in _ausstehend.items() if v["am"] < grenze]:
        _ausstehend.pop(schluessel, None)


async def _historie_nachholen(user_id: int) -> None:
    """Beim ersten Verbinden die Historie holen.

    Ohne das startet ein neuer Athlet mit leerer Formkurve: Die Fitness
    (CTL) ist ein Mittel über 42 Tage, und aus zwei Wochen Daten ergibt sich
    ein Wert, der zu niedrig ist und es wochenlang bleibt. Der erste Plan
    entstünde auf dieser Grundlage.

    Eigene Sitzung und ausdrücklicher Mandantenkontext: Eine
    Hintergrundaufgabe startet, nachdem die Anfrage beendet ist — die
    ContextVar ist dann längst zurückgesetzt. Ohne `acting_as` liefe der
    Abgleich ohne Nutzer und schriebe die Aktivitäten dem falschen Konto zu.
    """
    from core.config import settings
    from core.tenancy import acting_as
    from database import SessionLocal
    from services.reconcile import reconcile_activities

    db = SessionLocal()
    try:
        with acting_as(user_id):
            # Mehrere Seiten: Über drei Monate passen mehr Aktivitäten in
            # den Zeitraum, als eine Seite fasst.
            ergebnis = await reconcile_activities(
                db, days=settings.STRAVA_BACKFILL_DAYS, limit=100, max_seiten=4
            )
        logger.info(
            "Historie für Nutzer %s nachgeholt (%s Tage): %s",
            user_id, settings.STRAVA_BACKFILL_DAYS, ergebnis.get("by_action"),
        )
    except Exception:
        # Kein Abbruch: Die Verbindung steht, nur die Historie fehlt. Der
        # stündliche Abgleich holt ab jetzt ohnehin alles Neue.
        logger.exception("Historie für Nutzer %s konnte nicht nachgeholt werden", user_id)
    finally:
        db.close()


@router.get("/api/strava/callback")
async def strava_callback(
    code: str,
    background_tasks: BackgroundTasks,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """Rückleitung von Strava — ohne Token, dafür mit unserem state.

    Verbindet noch nicht, sondern legt den Vorgang zur Bestätigung ab (siehe
    `_ausstehend`). Die Oberfläche bestätigt ihn mit dem angemeldeten Konto.
    """
    import secrets
    from datetime import datetime

    from core.security import purpose_token_payload, token_issued_after
    from core.urls import app_pfad
    from models import User

    # Am Ende dieses Aufrufs steht ein Mensch vor einem Browserfenster, nicht
    # ein Programm vor einer Antwort. Deshalb wird umgeleitet statt JSON
    # zurückgegeben — auch im Fehlerfall: Eine HTTPException zeigte dem
    # Athleten eine rohe Fehlerzeile auf der API-Domain, ohne Weg zurück.
    def fehler(grund: str):
        return RedirectResponse(app_pfad("/connect", strava="fehler", grund=grund), status_code=303)

    payload = purpose_token_payload(state, OAUTH_ZWECK)
    user = None
    if payload:
        try:
            user = db.get(User, int(payload["sub"]))
        except (KeyError, TypeError, ValueError):
            user = None
    # Abgemeldet oder gesperrt seit dem Start der Freigabe: dann nicht.
    if user is None or not user.is_active or not token_issued_after(payload, user.tokens_valid_from):
        return fehler(
            "Die Freigabe ist abgelaufen oder gehört zu keiner gültigen Anmeldung. "
            "Bitte starte die Verbindung erneut."
        )

    service = StravaService(db)
    try:
        token_data = await service.exchange_code(code)
    except Exception as e:
        logger.warning("Strava-OAuth für Nutzer %s fehlgeschlagen: %s", user.id, e)
        return fehler(str(e)[:200])

    _aufraeumen()
    vorgang = secrets.token_urlsafe(24)
    _ausstehend[vorgang] = {"user_id": user.id, "token_data": token_data, "am": datetime.utcnow()}
    return RedirectResponse(app_pfad("/connect", strava="bestaetigen", vorgang=vorgang),
                            status_code=303)


@api_router.post("/api/strava/bestaetigen")
def strava_bestaetigen(body: dict, background_tasks: BackgroundTasks,
                       db: Session = Depends(get_db), user=Depends(require_user)):
    """Die Freigabe mit dem angemeldeten Konto abschließen."""
    from core.tenancy import acting_as
    from models import TrainingSession

    _aufraeumen()
    eintrag = _ausstehend.get(str(body.get("vorgang") or ""))
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Dieser Verbindungsvorgang ist abgelaufen. Bitte neu starten.")
    if eintrag["user_id"] != user.id:
        # Nicht verbrauchen: Der richtige Nutzer kann ihn noch bestätigen.
        raise HTTPException(
            status_code=403,
            detail="Diese Strava-Freigabe wurde für ein anderes Konto gestartet "
                   "und wird hier nicht übernommen.",
        )
    _ausstehend.pop(str(body.get("vorgang")), None)

    service = StravaService(db)
    try:
        with acting_as(user.id):
            athlete_id = service.save_credentials(eintrag["token_data"])
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Nur beim ersten Mal nachholen. Wer die Verbindung erneuert, hat seine
    # Historie bereits — ein zweiter Durchlauf über drei Monate kostete dann
    # nur Strava-Kontingent.
    with acting_as(user.id):
        hat_einheiten = db.query(TrainingSession.id).first() is not None
    if not hat_einheiten:
        background_tasks.add_task(_historie_nachholen, user.id)
    return {"status": "ok", "athlete_id": athlete_id, "historie": not hat_einheiten}


@api_router.get("/api/strava/status", response_model=StravaConnected)
def strava_status(db: Session = Depends(get_db)):
    from models import StravaCredentials
    creds = db.query(StravaCredentials).first()
    if creds:
        return StravaConnected(connected=True, athlete_id=creds.athlete_id)
    return StravaConnected(connected=False)


@api_router.get("/api/strava/scheduler")
def scheduler_state():
    """Läuft der stündliche Abgleich, und wann kommt der nächste Lauf?"""
    from core.scheduler import scheduler_status
    return scheduler_status()


@api_router.get("/api/strava/subscription")
async def strava_subscription(db: Session = Depends(get_db)):
    """Health-Check der Webhook-Subscription."""
    from services.reconcile import check_subscription
    return await check_subscription(db)


@api_router.post("/api/strava/sync-now")
async def sync_now(db: Session = Depends(get_db)):
    """Sofort abgleichen — derselbe Ablauf wie der stündliche Job.

    Strava nachziehen, klassifizieren, Obsidian-Outbox abarbeiten. Damit
    muss nach einer Einheit nicht bis zur nächsten vollen Stunde gewartet
    werden.
    """
    from core.config import settings
    from services.reconcile import run_full_reconcile

    result = await run_full_reconcile(db, days=settings.RECONCILE_WINDOW_DAYS)
    activities = result["activities"]
    counts = activities.get("by_action", {})
    details = activities.get("details", [])

    # Notes entstehen bereits beim Einlesen jeder Aktivität; die Outbox
    # danach fängt nur noch Nachzügler ab. Beides zählen, sonst meldet der
    # Knopf null geschriebene Notes, obwohl gerade welche entstanden sind.
    written = sum(1 for d in details if d.get("obsidian") in ("written", "moved"))
    written += (result["obsidian"].get("by_status") or {}).get("written", 0)

    return {
        "ok": activities.get("status") == "ok",
        "checked": activities.get("checked", 0),
        "created": counts.get("created", 0),
        "linked": counts.get("linked", 0),
        "unchanged": counts.get("skipped_duplicate", 0),
        "obsidian_written": written,
        "error": activities.get("error"),
        "details": details,
    }


@api_router.post("/api/strava/reconcile")
async def strava_reconcile(
    days: int = 14,
    dry_run: bool = True,
    db: Session = Depends(get_db),
):
    """Verpasste Aktivitäten nachziehen.

    dry_run ist absichtlich der Standard: der Lauf zeigt erst, was er tun
    würde. Schreiben nur mit dry_run=false.
    """
    from services.reconcile import reconcile_activities
    return await reconcile_activities(db, days=days, dry_run=dry_run)
